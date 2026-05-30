# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class SaCrmLead(models.Model):
    _name = 'sa.crm.lead'
    _description = 'طلب CRM'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'stage_id, priority desc, id desc'

    # ─── Identity ──────────────────────────────────────────────
    name = fields.Char(
        string='المرجع',
        readonly=True, copy=False,
        default=lambda s: _('جديد'),
    )
    active = fields.Boolean(default=True)

    # ─── Customer ──────────────────────────────────────────────
    partner_id = fields.Many2one(
        'res.partner', string='العميل',
        required=True, tracking=True,
    )
    phone = fields.Char(
        string='الهاتف',
        related='partner_id.phone', store=True,
    )
    email = fields.Char(
        string='البريد الإلكتروني',
        related='partner_id.email', store=True,
    )

    # ─── Classification ────────────────────────────────────────
    lead_type = fields.Selection([
        ('rent', 'بحث عن إيجار'),
        ('buy',  'بحث عن شراء'),
    ], string='نوع الطلب', required=True, default='rent', tracking=True)

    property_type = fields.Selection([
        ('residential', 'سكني'),
        ('commercial',  'تجاري'),
        ('industrial',  'صناعي'),
        ('land',        'أرض'),
    ], string='نوع العقار', default='residential', tracking=True)

    # ─── Budget ────────────────────────────────────────────────
    budget_min = fields.Float(string='الميزانية الدنيا')
    budget_max = fields.Float(string='الميزانية القصوى')
    currency_id = fields.Many2one(
        'res.currency', string='العملة',
        default=lambda s: s.env.company.currency_id,
    )

    # ─── Location ──────────────────────────────────────────────
    preferred_region_id = fields.Many2one(
        'sa.region', string='المنطقة المفضلة',
    )

    # ─── Pipeline ──────────────────────────────────────────────
    stage_id = fields.Many2one(
        'sa.crm.stage', string='المرحلة',
        required=True, ondelete='restrict', tracking=True,
        default=lambda s: s._default_stage_id(),
    )
    probability = fields.Float(
        string='الاحتمال',
        related='stage_id.probability', store=True,
    )
    kanban_state = fields.Selection([
        ('normal',  'في التقدم'),
        ('done',    'جاهز للمرحلة التالية'),
        ('blocked', 'محجوب'),
    ], string='حالة كانبان', default='normal')

    priority = fields.Selection([
        ('0', 'عادي'),
        ('1', 'مهم'),
        ('2', 'عاجل'),
    ], string='الأولوية', default='0')

    state = fields.Selection([
        ('open', 'مفتوح'),
        ('won',  'فاز'),
        ('lost', 'خسر'),
    ], string='الحالة', default='open', tracking=True, copy=False)

    lost_reason = fields.Char(string='سبب الخسارة')

    # ─── Assignment ────────────────────────────────────────────
    user_id = fields.Many2one(
        'res.users', string='الموظف المسؤول',
        default=lambda s: s.env.user, tracking=True,
    )
    source = fields.Selection([
        ('walkin',   'زيارة مباشرة'),
        ('phone',    'اتصال هاتفي'),
        ('website',  'الموقع الإلكتروني'),
        ('referral', 'إحالة'),
        ('social',   'وسائل التواصل'),
        ('portal',   'البوابة'),
    ], string='المصدر', default='phone')

    # ─── Property ──────────────────────────────────────────────
    property_id = fields.Many2one(
        'property.property', string='العقار المقترح',
    )
    expected_commission = fields.Float(
        string='العمولة المتوقعة', tracking=True,
    )

    # ─── Dates & Notes ─────────────────────────────────────────
    date_deadline = fields.Date(string='الموعد النهائي')
    description = fields.Text(string='ملاحظات')

    # ─── Showings ──────────────────────────────────────────────
    showing_ids = fields.One2many(
        'sa.crm.showing', 'lead_id', string='الجولات الميدانية',
    )
    showing_count = fields.Integer(
        string='عدد الجولات', compute='_compute_showing_count',
    )

    # ─── Helpers ───────────────────────────────────────────────
    @api.model
    def _default_stage_id(self):
        return self.env['sa.crm.stage'].search([], order='sequence asc', limit=1)

    @api.depends('showing_ids')
    def _compute_showing_count(self):
        for rec in self:
            rec.showing_count = len(rec.showing_ids)

    # ─── Sequencing ────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('جديد')) == _('جديد'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'sa.crm.lead'
                ) or _('جديد')
        return super().create(vals_list)

    # ─── Actions ───────────────────────────────────────────────
    def action_mark_won(self):
        won_stage = self.env['sa.crm.stage'].search(
            [('is_won', '=', True)], order='sequence asc', limit=1
        )
        for rec in self:
            rec.state = 'won'
            if won_stage:
                rec.stage_id = won_stage

    def action_mark_lost(self):
        for rec in self:
            rec.state = 'lost'
            rec.active = False

    def action_reopen(self):
        for rec in self:
            rec.state = 'open'
            rec.active = True

    def action_view_showings(self):
        self.ensure_one()
        return {
            'name': _('الجولات الميدانية'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.crm.showing',
            'view_mode': 'list,form',
            'domain': [('lead_id', '=', self.id)],
            'context': {'default_lead_id': self.id},
        }
