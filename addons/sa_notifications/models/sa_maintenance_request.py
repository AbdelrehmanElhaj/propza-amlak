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
        helper = self.env['sa.notifications.helper']
        if helper._is_enabled('maintenance_received_enabled'):
            for r in records:
                if r.partner_id and r.partner_id.email:
                    helper._send_template(
                        'sa_notifications.mail_template_maintenance_received',
                        r.id,
                    )
        return records

    def action_done(self):
        """يُستدعى من الزرّ + cron — أضف بعده إرسال بريد إكمال."""
        res = super().action_done()
        helper = self.env['sa.notifications.helper']
        if helper._is_enabled('maintenance_completed_enabled'):
            for r in self:
                if r.partner_id and r.partner_id.email:
                    helper._send_template(
                        'sa_notifications.mail_template_maintenance_completed',
                        r.id,
                    )
        return res
