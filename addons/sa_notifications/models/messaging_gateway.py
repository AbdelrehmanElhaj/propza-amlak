# -*- coding: utf-8 -*-
"""بوابة التوجيه المركزية للرسائل — تدعم Unifonic وUltraMsg مع fallback خلفي."""
import re
import logging
from odoo import models, api

_logger = logging.getLogger(__name__)


class SaMessagingGateway(models.AbstractModel):
    _name = 'sa.messaging.gateway'
    _description = 'Multi-provider messaging gateway (WhatsApp / SMS)'

    # ─── Config helpers ──────────────────────────────────────────────
    @api.model
    def _cfg(self, key):
        return self.env['ir.config_parameter'].sudo().get_param(
            'sa_notifications.%s' % key, default=''
        )

    @api.model
    def _cfg_bool(self, key, default='False'):
        return self.env['ir.config_parameter'].sudo().get_param(
            'sa_notifications.%s' % key, default=default
        ).lower() in ('true', '1', 'yes')

    # ─── Phone normalisation (single authoritative copy) ────────────
    @api.model
    def _normalize_phone(self, phone):
        """Return E.164 digits (no +) for Saudi numbers, e.g. 9665XXXXXXXX."""
        if not phone:
            return None
        digits = re.sub(r'\D', '', phone)
        if digits.startswith('00'):
            digits = digits[2:]
        if digits.startswith('0') and len(digits) == 10:
            digits = '966' + digits[1:]
        if not digits.startswith('966'):
            digits = '966' + digits
        return digits if 11 <= len(digits) <= 13 else None

    # ─── Partner phone helper ────────────────────────────────────────
    @api.model
    def _partner_phone(self, partner):
        """Return mobile, then phone from a res.partner record."""
        return partner and (partner.mobile or partner.phone) or None

    # ─── Provider resolution with backward-compat fallback ───────────
    @api.model
    def _get_provider(self):
        """
        Read messaging_provider config.
        Backward compat: if absent/empty but unifonic_enabled=True → 'unifonic'.
        """
        provider = self._cfg('messaging_provider').strip().lower()
        if provider in ('unifonic', 'ultramsg', 'disabled'):
            return provider
        if self._cfg_bool('unifonic_enabled'):
            return 'unifonic'
        return 'disabled'

    # ─── Public routing method ───────────────────────────────────────
    @api.model
    def _send_whatsapp_sms(self, phone, message):
        """توجيه الرسالة للمزوّد المختار. يرجع True عند النجاح."""
        provider = self._get_provider()

        if provider == 'unifonic':
            svc    = self.env['sa.unifonic.service']
            wa_on  = self._cfg_bool('whatsapp_enabled', default='True')
            sms_on = self._cfg_bool('sms_enabled', default='True')
            if wa_on and svc._unifonic_send_whatsapp(phone, message):
                return True
            return bool(sms_on and svc._unifonic_send_sms(phone, message))

        if provider == 'ultramsg':
            return self.env['sa.ultramsg.service']._ultramsg_send_whatsapp(
                phone, message
            )

        _logger.debug('sa.messaging.gateway: messaging disabled — message not sent')
        return False
