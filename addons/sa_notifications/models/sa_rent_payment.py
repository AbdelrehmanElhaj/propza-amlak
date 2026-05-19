# -*- coding: utf-8 -*-
"""تنبيهات الدفعات: تذكير قبل الاستحقاق + متأخرات."""
from odoo import models, api
from datetime import date, timedelta


class SaRentPaymentNotifications(models.Model):
    _inherit = 'sa.rent.payment'

    # ─── Cron 1: تذكير قبل الاستحقاق ───────────────────────────
    @api.model
    def _cron_send_payment_reminders(self):
        helper = self.env['sa.notifications.helper']
        if not helper._is_enabled('payment_reminder_enabled'):
            return 0
        days_before = helper._get_int('payment_reminder_days', 7)
        target_date = date.today() + timedelta(days=days_before)

        upcoming = self.search([
            ('state', 'in', ('pending', 'partial')),
            ('due_date', '=', target_date),
            ('payment_type', '=', 'rent'),
        ])
        sent = 0
        for p in upcoming:
            if p.tenant_id and p.tenant_id.email:
                if helper._send_template(
                    'sa_notifications.mail_template_payment_reminder', p.id
                ):
                    sent += 1
        return sent

    # ─── Cron 2: تنبيه متأخرات ─────────────────────────────────
    @api.model
    def _cron_send_overdue_alerts(self):
        helper = self.env['sa.notifications.helper']
        if not helper._is_enabled('payment_overdue_enabled'):
            return 0
        # Send only on day 1 + day 7 + day 14 + day 30 of overdue
        # (avoid spam — significant milestones)
        target_overdue_days = [1, 7, 14, 30]
        sent = 0
        for d in target_overdue_days:
            target_date = date.today() - timedelta(days=d)
            overdue = self.search([
                ('state', '=', 'overdue'),
                ('due_date', '=', target_date),
                ('payment_type', '=', 'rent'),
            ])
            for p in overdue:
                if p.tenant_id and p.tenant_id.email:
                    if helper._send_template(
                        'sa_notifications.mail_template_payment_overdue', p.id
                    ):
                        sent += 1
        return sent
