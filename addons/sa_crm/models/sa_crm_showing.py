# -*- coding: utf-8 -*-
from odoo import models, fields


class SaCrmShowing(models.Model):
    _name = 'sa.crm.showing'
    _description = 'جولة ميدانية'
    _inherit = ['mail.thread']
    _order = 'scheduled_date desc'

    lead_id = fields.Many2one(
        'sa.crm.lead', string='الطلب',
        required=True, ondelete='cascade',
    )
    property_id = fields.Many2one(
        'property.property', string='العقار',
        required=True, tracking=True,
    )
    scheduled_date = fields.Datetime(
        string='تاريخ الجولة',
        required=True, tracking=True,
        default=fields.Datetime.now,
    )
    user_id = fields.Many2one(
        'res.users', string='الموظف',
        default=lambda s: s.env.user,
    )
    outcome = fields.Selection([
        ('scheduled', 'مجدولة'),
        ('done',      'تمت'),
        ('cancelled', 'ملغاة'),
        ('no_show',   'لم يحضر'),
    ], string='النتيجة', default='scheduled', tracking=True)

    # ─── Client Feedback ───────────────────────────────────────
    interest_level = fields.Selection([
        ('very_interested', 'مهتم جداً'),
        ('interested',      'مهتم'),
        ('neutral',         'محايد'),
        ('not_interested',  'غير مهتم'),
    ], string='مستوى الاهتمام', tracking=True)
    client_feedback = fields.Text(string='ملاحظات العميل')

    notes = fields.Text(string='ملاحظات الموظف')
