# -*- coding: utf-8 -*-
"""إعدادات SADAD."""
from odoo import models, fields


class ResConfigSettingsSadad(models.TransientModel):
    _inherit = 'res.config.settings'

    sa_sadad_biller_code = fields.Char(
        string='رمز المُصدِر SADAD (4 أرقام)',
        config_parameter='sa_sadad.biller_code',
        default='9999',
        help='الرمز المعتمد من SAMA. للاختبار استخدم 9999.',
    )
    sa_sadad_expiry_days = fields.Integer(
        string='صلاحية الفاتورة (أيام)',
        config_parameter='sa_sadad.expiry_days',
        default=30,
    )
    sa_sadad_webhook_token = fields.Char(
        string='Webhook Token (للتحقق من callback من SADAD)',
        config_parameter='sa_sadad.webhook_token',
        default='change-me-in-production',
        help='الـ token الذي يجب أن تُرسله SADAD مع callback. أنشئ token قوي للإنتاج.',
    )
