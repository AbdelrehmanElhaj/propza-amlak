# -*- coding: utf-8 -*-
"""Auto-triggers على طلبات الصيانة:
    * عند الإنشاء → بريد تأكيد للمستأجر
    * عند الإنجاز → بريد إشعار إكمال للمستأجر
"""
from odoo import models, api


class SaMaintenanceRequestNotifications(models.Model):
    _inherit = 'sa.maintenance.request'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        helper   = self.env['sa.notifications.helper']
        unifonic = self.env['sa.unifonic.service']
        if helper._is_enabled('maintenance_received_enabled'):
            for r in records:
                if r.partner_id:
                    if r.partner_id.email:
                        helper._send_template(
                            'sa_notifications.mail_template_maintenance_received',
                            r.id,
                        )
                    phone = unifonic._partner_phone(r.partner_id)
                    if phone:
                        msg = (
                            f"عزيزنا {r.partner_id.name}،\n"
                            f"تم استلام طلب الصيانة رقم {r.name}.\n"
                            f"سنتواصل معك قريباً لتحديد الموعد."
                        )
                        unifonic._send_whatsapp_sms(phone, msg)
        return records

    def action_done(self):
        """يُستدعى من الزرّ + cron — أضف بعده إرسال بريد + WA/SMS إكمال."""
        res = super().action_done()
        helper   = self.env['sa.notifications.helper']
        unifonic = self.env['sa.unifonic.service']
        if helper._is_enabled('maintenance_completed_enabled'):
            for r in self:
                if r.partner_id:
                    if r.partner_id.email:
                        helper._send_template(
                            'sa_notifications.mail_template_maintenance_completed',
                            r.id,
                        )
                    phone = unifonic._partner_phone(r.partner_id)
                    if phone:
                        msg = (
                            f"عزيزنا {r.partner_id.name}،\n"
                            f"تم إنجاز طلب الصيانة {r.name} بنجاح. شكراً لثقتكم."
                        )
                        unifonic._send_whatsapp_sms(phone, msg)
        return res
