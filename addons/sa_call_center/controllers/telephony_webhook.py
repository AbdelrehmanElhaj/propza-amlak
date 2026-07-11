# -*- coding: utf-8 -*-
"""Webhook لاستقبال أحداث المكالمات من نظام PBX/الاتصالات (Asterisk أو أي مزود آخر).

Endpoint:
    POST /callcenter/webhook/event
    Headers:
        X-CallCenter-Token: <configured token>
    Body (JSON):
        {
            "event": "ringing" | "answered" | "ended" | "voicemail",
            "call_uid": "unique-call-id",
            "direction": "in" | "out",
            "from_number": "0501234567",
            "to_number": "8001234567",
            "queue_code": "sales",           # اختياري
            "agent_extension": "101",        # اختياري
            "recording_url": "https://...",  # مع حدث ended فقط
        }

ملاحظة: هذا الإصدار (المرحلة 1) لا يبث Screen Pop لحظي؛ الوكيل يفتح سجل
المكالمة يدوياً من القائمة. البث اللحظي عبر bus.bus مخطط للمرحلة 2.
"""
import logging
from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


class CallCenterWebhookController(http.Controller):

    @http.route('/callcenter/webhook/event', type='json', auth='none',
                methods=['POST'], csrf=False)
    def call_event(self, **kwargs):
        token = request.httprequest.headers.get('X-CallCenter-Token', '')
        expected = request.env['ir.config_parameter'].sudo().get_param(
            'sa_call_center.webhook_token', 'change-me-in-production'
        )
        if token != expected:
            _logger.warning('Call center webhook called with invalid token')
            return {'status': 'error', 'message': 'invalid token'}

        try:
            data = request.get_json_data() or {}
        except Exception:
            data = {}

        event = data.get('event')
        call_uid = data.get('call_uid')
        if not event or not call_uid:
            return {'status': 'error', 'message': 'missing event/call_uid'}

        Call = request.env['sa.call.center.call'].sudo()
        call = Call.search([('call_uid', '=', call_uid)], limit=1)

        if event == 'ringing':
            if call:
                return {'status': 'already_exists', 'call': call.name}

            queue = request.env['sa.call.center.queue'].sudo()
            if data.get('queue_code'):
                queue = queue.search([('code', '=', data['queue_code'])], limit=1)
            else:
                queue = queue.browse()

            agent = request.env['res.users'].sudo()
            if data.get('agent_extension'):
                agent = agent.search([('sip_extension', '=', data['agent_extension'])], limit=1)
            else:
                agent = agent.browse()

            call = Call.create({
                'call_uid': call_uid,
                'direction': data.get('direction', 'in'),
                'from_number': data.get('from_number'),
                'to_number': data.get('to_number'),
                'queue_id': queue.id if queue else False,
                'agent_id': agent.id if agent else False,
                'state': 'ringing',
                'start_datetime': fields.Datetime.now(),
            })
            return {'status': 'created', 'call': call.name}

        if not call:
            return {'status': 'error', 'message': 'call_uid not found'}

        if event == 'answered':
            call.write({'state': 'answered', 'answer_datetime': fields.Datetime.now()})
        elif event == 'ended':
            vals = {'state': 'ended', 'end_datetime': fields.Datetime.now()}
            if data.get('recording_url'):
                vals['recording_url'] = data['recording_url']
            if not call.answer_datetime:
                vals['state'] = 'missed'
            call.write(vals)
        elif event == 'voicemail':
            call.write({'state': 'voicemail', 'end_datetime': fields.Datetime.now()})
        else:
            return {'status': 'error', 'message': 'unknown event'}

        return {'status': 'updated', 'call': call.name, 'state': call.state}
