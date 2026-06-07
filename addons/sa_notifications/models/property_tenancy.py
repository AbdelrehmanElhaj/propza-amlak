# -*- coding: utf-8 -*-
"""تنبيهات العقود: انتهاء قريب + اقتراح تجديد."""
from odoo import models, api
from datetime import date, timedelta


class PropertyTenancyNotifications(models.Model):
    _inherit = 'property.tenancy'

    # ─── Cron 3: تنبيه عقود تنتهي قريباً ───────────────────────
    @api.model
    def _cron_send_expiring_alerts(self):
        helper   = self.env['sa.notifications.helper']
        unifonic = self.env['sa.unifonic.service']
        if not helper._is_enabled('contract_expiring_enabled'):
            return 0
        days_before = helper._get_int('contract_expiring_days', 30)
        target_date = date.today() + timedelta(days=days_before)

        expiring = self.search([
            ('state', '=', 'running'),
            ('end_date', '=', target_date),
            ('renewed_to_id', '=', False),
        ])
        sent = 0
        for t in expiring:
            if t.partner_id.email or t.owner_partner_id.email:
                helper._send_template(
                    'sa_notifications.mail_template_contract_expiring', t.id
                )
            phone = unifonic._partner_phone(t.partner_id)
            if phone:
                msg = (
                    f"عزيزنا {t.partner_id.name}،\n"
                    f"عقد الإيجار {t.name} ينتهي خلال {days_before} يوم ({t.end_date}).\n"
                    f"تواصل معنا للتجديد قبل فوات الأوان."
                )
                unifonic._send_whatsapp_sms(phone, msg)
            sent += 1
        return sent

    # ─── Auto-trigger: عند توليد عقد تجديد، أرسل اقتراحاً ──────
    def _do_renewal(self, **kwargs):
        """امتداد لـ _do_renewal في sa_rental_cycle: يرسل بريد + WA/SMS اقتراح تجديد."""
        new_tenancy = super()._do_renewal(**kwargs)
        helper   = self.env['sa.notifications.helper']
        unifonic = self.env['sa.unifonic.service']
        if new_tenancy and helper._is_enabled('renewal_proposed_enabled'):
            if new_tenancy.owner_partner_id.email or new_tenancy.partner_id.email:
                helper._send_template(
                    'sa_notifications.mail_template_renewal_proposed',
                    new_tenancy.id,
                )
            phone = unifonic._partner_phone(new_tenancy.owner_partner_id)
            if phone:
                msg = (
                    f"عزيزنا {new_tenancy.owner_partner_id.name}،\n"
                    f"عقد تجديد {new_tenancy.name} جاهز للمراجعة والموافقة."
                )
                unifonic._send_whatsapp_sms(phone, msg)
        return new_tenancy
