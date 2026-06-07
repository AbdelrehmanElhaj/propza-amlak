# -*- coding: utf-8 -*-
"""Auto-trigger: عند جدولة أمر العمل، أرسل بريد للفني المُسنَد."""
from odoo import models


class SaMaintenanceWorkOrderNotifications(models.Model):
    _inherit = 'sa.maintenance.work_order'

    def action_schedule(self):
        res = super().action_schedule()
        helper   = self.env['sa.notifications.helper']
        unifonic = self.env['sa.unifonic.service']
        if helper._is_enabled('maintenance_assigned_enabled'):
            for wo in self:
                if wo.technician_id:
                    if wo.technician_id.email:
                        helper._send_template(
                            'sa_notifications.mail_template_maintenance_assigned',
                            wo.id,
                        )
                    phone = unifonic._partner_phone(wo.technician_id.partner_id)
                    if phone:
                        prop_name = (wo.maintenance_id.property_id.name
                                     if wo.maintenance_id and wo.maintenance_id.property_id
                                     else '')
                        scheduled = wo.scheduled_date or 'قريباً'
                        msg = (
                            f"أمر عمل جديد: {wo.name}\n"
                            f"العقار: {prop_name}\n"
                            f"الموعد: {scheduled}"
                        )
                        unifonic._send_whatsapp_sms(phone, msg)
        return res
