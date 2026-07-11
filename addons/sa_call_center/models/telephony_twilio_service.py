# -*- coding: utf-8 -*-
"""محول Twilio — مزوّد اتصالات سحابي.

عكس Asterisk، لا تصل أحداث Twilio عبر webhook JSON بسيط: Twilio يطلب رداً
فورياً بتعليمات TwiML (XML) عند وصول مكالمة، ويرسل باقي التحديثات
form-encoded مع توقيع HMAC-SHA1 (`X-Twilio-Signature`) بدل token في ترويسة.

لا توجد حزمة `twilio` بايثون في هذه الحاوية ولا Dockerfile مخصص لإضافتها،
لذا يُطبَّق التحقق من التوقيع والاتصال بـ REST API يدوياً (نفس أسلوب
UltraMsg/Unifonic في sa_notifications — عبر `requests` فقط بدون SDK).
"""
import base64
import hashlib
import hmac
import json
import logging
import time
import uuid
import requests
from odoo import models, api

_logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 5
TWILIO_API_BASE = 'https://api.twilio.com/2010-04-01'


class SaTelephonyTwilioService(models.AbstractModel):
    _name = 'sa.telephony.twilio.service'
    _inherit = 'sa.telephony.gateway'
    _description = 'Twilio Voice connector'

    @api.model
    def _public_base_url(self):
        return self._cfg('twilio_public_base_url').strip().rstrip('/')

    @api.model
    def _validate_signature(self, url, params, signature, auth_token):
        """يعيد تطبيق خوارزمية توقيع Twilio يدوياً (بدون SDK).

        Twilio يوقّع: الرابط الكامل + قيم كل معاملات POST مرتّبة أبجدياً
        (مفتاح متبوعاً بقيمته، بلا فواصل)، عبر HMAC-SHA1 بمفتاح auth_token،
        ثم base64. يُقارَن الناتج بترويسة X-Twilio-Signature.
        """
        if not auth_token or not signature:
            return False
        data = url + ''.join(
            '%s%s' % (k, params[k]) for k in sorted(params.keys())
        )
        expected = base64.b64encode(
            hmac.new(auth_token.encode(), data.encode(), hashlib.sha1).digest()
        ).decode()
        return hmac.compare_digest(expected, signature)

    @api.model
    def _agent_identity(self, user):
        """معرّف ثابت وآمن للموظف كـ Twilio Client — بلا بيانات شخصية."""
        return 'agent_%s' % user.id

    @api.model
    def _b64url(self, data):
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

    @api.model
    def _generate_access_token(self, identity, ttl=3600):
        """يبني Twilio Access Token (JWT) يدوياً بدون SDK — لمنح متصفح الموظف
        صلاحية "Voice Grant" لاستقبال المكالمات (`incoming.allow`)، بالإضافة
        لصلاحية الاتصال الصادر (`outgoing`) إن كان TwiML App مضبوطاً.

        يرجع None إذا لم تُضبط بيانات اعتماد API Key/Secret بعد.
        """
        api_key_sid = self._cfg('twilio_api_key_sid').strip()
        api_key_secret = self._cfg('twilio_api_key_secret').strip()
        account_sid = self._cfg('twilio_account_sid').strip()
        if not (api_key_sid and api_key_secret and account_sid):
            return None

        voice_grant = {'incoming': {'allow': True}}
        twiml_app_sid = self._cfg('twilio_twiml_app_sid').strip()
        if twiml_app_sid:
            voice_grant['outgoing'] = {'application_sid': twiml_app_sid}

        now = int(time.time())
        header = {'typ': 'JWT', 'alg': 'HS256', 'cty': 'twilio-fpa;v=1'}
        payload = {
            'jti': '%s-%s' % (api_key_sid, uuid.uuid4().hex),
            'iss': api_key_sid,
            'sub': account_sid,
            'exp': now + ttl,
            'grants': {
                'identity': identity,
                'voice': voice_grant,
            },
        }
        segments = [
            self._b64url(json.dumps(header, separators=(',', ':')).encode()),
            self._b64url(json.dumps(payload, separators=(',', ':')).encode()),
        ]
        signature = hmac.new(
            api_key_secret.encode(), '.'.join(segments).encode(), hashlib.sha256
        ).digest()
        segments.append(self._b64url(signature))
        return '.'.join(segments)

    @api.model
    def originate_call(self, agent_phone, destination_number):
        """اتصال صادر (click-to-dial): يتصل Twilio أولاً بهاتف الوكيل،
        وعند الرد يربطه بالعميل عبر TwiML مضمّن.

        يرجع True عند نجاح إرسال الطلب إلى Twilio، False عند أي فشل.
        """
        account_sid = self._cfg('twilio_account_sid').strip()
        auth_token = self._cfg('twilio_auth_token').strip()
        twilio_number = self._cfg('twilio_phone_number').strip()
        if not (account_sid and auth_token and twilio_number):
            _logger.warning('sa_call_center: بيانات اعتماد Twilio غير مكتملة — تم تخطي originate')
            return False

        twiml = '<Response><Dial>%s</Dial></Response>' % destination_number
        try:
            requests.post(
                '%s/Accounts/%s/Calls.json' % (TWILIO_API_BASE, account_sid),
                data={
                    'To': agent_phone,
                    'From': twilio_number,
                    'Twiml': twiml,
                },
                auth=(account_sid, auth_token),
                timeout=REQUEST_TIMEOUT,
            )
            return True
        except Exception:
            _logger.exception('sa_call_center: فشل طلب originate_call عبر Twilio')
            return False
