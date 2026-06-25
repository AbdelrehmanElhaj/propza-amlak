# -*- coding: utf-8 -*-
"""خدمة UltraMsg لإرسال رسائل WhatsApp فقط (لا يدعم SMS)."""
import logging
import requests
from odoo import models, api

_logger = logging.getLogger(__name__)

ULTRAMSG_URL    = 'https://api.ultramsg.com/{instance_id}/messages/chat'
REQUEST_TIMEOUT = 10


class UltramsgService(models.AbstractModel):
    _name        = 'sa.ultramsg.service'
    _description = 'UltraMsg WhatsApp-only gateway'
    _inherit     = 'sa.messaging.gateway'

    @api.model
    def _ultramsg_send_whatsapp(self, phone, message):
        """
        إرسال رسالة WhatsApp عبر UltraMsg API.
        يستخدم + prefix لأن UltraMsg يقبل كلا الشكلين وهذا هو الأكثر أماناً.
        يرجع True عند النجاح، False عند الفشل.
        """
        instance_id = self._cfg('ultramsg_instance_id').strip()
        token       = self._cfg('ultramsg_token').strip()

        if not instance_id or not token:
            _logger.warning('sa_ultramsg: instance_id أو token غير مضبوط — تم تخطي WA')
            return False

        number = self._normalize_phone(phone)
        if not number:
            _logger.warning('sa_ultramsg: رقم هاتف غير صالح "%s" — تم تخطي WA', phone)
            return False

        url = ULTRAMSG_URL.format(instance_id=instance_id)
        try:
            resp = requests.post(
                url,
                data={
                    'token': token,
                    'to':    '+' + number,
                    'body':  message,
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=REQUEST_TIMEOUT,
            )
            data = resp.json()
            if str(data.get('sent', '')).lower() == 'true':
                _logger.info('sa_ultramsg: WhatsApp أُرسل → +%s (id=%s)',
                             number, data.get('id', ''))
                return True
            _logger.warning('sa_ultramsg: فشل WA: %s', data)
            return False
        except Exception:
            _logger.exception('sa_ultramsg: استثناء WA للرقم +%s', number)
            return False
