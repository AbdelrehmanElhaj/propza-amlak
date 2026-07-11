# -*- coding: utf-8 -*-
"""صفحة إعدادات مركز الاتصال — مزوّد الاتصالات + بيانات اتصال Asterisk ARI + Webhook token."""
from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sa_telephony_provider = fields.Selection(
        selection=[
            ('disabled', 'معطّل'),
            ('asterisk', 'Asterisk (ARI)'),
            ('twilio', 'Twilio'),
        ],
        string='مزوّد الاتصالات',
        config_parameter='sa_call_center.telephony_provider',
        default='disabled',
    )

    sa_asterisk_ari_host = fields.Char(
        string='Asterisk ARI Host',
        config_parameter='sa_call_center.asterisk_ari_host',
    )
    sa_asterisk_ari_port = fields.Char(
        string='Asterisk ARI Port',
        config_parameter='sa_call_center.asterisk_ari_port',
        default='8088',
    )
    sa_asterisk_ari_user = fields.Char(
        string='Asterisk ARI User',
        config_parameter='sa_call_center.asterisk_ari_user',
    )
    sa_asterisk_ari_password = fields.Char(
        string='Asterisk ARI Password',
        config_parameter='sa_call_center.asterisk_ari_password',
    )
    sa_call_center_webhook_token = fields.Char(
        string='Webhook Token',
        config_parameter='sa_call_center.webhook_token',
        help='القيمة المرسلة في ترويسة X-CallCenter-Token من نظام PBX/الاتصالات',
    )

    # ─── Twilio ────────────────────────────────────────────────────
    sa_twilio_account_sid = fields.Char(
        string='Twilio Account SID',
        config_parameter='sa_call_center.twilio_account_sid',
    )
    sa_twilio_auth_token = fields.Char(
        string='Twilio Auth Token',
        config_parameter='sa_call_center.twilio_auth_token',
    )
    sa_twilio_phone_number = fields.Char(
        string='رقم Twilio',
        config_parameter='sa_call_center.twilio_phone_number',
        help='الرقم المسجَّل في Twilio بصيغة E.164، مثال: +19999999999',
    )
    sa_twilio_forward_number = fields.Char(
        string='رقم التحويل الثابت',
        config_parameter='sa_call_center.twilio_forward_number',
        help='كل مكالمة واردة على رقم Twilio تُحوَّل فوراً لهذا الرقم (E.164)',
    )
    sa_twilio_public_base_url = fields.Char(
        string='Public Base URL',
        config_parameter='sa_call_center.twilio_public_base_url',
        help='الرابط العام لهذا الـ Odoo كما يراه Twilio، مثال: https://amlak.hdrelhaj.com '
             '— يُستخدم للتحقق من توقيع الطلبات القادمة من Twilio',
    )
    sa_twilio_api_key_sid = fields.Char(
        string='Twilio API Key SID',
        config_parameter='sa_call_center.twilio_api_key_sid',
        help='مختلف عن Account SID — يُنشأ من Console → Account → API keys & tokens. '
             'يُستخدم لتوليد Access Token للرد على المكالمات من داخل المتصفح',
    )
    sa_twilio_api_key_secret = fields.Char(
        string='Twilio API Key Secret',
        config_parameter='sa_call_center.twilio_api_key_secret',
    )
    sa_twilio_twiml_app_sid = fields.Char(
        string='Twilio TwiML App SID',
        config_parameter='sa_call_center.twilio_twiml_app_sid',
        help='يُنشأ من Console → Voice → TwiML → TwiML Apps، مع ضبط '
             'Voice Request URL على: <public base url>/callcenter/webhook/twilio/outbound-voice '
             '(HTTP POST). مطلوب لتفعيل الاتصال الصادر من سمّاعة المتصفح.',
    )
