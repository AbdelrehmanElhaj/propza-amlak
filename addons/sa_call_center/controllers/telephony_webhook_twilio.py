# -*- coding: utf-8 -*-
"""Webhooks Twilio Voice — صيغة وسلوك مختلفان جذرياً عن الـ webhook العام:

- Twilio يرسل الجسم form-encoded (ليس JSON) ويطلب رداً فورياً بتعليمات
  TwiML (XML) عند وصول المكالمة.
- التحقق من الطلب عبر توقيع `X-Twilio-Signature` (HMAC-SHA1) وليس token.

Endpoints (تُضبط في لوحة تحكم Twilio على رقم الهاتف):
    Voice URL:           POST /callcenter/webhook/twilio/voice
    Status Callback URL: POST /callcenter/webhook/twilio/status
"""
import logging
from datetime import timedelta
from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)

MISSED_STATUSES = {'busy', 'no-answer', 'failed', 'canceled'}


class CallCenterTwilioWebhookController(http.Controller):

    def _twiml_response(self, xml_body):
        return request.make_response(
            '<?xml version="1.0" encoding="UTF-8"?>%s' % xml_body,
            headers=[('Content-Type', 'text/xml')],
        )

    def _validate(self, path):
        Twilio = request.env['sa.telephony.twilio.service'].sudo()
        auth_token = Twilio._cfg('twilio_auth_token').strip()
        base_url = Twilio._public_base_url()
        signature = request.httprequest.headers.get('X-Twilio-Signature', '')
        params = dict(request.httprequest.form)
        if not base_url:
            _logger.warning('sa_call_center: Twilio Public Base URL غير مضبوط')
            return False
        url = base_url + path
        return Twilio._validate_signature(url, params, signature, auth_token)

    @http.route('/callcenter/webhook/twilio/voice', type='http', auth='none',
                methods=['POST'], csrf=False)
    def twilio_voice(self, **kwargs):
        if not self._validate('/callcenter/webhook/twilio/voice'):
            _logger.warning('Twilio voice webhook: invalid signature')
            return self._twiml_response('<Response><Reject/></Response>')

        form = request.httprequest.form
        call_uid = form.get('CallSid')
        Call = request.env['sa.call.center.call'].sudo()
        if call_uid and not Call.search([('call_uid', '=', call_uid)], limit=1):
            Call.create({
                'call_uid': call_uid,
                'direction': 'in',
                'from_number': form.get('From'),
                'to_number': form.get('To'),
                'state': 'ringing',
            })

        Twilio = request.env['sa.telephony.twilio.service'].sudo()
        forward_number = Twilio._cfg('twilio_forward_number').strip()

        # يُرن على كل موظف مفعّل is_call_center_agent (سمّاعة المتصفح) وعلى
        # الرقم الثابت في آن واحد — أول من يرد يحصل على المكالمة. Twilio
        # يتجاهل بصمت أي Client غير مسجَّل حالياً ويستمر بباقي الأطراف.
        agents = request.env['res.users'].sudo().search([
            ('is_call_center_agent', '=', True),
        ])
        dial_targets = ''.join(
            '<Client>%s</Client>' % Twilio._agent_identity(agent) for agent in agents
        )
        if forward_number:
            dial_targets += '<Number>%s</Number>' % forward_number

        if not dial_targets:
            _logger.warning('sa_call_center: لا يوجد موظفون مفعَّلون ولا رقم تحويل ثابت لـ Twilio')
            return self._twiml_response('<Response><Reject/></Response>')

        # answerOnBridge: لا يُعتبر الطرف المتصل "مُجاباً" فعلياً حتى تكتمل
        # عملية الربط الحقيقية مع الطرف الذي رد — يمنع تشغيل نغمات/صوت مؤقت
        # قبل اكتمال الجسر الصوتي الفعلي بين الطرفين.
        return self._twiml_response(
            '<Response><Dial answerOnBridge="true">%s</Dial></Response>' % dial_targets
        )

    def _apply_call_status(self, call, form):
        """يطبّق CallStatus القادم من Twilio على سجل مكالمة — مشترك بين
        الوارد (يُطابَق بـ CallSid) والصادر (يُطابَق بمعرّف السجل مباشرة)."""
        call_status = form.get('CallStatus')
        if call_status == 'ringing':
            call.write({'state': 'ringing'})
        elif call_status == 'in-progress':
            call.write({'state': 'answered', 'answer_datetime': fields.Datetime.now()})
        elif call_status == 'completed':
            end_dt = fields.Datetime.now()
            vals = {'state': 'ended', 'end_datetime': end_dt}
            recording_url = form.get('RecordingUrl')
            if recording_url:
                vals['recording_url'] = recording_url

            # نمط استدعاء Twilio على مستوى الرقم يرسل حدثاً نهائياً واحداً فقط
            # (لا يوجد حدث "in-progress" منفصل) — نستنتج أن المكالمة أُجيبت من
            # CallDuration (المدة الفعلية للمكالمة بالثواني، موجودة فقط عند
            # اكتمال مكالمة تم الرد عليها فعلياً) بدل الاعتماد على answer_datetime.
            call_duration = form.get('CallDuration') or form.get('Duration')
            if not call.answer_datetime and call_duration and int(call_duration) > 0:
                vals['answer_datetime'] = end_dt - timedelta(seconds=int(call_duration))
            if not call.answer_datetime and not vals.get('answer_datetime'):
                vals['state'] = 'missed'
            call.write(vals)
        elif call_status in MISSED_STATUSES:
            call.write({'state': 'missed', 'end_datetime': fields.Datetime.now()})

    @http.route('/callcenter/webhook/twilio/status', type='http', auth='none',
                methods=['POST'], csrf=False)
    def twilio_status(self, **kwargs):
        if not self._validate('/callcenter/webhook/twilio/status'):
            _logger.warning('Twilio status webhook: invalid signature')
            return request.make_response('invalid signature', status=403)

        form = request.httprequest.form
        call_uid = form.get('CallSid')
        Call = request.env['sa.call.center.call'].sudo()
        call = Call.search([('call_uid', '=', call_uid)], limit=1)
        if not call:
            return request.make_response('call not found', status=404)

        self._apply_call_status(call, form)
        return request.make_response('OK')

    @http.route('/callcenter/webhook/twilio/outbound-voice', type='http', auth='none',
                methods=['POST'], csrf=False)
    def twilio_outbound_voice(self, **kwargs):
        """Voice Request URL لتطبيق TwiML الخاص بالاتصال الصادر — يستدعيه
        Twilio عندما تطلب سمّاعة المتصفح (Device.connect) اتصالاً صادراً.
        ينشئ سجل مكالمة صادرة فوراً، ثم يربط الوكيل بالعميل المطلوب."""
        if not self._validate('/callcenter/webhook/twilio/outbound-voice'):
            _logger.warning('Twilio outbound-voice webhook: invalid signature')
            return self._twiml_response('<Response><Reject/></Response>')

        form = request.httprequest.form
        destination = (form.get('To') or '').strip()
        if not destination:
            return self._twiml_response('<Response><Reject/></Response>')

        Twilio = request.env['sa.telephony.twilio.service'].sudo()
        twilio_number = Twilio._cfg('twilio_phone_number').strip()

        from_identity = form.get('From', '')  # مثال: "client:agent_5"
        agent = request.env['res.users'].sudo()
        if from_identity.startswith('client:agent_'):
            agent = agent.browse(int(from_identity[len('client:agent_'):]))

        call = request.env['sa.call.center.call'].sudo().create({
            'call_uid': form.get('CallSid'),
            'direction': 'out',
            'from_number': twilio_number,
            'to_number': destination,
            'agent_id': agent.id if agent else False,
            'state': 'ringing',
        })

        base_url = Twilio._public_base_url()
        status_url = '%s/callcenter/webhook/twilio/outbound-status/%d' % (base_url, call.id)
        return self._twiml_response(
            '<Response><Dial answerOnBridge="true" callerId="%s">'
            '<Number statusCallback="%s" statusCallbackEvent="ringing answered completed">%s</Number>'
            '</Dial></Response>' % (twilio_number, status_url, destination)
        )

    @http.route('/callcenter/webhook/twilio/outbound-status/<int:call_id>', type='http', auth='none',
                methods=['POST'], csrf=False)
    def twilio_outbound_status(self, call_id, **kwargs):
        """Status callback لطرف العميل في مكالمة صادرة — يُطابَق مباشرة
        بمعرّف سجل `sa.call.center.call` (وُضع في الرابط عند الإنشاء) بدل
        CallSid، لأن هذا الطرف يحمل CallSid مختلفاً عن مكالمة العميل الأصلية
        من المتصفح إلى Twilio."""
        if not self._validate('/callcenter/webhook/twilio/outbound-status/%d' % call_id):
            _logger.warning('Twilio outbound-status webhook: invalid signature')
            return request.make_response('invalid signature', status=403)

        call = request.env['sa.call.center.call'].sudo().browse(call_id)
        if not call.exists():
            return request.make_response('call not found', status=404)

        self._apply_call_status(call, request.httprequest.form)
        return request.make_response('OK')
