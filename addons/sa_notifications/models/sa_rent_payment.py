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
        unifonic = self.env['sa.unifonic.service']
        sent = 0
        for p in upcoming:
            if not p.tenant_id:
                continue
            if p.tenant_id.email:
                helper._send_template(
                    'sa_notifications.mail_template_payment_reminder', p.id
                )
            phone = unifonic._partner_phone(p.tenant_id)
            if phone:
                msg = (
                    f"عزيزنا {p.tenant_id.name}،\n"
                    f"تذكير: دفعة إيجار بمبلغ {p.amount:,.0f} ريال مستحقة بتاريخ {p.due_date}.\n"
                    f"يرجى السداد عبر البوابة الإلكترونية أو SADAD."
                )
                unifonic._send_whatsapp_sms(phone, msg)
            sent += 1
        return sent

    # ─── Cron 2: تنبيه متأخرات ─────────────────────────────────
    @api.model
    def _cron_send_overdue_alerts(self):
        helper   = self.env['sa.notifications.helper']
        unifonic = self.env['sa.unifonic.service']
        if not helper._is_enabled('payment_overdue_enabled'):
            return 0
        # Send only on milestone days to avoid spam
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
                if not p.tenant_id:
                    continue
                if p.tenant_id.email:
                    helper._send_template(
                        'sa_notifications.mail_template_payment_overdue', p.id
                    )
                phone = unifonic._partner_phone(p.tenant_id)
                if phone:
                    msg = (
                        f"تنبيه عاجل لـ {p.tenant_id.name}:\n"
                        f"دفعة إيجار متأخرة {d} يوم بمبلغ {p.amount:,.0f} ريال.\n"
                        f"يرجى التواصل فوراً لتجنب الغرامات."
                    )
                    unifonic._send_whatsapp_sms(phone, msg)
                sent += 1
        return sent
