# -*- coding: utf-8 -*-
"""Webhook endpoint محاكي لـ SADAD.

In production: SADAD platform calls this URL when a customer pays a bill.
For simulation: any caller with the right token can mark a bill as paid.

Endpoint:
    POST /sadad/webhook
    Headers:
        X-Sadad-Token: <configured token>
    Body (JSON):
        {
            "bill_number": "999900001000000123",
            "amount": 5000.0,
            "payment_ref": "BANK-REF-123",
            "channel": "ATM" | "Online" | "App" | "Branch"
        }

For convenience, also exposes a GET endpoint /sadad/pay/<bill_number>
that simulates a customer scanning the QR and paying online (no token required —
this is for the SIMULATION button in the UI).
"""
import json
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class SadadWebhookController(http.Controller):

    @http.route('/sadad/webhook', type='json', auth='none',
                methods=['POST'], csrf=False)
    def sadad_webhook(self, **kwargs):
        """يستقبل callbacks من SADAD (محاكاة) أو من نظام بنكي حقيقي."""
        # Read token from header
        token = request.httprequest.headers.get('X-Sadad-Token', '')
        expected = request.env['ir.config_parameter'].sudo().get_param(
            'sa_sadad.webhook_token', 'change-me-in-production'
        )
        if token != expected:
            _logger.warning('SADAD webhook called with invalid token')
            return {'status': 'error', 'message': 'invalid token'}

        # Read body
        try:
            data = request.get_json_data() or {}
        except Exception:
            data = {}

        bill_number = data.get('bill_number')
        amount = data.get('amount')
        payment_ref = data.get('payment_ref', '')
        channel = data.get('channel', 'Webhook')

        if not bill_number:
            return {'status': 'error', 'message': 'missing bill_number'}

        invoice = request.env['sa.sadad.invoice'].sudo().search([
            ('bill_number', '=', bill_number),
        ], limit=1)
        if not invoice:
            return {'status': 'error', 'message': 'bill not found'}
        if invoice.state == 'paid':
            return {'status': 'already_paid', 'invoice': invoice.name}
        if invoice.state == 'cancelled':
            return {'status': 'error', 'message': 'invoice cancelled'}

        # Verify amount (within 1 SAR tolerance for rounding)
        if amount and abs(float(amount) - invoice.amount) > 1.0:
            _logger.warning(
                'SADAD webhook amount mismatch: bill %s expected %s got %s',
                bill_number, invoice.amount, amount
            )

        invoice._mark_paid(
            payment_ref=payment_ref,
            channel=channel,
        )
        _logger.info('SADAD webhook: bill %s paid via %s, ref=%s',
                     bill_number, channel, payment_ref)
        return {
            'status': 'success',
            'invoice': invoice.name,
            'amount': invoice.amount,
        }

    @http.route('/sadad/pay/<string:bill_number>', type='http',
                auth='public', methods=['GET'], csrf=False)
    def sadad_pay_simulator(self, bill_number, **kwargs):
        """صفحة محاكاة للدفع — تُحاكي تجربة العميل عند مسح QR."""
        invoice = request.env['sa.sadad.invoice'].sudo().search([
            ('bill_number', '=', bill_number),
        ], limit=1)
        if not invoice:
            return request.render('sa_sadad.sadad_pay_not_found', {})
        return request.render('sa_sadad.sadad_pay_simulator', {
            'invoice': invoice,
        })

    @http.route('/sadad/pay/<string:bill_number>/confirm', type='http',
                auth='public', methods=['POST'], csrf=True)
    def sadad_pay_confirm(self, bill_number, **post):
        """يتم استدعاؤه عند ضغط "تأكيد الدفع" في صفحة المحاكاة."""
        invoice = request.env['sa.sadad.invoice'].sudo().search([
            ('bill_number', '=', bill_number),
        ], limit=1)
        if not invoice or invoice.state != 'pending':
            return request.redirect('/sadad/pay/%s' % bill_number)
        invoice._mark_paid(
            payment_ref='SIM-WEB-%s' % invoice.id,
            channel='Web Simulator',
        )
        return request.render('sa_sadad.sadad_pay_success', {
            'invoice': invoice,
        })
