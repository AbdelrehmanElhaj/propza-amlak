# -*- coding: utf-8 -*-
"""خدمة Unifonic لإرسال الرسائل عبر WhatsApp وSMS مع fallback تلقائي."""
import re
import logging
import requests
from odoo import models, api

_logger = logging.getLogger(__name__)

UNIFONIC_SMS_URL = 'https://api.unifonic.com/rest/Messages/Send'
UNIFONIC_WA_URL  = 'https://messaging.unifonic.com/v2/messages'
REQUEST_TIMEOUT  = 10


class UnifoniService(models.AbstractModel):
    _name = 'sa.unifonic.service'
    _description = 'Unifonic SMS/WhatsApp gateway'

    # ─── Phone normalisation ─────────────────────────────────────────
    @api.model
    def _normalize_phone(self, phone):
        """Return E.164 digits (no +) for Saudi numbers, e.g. 9665XXXXXXXX."""
        if not phone:
            return None
        digits = re.sub(r'\D', '', phone)
        if digits.startswith('00'):
            digits = digits[2:]
        if digits.startswith('0') and len(digits) == 10:
            # 05XXXXXXXX → 9665XXXXXXXX
            digits = '966' + digits[1:]
        if not digits.startswith('966'):
            digits = '966' + digits
        # Saudi mobile: 9665XXXXXXXX (12 digits)
        if not (11 <= len(digits) <= 13):
            return None
        return digits

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

    # ─── SMS via Unifonic REST ───────────────────────────────────────
    @api.model
    def _unifonic_send_sms(self, phone, message):
        """Sends an SMS. Returns True on success, False on failure."""
        app_sid   = self._cfg('unifonic_app_sid')
        sender_id = self._cfg('unifonic_sender_id') or 'Propza'
        if not app_sid:
            _logger.warning('sa_unifonic: AppSid not configured — SMS skipped')
            return False
        number = self._normalize_phone(phone)
        if not number:
            _logger.warning('sa_unifonic: invalid phone "%s" — SMS skipped', phone)
            return False
        try:
            resp = requests.post(UNIFONIC_SMS_URL, data={
                'AppSid':    app_sid,
                'Recipient': number,
                'Body':      message,
                'SenderID':  sender_id,
            }, timeout=REQUEST_TIMEOUT)
            data = resp.json()
            if data.get('Success'):
                _logger.info('sa_unifonic: SMS sent → %s', number)
                return True
            _logger.warning('sa_unifonic: SMS failed: %s', data)
            return False
        except Exception:
            _logger.exception('sa_unifonic: SMS exception for %s', number)
            return False

    # ─── WhatsApp via Unifonic CPaaS ─────────────────────────────────
    @api.model
    def _unifonic_send_whatsapp(self, phone, message):
        """Sends a WhatsApp message. Returns True on success, False on failure."""
        token  = self._cfg('unifonic_token')
        sender = self._cfg('unifonic_whatsapp_sender')
        if not token or not sender:
            _logger.warning('sa_unifonic: WA token/sender not configured — WA skipped')
            return False
        number = self._normalize_phone(phone)
        if not number:
            _logger.warning('sa_unifonic: invalid phone "%s" — WA skipped', phone)
            return False
        try:
            resp = requests.post(UNIFONIC_WA_URL, json={
                'channel':   'whatsapp',
                'sender':    sender,
                'recipient': {'phone': number},
                'message':   {'text': message},
            }, headers={
                'Authorization': 'Bearer ' + token,
                'Content-Type':  'application/json',
            }, timeout=REQUEST_TIMEOUT)
            if resp.status_code in (200, 201):
                _logger.info('sa_unifonic: WhatsApp sent → %s', number)
                return True
            _logger.warning('sa_unifonic: WA failed (%s): %s', resp.status_code, resp.text[:200])
            return False
        except Exception:
            _logger.exception('sa_unifonic: WA exception for %s', number)
            return False

    # ─── Combined: WhatsApp-first, SMS fallback ──────────────────────
    @api.model
    def _send_whatsapp_sms(self, phone, message):
        """Try WhatsApp first; fall back to SMS if WA fails or is disabled.
        Returns True if at least one channel delivered the message."""
        if not self._cfg_bool('unifonic_enabled'):
            return False
        wa_on  = self._cfg_bool('whatsapp_enabled', default='True')
        sms_on = self._cfg_bool('sms_enabled', default='True')
        if wa_on and self._unifonic_send_whatsapp(phone, message):
            return True
        if sms_on:
            return self._unifonic_send_sms(phone, message)
        return False

    # ─── Convenience: resolve best phone from a res.partner ──────────
    @api.model
    def _partner_phone(self, partner):
        """Return mobile, then phone from a res.partner record."""
        return partner and (partner.mobile or partner.phone) or None
