# -*- coding: utf-8 -*-
"""يولّد Twilio Access Token لموظف مركز الاتصال الحالي ليستخدمه سمّاعة
المتصفح (static/src/js/softphone.js) عند تسجيل نفسه كـ Twilio Client.
"""
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class CallCenterTokenController(http.Controller):

    @http.route('/callcenter/twilio/token', type='json', auth='user', methods=['POST'])
    def twilio_token(self, **kwargs):
        user = request.env.user
        if not user.is_call_center_agent:
            return {'error': 'not_an_agent'}

        Twilio = request.env['sa.telephony.twilio.service'].sudo()
        identity = Twilio._agent_identity(user)
        token = Twilio._generate_access_token(identity)
        if not token:
            _logger.warning('sa_call_center: طلب Twilio Access Token فشل — بيانات API Key غير مكتملة')
            return {'error': 'not_configured'}

        return {'token': token, 'identity': identity}
