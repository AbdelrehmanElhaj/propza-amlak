# -*- coding: utf-8 -*-
"""دوال مساعدة لإرسال الإشعارات + قراءة إعدادات النظام."""
from odoo import models, api
import logging
_logger = logging.getLogger(__name__)


class SaNotificationsHelper(models.AbstractModel):
    _name = 'sa.notifications.helper'
    _description = 'Notifications helper'

    @api.model
    def _is_enabled(self, key):
        """يقرأ إعداد True/False من ir.config_parameter."""
        param = self.env['ir.config_parameter'].sudo().get_param(
            'sa_notifications.%s' % key, default='True'
        )
        return str(param).lower() in ('true', '1', 'yes', 'on')

    @api.model
    def _get_int(self, key, default):
        """يقرأ إعداد عددي."""
        try:
            return int(self.env['ir.config_parameter'].sudo().get_param(
                'sa_notifications.%s' % key, default=str(default)
            ))
        except (ValueError, TypeError):
            return default

    @api.model
    def _send_template(self, template_xml_id, record_id, force=False):
        """يُرسل قالب بريد على سجل محدد. يبتلع الأخطاء ويسجلها."""
        try:
            tpl = self.env.ref(template_xml_id, raise_if_not_found=False)
            if not tpl:
                _logger.warning('Notification template not found: %s', template_xml_id)
                return False
            tpl.send_mail(record_id, force_send=force)
            return True
        except Exception as e:
            _logger.exception('Failed to send notification %s for record %s: %s',
                              template_xml_id, record_id, e)
            return False

    @api.model
    def _send_whatsapp_sms(self, phone, message):
        """يُرسل رسالة عبر المزوّد المُختار (Unifonic أو UltraMsg أو معطّل)."""
        return self.env['sa.messaging.gateway']._send_whatsapp_sms(phone, message)
