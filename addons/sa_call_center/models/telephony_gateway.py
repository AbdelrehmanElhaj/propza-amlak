# -*- coding: utf-8 -*-
"""بوابة الاتصالات المركزية — إعدادات المزود + بحث العميل بالرقم.

يوازي `sa.messaging.gateway` في sa_notifications، ويعيد استخدام
`_normalize_phone` منه بدل تكرار منطق التطبيع.
"""
import logging
from odoo import models, api

_logger = logging.getLogger(__name__)


class SaTelephonyGateway(models.AbstractModel):
    _name = 'sa.telephony.gateway'
    _description = 'Telephony provider gateway (SIP/VoIP)'

    @api.model
    def _cfg(self, key):
        return self.env['ir.config_parameter'].sudo().get_param(
            'sa_call_center.%s' % key, default=''
        )

    @api.model
    def _cfg_bool(self, key, default='False'):
        return self.env['ir.config_parameter'].sudo().get_param(
            'sa_call_center.%s' % key, default=default
        ).lower() in ('true', '1', 'yes')

    @api.model
    def _get_provider(self):
        provider = self._cfg('telephony_provider').strip().lower()
        return provider if provider in ('asterisk',) else 'disabled'

    @api.model
    def _find_partner_by_phone(self, phone):
        """يبحث عن res.partner برقم هاتف (mobile ثم phone)، مع تطبيع الأرقام.

        يجرّب أولاً مطابقة مباشرة على أشكال شائعة للرقم (سريع، عبر SQL)،
        ثم يتراجع لمسح وتطبيع الأرقام المخزَّنة عند عدم التطابق (لتغطية
        تنسيقات غير معتادة مثل المسافات أو الشرطات).
        """
        Gateway = self.env['sa.messaging.gateway']
        normalized = Gateway._normalize_phone(phone)
        if not normalized:
            return self.env['res.partner']

        local = normalized[3:] if normalized.startswith('966') else normalized
        candidates = list({normalized, '+' + normalized, '00' + normalized, '0' + local, local})

        Partner = self.env['res.partner'].sudo()
        partner = Partner.search([('mobile', 'in', candidates)], limit=1)
        if not partner:
            partner = Partner.search([('phone', 'in', candidates)], limit=1)
        if not partner:
            loose = Partner.search([
                '|', ('mobile', '!=', False), ('phone', '!=', False),
            ])
            partner = loose.filtered(
                lambda p: Gateway._normalize_phone(p.mobile) == normalized
                or Gateway._normalize_phone(p.phone) == normalized
            )[:1]
        return partner
