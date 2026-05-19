# -*- coding: utf-8 -*-
"""تنبيهات العقود: انتهاء قريب + اقتراح تجديد."""
from odoo import models, api
from datetime import date, timedelta


class PropertyTenancyNotifications(models.Model):
    _inherit = 'property.tenancy'

    # ─── Cron 3: تنبيه عقود تنتهي قريباً ───────────────────────
    @api.model
    def _cron_send_expiring_alerts(self):
        helper = self.env['sa.notifications.helper']
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
                if helper._send_template(
                    'sa_notifications.mail_template_contract_expiring', t.id
                ):
                    sent += 1
        return sent

    # ─── Auto-trigger: عند توليد عقد تجديد، أرسل اقتراحاً ──────
    def _do_renewal(self, **kwargs):
        """امتداد لـ _do_renewal في sa_rental_cycle: يرسل بريد اقتراح تجديد."""
        new_tenancy = super()._do_renewal(**kwargs)
        helper = self.env['sa.notifications.helper']
        if (new_tenancy and helper._is_enabled('renewal_proposed_enabled')
                and (new_tenancy.owner_partner_id.email
                     or new_tenancy.partner_id.email)):
            helper._send_template(
                'sa_notifications.mail_template_renewal_proposed',
                new_tenancy.id,
            )
        return new_tenancy
