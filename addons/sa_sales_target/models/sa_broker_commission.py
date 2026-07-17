# -*- coding: utf-8 -*-
"""تمديد عقد عمولة الوسيط لربطه بمندوب مبيعات (مستخدم) لأغراض قياس الأهداف.

لا يعدّل هذا الملف أي شيء في addons/sa_broker_commission — فقط يضيف حقلاً
جديداً عبر _inherit، حسب سياسة عدم تعديل الموديولات الأخرى في مكانها.
"""
from odoo import models, fields, api


class SaBrokerCommission(models.Model):
    _inherit = 'sa.broker.commission'

    salesperson_user_id = fields.Many2one(
        'res.users', string='مندوب المبيعات', tracking=True,
        help='المستخدم المسؤول عن هذه العمولة لأغراض قياس الأهداف. '
             'يُقترح تلقائياً من المستخدم المرتبط بجهة اتصال الوسيط، '
             'ويمكن تعديله يدوياً (خصوصاً للوسطاء الخارجيين بلا حساب دخول).',
    )

    @api.onchange('broker_partner_id')
    def _onchange_broker_partner_suggest_user(self):
        for rec in self:
            if rec.broker_partner_id.user_ids:
                rec.salesperson_user_id = rec.broker_partner_id.user_ids[:1]
