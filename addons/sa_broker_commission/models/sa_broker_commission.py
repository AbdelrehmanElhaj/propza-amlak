# -*- coding: utf-8 -*-
"""عقد عمولة وسيط عقاري — يربط وسيطاً بعقد إيجار محدد.

الأنماط المدعومة:
    * percentage: نسبة من الإيجار السنوي (مثلاً 5%)
    * fixed: مبلغ ثابت (مثلاً 1500 ريال لكل عقد)

طرق الدفع:
    * on_signup: مرة واحدة عند توقيع العقد
    * monthly: دفعة شهرية صغيرة
    * split: دفعتان (50% عند التوقيع + 50% بعد 6 أشهر)
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta
from datetime import timedelta


class SaBrokerCommission(models.Model):
    _name = 'sa.broker.commission'
    _description = 'عمولة وسيط عقاري'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_signed desc, id desc'

    # ─── Identity ─────────────────────────────────────────────────
    name = fields.Char(
        string='المرجع', required=True, copy=False,
        readonly=True, default=lambda s: _('جديد'), tracking=True,
    )

    # ─── Parties ──────────────────────────────────────────────────
    broker_partner_id = fields.Many2one(
        'res.partner', string='الوسيط',
        required=True, tracking=True,
        domain="[('is_broker','=',True)]",
    )
    tenancy_id = fields.Many2one(
        'property.tenancy', string='عقد الإيجار',
        required=True, tracking=True, ondelete='restrict',
    )
    property_id = fields.Many2one(
        'property.property', string='العقار',
        related='tenancy_id.property_id', store=True, readonly=True,
    )
    tenant_partner_id = fields.Many2one(
        'res.partner', string='المستأجر',
        related='tenancy_id.partner_id', store=True, readonly=True,
    )
    owner_partner_id = fields.Many2one(
        'res.partner', string='المالك',
        related='tenancy_id.owner_partner_id', store=True, readonly=True,
    )
    annual_rent = fields.Float(
        string='الإيجار السنوي (ريال)',
        compute='_compute_annual_rent', store=True,
    )

    @api.depends('tenancy_id', 'tenancy_id.rent_amount',
                 'tenancy_id.duration', 'tenancy_id.interval_type')
    def _compute_annual_rent(self):
        for rec in self:
            if not rec.tenancy_id:
                rec.annual_rent = 0.0
                continue
            t = rec.tenancy_id
            # Convert to monthly base then × 12
            monthly = t.rent_amount or 0.0
            rec.annual_rent = monthly * 12

    # ─── Commission spec ──────────────────────────────────────────
    commission_type = fields.Selection([
        ('percentage', 'نسبة من الإيجار السنوي'),
        ('fixed',      'مبلغ ثابت'),
    ], string='نوع العمولة', required=True, default='percentage', tracking=True)

    commission_rate = fields.Float(
        string='النسبة (٪)', default=5.0, tracking=True,
        help='النسبة المطبَّقة على الإيجار السنوي. مثال: 5%',
    )
    fixed_amount = fields.Float(
        string='المبلغ الثابت (ريال)', tracking=True,
    )
    commission_amount = fields.Float(
        string='قيمة العمولة (ريال)',
        compute='_compute_commission_amount', store=True, tracking=True,
    )

    @api.depends('commission_type', 'commission_rate', 'fixed_amount', 'annual_rent')
    def _compute_commission_amount(self):
        for rec in self:
            if rec.commission_type == 'percentage':
                rec.commission_amount = (rec.annual_rent or 0.0) * (rec.commission_rate or 0.0) / 100.0
            else:
                rec.commission_amount = rec.fixed_amount or 0.0

    # ─── Payment schedule ─────────────────────────────────────────
    payment_schedule = fields.Selection([
        ('on_signup', 'مرة واحدة عند التوقيع'),
        ('monthly',   'دفعة شهرية'),
        ('split',     '50/50 (توقيع + 6 أشهر)'),
    ], string='طريقة الدفع', required=True, default='on_signup', tracking=True)

    date_signed = fields.Date(
        string='تاريخ التوقيع', required=True, tracking=True,
        default=fields.Date.context_today,
    )

    line_ids = fields.One2many(
        'sa.broker.commission.line', 'commission_id',
        string='جدول الدفعات', copy=True,
    )
    paid_amount = fields.Float(
        string='المُسدَّد (ريال)',
        compute='_compute_payment_stats', store=True,
    )
    remaining_amount = fields.Float(
        string='المتبقي (ريال)',
        compute='_compute_payment_stats', store=True,
    )

    @api.depends('line_ids.state', 'line_ids.amount', 'commission_amount')
    def _compute_payment_stats(self):
        for rec in self:
            paid = sum(rec.line_ids.filtered(
                lambda l: l.state == 'paid'
            ).mapped('amount'))
            rec.paid_amount = paid
            rec.remaining_amount = (rec.commission_amount or 0.0) - paid

    # ─── State machine ───────────────────────────────────────────
    state = fields.Selection([
        ('draft',     'مسودة'),
        ('confirmed', 'مؤكد'),
        ('partial',   'مدفوع جزئياً'),
        ('paid',      'مدفوع كاملاً'),
        ('cancelled', 'ملغي'),
    ], string='الحالة', default='draft', required=True, tracking=True, copy=False)

    notes = fields.Text(string='ملاحظات')

    # ─── Sequencing ───────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('جديد')) == _('جديد'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'sa.broker.commission'
                ) or _('جديد')
        return super().create(vals_list)

    # ─── State transitions ───────────────────────────────────────
    def _generate_lines(self):
        """يولّد جدول دفعات بناءً على payment_schedule."""
        self.ensure_one()
        # Clear unpaid lines
        self.line_ids.filtered(lambda l: l.state != 'paid').unlink()
        Line = self.env['sa.broker.commission.line']
        amount = self.commission_amount or 0.0
        if amount <= 0:
            return False

        if self.payment_schedule == 'on_signup':
            Line.create({
                'commission_id': self.id,
                'due_date': self.date_signed,
                'amount': amount,
                'description': _('دفعة كاملة عند التوقيع'),
            })
        elif self.payment_schedule == 'split':
            half = amount / 2
            Line.create([
                {
                    'commission_id': self.id,
                    'due_date': self.date_signed,
                    'amount': half,
                    'description': _('الدفعة الأولى عند التوقيع (50%)'),
                },
                {
                    'commission_id': self.id,
                    'due_date': self.date_signed + relativedelta(months=6),
                    'amount': half,
                    'description': _('الدفعة الثانية بعد 6 أشهر (50%)'),
                },
            ])
        elif self.payment_schedule == 'monthly':
            duration_months = self.tenancy_id.duration or 12
            if self.tenancy_id.interval_type == 'years':
                duration_months *= 12
            per_month = amount / duration_months
            for i in range(duration_months):
                Line.create({
                    'commission_id': self.id,
                    'due_date': self.date_signed + relativedelta(months=i),
                    'amount': per_month,
                    'description': _('الشهر %d') % (i + 1),
                })
        return True

    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('يمكن تأكيد العقد فقط من حالة "مسودة"'))
            if rec.commission_amount <= 0:
                raise UserError(_('قيمة العمولة غير صحيحة'))
            rec._generate_lines()
            rec.state = 'confirmed'
        return True

    def action_cancel(self):
        for rec in self:
            if rec.line_ids.filtered(lambda l: l.state == 'paid'):
                raise UserError(_('لا يمكن إلغاء عقد به دفعات مُسدَّدة. الرجاء عكس الدفعات أولاً.'))
            rec.state = 'cancelled'
        return True

    def action_set_to_draft(self):
        for rec in self:
            if rec.line_ids.filtered(lambda l: l.state == 'paid'):
                raise UserError(_('لا يمكن العودة لـ مسودة بعد دفع جزء من العمولة'))
            rec.state = 'draft'
        return True

    # ─── Update overall state when lines change ──────────────────
    @api.depends('line_ids.state', 'commission_amount', 'paid_amount')
    def _compute_overall_state(self):
        # This is handled in line.write() which calls back here
        pass

    def _refresh_state_from_lines(self):
        for rec in self:
            if rec.state in ('draft', 'cancelled'):
                continue
            if rec.line_ids and all(l.state == 'paid' for l in rec.line_ids):
                rec.state = 'paid'
            elif any(l.state == 'paid' for l in rec.line_ids):
                rec.state = 'partial'
            else:
                rec.state = 'confirmed'

    # ─── Drill-down ──────────────────────────────────────────────
    def action_view_lines(self):
        self.ensure_one()
        return {
            'name': _('دفعات العمولة'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.broker.commission.line',
            'view_mode': 'tree,form',
            'domain': [('commission_id', '=', self.id)],
        }
