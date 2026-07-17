# -*- coding: utf-8 -*-
"""هدف مبيعات (عمولات) — فردي أو على مستوى فريق، لفترة شهرية/ربع سنوية/سنوية.

يُحتسب "المحقَّق" من مجموع دفعات عمولات الوسطاء (sa.broker.commission.line)
التي حالتها 'paid' وتاريخ استحقاقها ضمن فترة الهدف، والمرتبطة بمندوب
مبيعات (sa.broker.commission.salesperson_user_id) يطابق نطاق الهدف.
"""
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SaSalesTarget(models.Model):
    _name = 'sa.sales.target'
    _description = 'هدف مبيعات (عمولات)'
    _inherit = ['mail.thread']
    _order = 'date_from desc'

    name = fields.Char(compute='_compute_name', store=True)
    scope = fields.Selection([
        ('user', 'فردي'),
        ('team', 'فريق'),
    ], string='النطاق', required=True, default='user', tracking=True)
    user_id = fields.Many2one('res.users', string='الموظف', tracking=True)
    team_id = fields.Many2one('sa.sales.team', string='الفريق', tracking=True)
    period_type = fields.Selection([
        ('month', 'شهري'),
        ('quarter', 'ربع سنوي'),
        ('year', 'سنوي'),
    ], string='نوع الفترة', required=True, default='month', tracking=True)
    date_from = fields.Date(
        string='من تاريخ', required=True, tracking=True,
        default=lambda s: date.today().replace(day=1),
    )
    date_to = fields.Date(string='إلى تاريخ', required=True, tracking=True)
    target_amount = fields.Float(string='المبلغ المستهدف (ريال)', required=True, tracking=True)
    achieved_amount = fields.Float(compute='_compute_achievement', string='المحقَّق (ريال)')
    achievement_pct = fields.Float(compute='_compute_achievement', string='نسبة الإنجاز (٪)')
    company_id = fields.Many2one('res.company', default=lambda s: s.env.company)

    _sql_constraints = [
        ('check_dates', 'CHECK(date_to >= date_from)',
         'تاريخ النهاية يجب أن يكون بعد أو يساوي تاريخ البداية.'),
        ('check_amount_positive', 'CHECK(target_amount > 0)',
         'قيمة الهدف يجب أن تكون أكبر من صفر.'),
    ]

    @api.depends('scope', 'user_id', 'team_id')
    def _compute_name(self):
        for rec in self:
            rec.name = rec.user_id.name if rec.scope == 'user' else (rec.team_id.name or '')

    @api.constrains('scope', 'user_id', 'team_id')
    def _check_scope_consistency(self):
        for rec in self:
            if rec.scope == 'user' and not rec.user_id:
                raise ValidationError(_('يجب تحديد الموظف عند اختيار النطاق "فردي".'))
            if rec.scope == 'team' and not rec.team_id:
                raise ValidationError(_('يجب تحديد الفريق عند اختيار النطاق "فريق".'))

    @api.onchange('period_type', 'date_from')
    def _onchange_period_type(self):
        for rec in self:
            if not rec.date_from:
                continue
            if rec.period_type == 'month':
                rec.date_to = rec.date_from + relativedelta(months=1, days=-1)
            elif rec.period_type == 'quarter':
                rec.date_to = rec.date_from + relativedelta(months=3, days=-1)
            elif rec.period_type == 'year':
                rec.date_to = rec.date_from + relativedelta(years=1, days=-1)

    def _get_commission_line_domain(self):
        self.ensure_one()
        domain = [
            ('state', '=', 'paid'),
            ('due_date', '>=', self.date_from),
            ('due_date', '<=', self.date_to),
        ]
        if self.scope == 'user':
            domain.append(('commission_id.salesperson_user_id', '=', self.user_id.id))
        else:
            domain.append(('commission_id.salesperson_user_id', 'in', self.team_id.member_ids.ids))
        return domain

    @api.depends('scope', 'user_id', 'team_id', 'date_from', 'date_to', 'target_amount')
    def _compute_achievement(self):
        Line = self.env['sa.broker.commission.line']
        for rec in self:
            if not rec.date_from or not rec.date_to:
                rec.achieved_amount = 0.0
                rec.achievement_pct = 0.0
                continue
            if rec.scope == 'user' and not rec.user_id:
                rec.achieved_amount = 0.0
                rec.achievement_pct = 0.0
                continue
            if rec.scope == 'team' and not rec.team_id:
                rec.achieved_amount = 0.0
                rec.achievement_pct = 0.0
                continue
            achieved = sum(Line.search(rec._get_commission_line_domain()).mapped('amount'))
            rec.achieved_amount = achieved
            rec.achievement_pct = round(achieved / rec.target_amount * 100.0, 1) if rec.target_amount else 0.0
