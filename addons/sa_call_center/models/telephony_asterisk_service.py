# -*- coding: utf-8 -*-
"""محول Asterisk (ARI) — أول محول فعلي لبوابة الاتصالات.

استقبال الأحداث (رنين/رد/إنهاء) يصل عبر webhook وسيط (controllers/telephony_webhook.py)
لأن Odoo لا يتصل مباشرة بمقبس AMI من كنترولر HTTP. هذا الملف مسؤول فقط عن
الاتصال الصادر (click-to-dial) عبر REST API الخاص بـ ARI.
"""
import logging
import requests
from odoo import models, api

_logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 5


class SaTelephonyAsteriskService(models.AbstractModel):
    _name = 'sa.telephony.asterisk.service'
    _inherit = 'sa.telephony.gateway'
    _description = 'Asterisk ARI connector'

    @api.model
    def _ari_base_url(self):
        host = self._cfg('asterisk_ari_host').strip()
        if not host:
            return None
        port = self._cfg('asterisk_ari_port').strip() or '8088'
        return 'http://%s:%s/ari' % (host, port)

    @api.model
    def originate_call(self, agent_extension, destination_number):
        """يطلب من Asterisk ARI بدء اتصال صادر بين هاتف الوكيل والعميل.

        يرجع True عند نجاح إرسال الطلب إلى Asterisk، False عند أي فشل.
        """
        base_url = self._ari_base_url()
        if not base_url:
            _logger.warning('sa_call_center: Asterisk ARI host غير مضبوط — تم تخطي originate')
            return False

        user = self._cfg('asterisk_ari_user')
        password = self._cfg('asterisk_ari_password')
        try:
            requests.post(
                '%s/channels' % base_url,
                params={
                    'endpoint': 'PJSIP/%s' % agent_extension,
                    'extension': destination_number,
                    'context': 'from-internal',
                    'priority': 1,
                    'app': 'sa_call_center',
                },
                auth=(user, password),
                timeout=REQUEST_TIMEOUT,
            )
            return True
        except Exception:
            _logger.exception('sa_call_center: فشل طلب originate_call عبر Asterisk ARI')
            return False
