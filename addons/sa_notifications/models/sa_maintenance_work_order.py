# -*- coding: utf-8 -*-
"""Auto-trigger: عند جدولة أمر العمل، أرسل بريد للفني المُسنَد."""
from odoo import models


class SaMaintenanceWorkOrderNotifications(models.Model):
    _inherit = 'sa.maintenance.work_order'

    def action_schedule(self):
        res = super().action_schedule()
        helper = self.env['sa.notifications.helper']
        if helper._is_enabled('maintenance_assigned_enabled'):
            for wo in self:
                if wo.technician_id and wo.technician_id.email:
                    helper._send_template(
                        'sa_notifications.mail_template_maintenance_assigned',
                        wo.id,
                    )
        return res
