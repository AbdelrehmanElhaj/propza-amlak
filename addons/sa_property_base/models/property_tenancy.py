# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta


class PropertyTenancy(models.Model):
    """Saudi-first tenancy model with a clean state machine.

    Workflow: draft -> confirm -> running -> closed/cancelled
    Workflow extensions (sa_cycle_state, ejar status, payment schedule, etc.)
    live in l10n_sa_ejar and sa_rental_cycle.
    """
    _name = 'property.tenancy'
    _description = 'عقد إيجار'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start_date desc, id desc'

    # ─── Identity ──────────────────────────────────────────────
    name = fields.Char(
        string='المرجع',
        required=True, copy=False, readonly=True, tracking=True,
        default=lambda s: _('جديد'),
    )

    # ─── Parties ───────────────────────────────────────────────
    property_id = fields.Many2one(
        'property.property', string='العقار',
        required=True, tracking=True, ondelete='restrict',
    )
    partner_id = fields.Many2one(
        'res.partner', string='المستأجر',
        required=True, tracking=True,
        domain="[('is_tenant','=',True)]",
    )
    owner_partner_id = fields.Many2one(
        'res.partner', string='المؤجر',
        related='property_id.owner_partner_id',
        store=True, readonly=True,
    )

    # ─── Dates & Duration ──────────────────────────────────────
    start_date = fields.Date(
        string='تاريخ البداية', required=True, tracking=True,
        default=fields.Date.context_today,
    )
    end_date = fields.Date(string='تاريخ النهاية', tracking=True, copy=False)
    duration = fields.Integer(string='المدة', default=12, tracking=True)
    interval_type = fields.Selection([
        ('months', 'أشهر'),
        ('years',  'سنوات'),
    ], string='وحدة المدة', default='months', required=True, tracking=True)

    @api.onchange('start_date', 'duration', 'interval_type')
    def _onchange_compute_end_date(self):
        for rec in self:
            if rec.start_date and rec.duration and rec.interval_type:
                if rec.interval_type == 'years':
                    rec.end_date = rec.start_date + relativedelta(years=rec.duration)
                else:
                    rec.end_date = rec.start_date + relativedelta(months=rec.duration)

    # ─── Money ─────────────────────────────────────────────────
    rent_amount = fields.Float(string='قيمة الإيجار', required=True, tracking=True)
    deposit_amount = fields.Float(string='التأمين', tracking=True)
    currency_id = fields.Many2one(
        'res.currency', string='العملة',
        default=lambda s: s.env.company.currency_id,
    )

    payment_method = fields.Selection([
        ('sadad',         'SADAD'),
        ('mada',          'مدى'),
        ('bank_transfer', 'تحويل بنكي'),
        ('cheque',        'شيك'),
        ('cash',          'نقداً'),
    ], string='طريقة الدفع', default='bank_transfer')

    # ─── Workflow ──────────────────────────────────────────────
    state = fields.Selection([
        ('draft',     'جديد'),
        ('confirm',   'مؤكد'),
        ('running',   'ساري'),
        ('closed',    'منتهي'),
        ('cancelled', 'ملغي'),
    ], string='الحالة', default='draft', required=True, tracking=True, copy=False)

    priority = fields.Selection([
        ('0', 'عادي'),
        ('1', 'مهم'),
        ('2', 'عاجل'),
    ], string='الأولوية', default='0')

    # ─── Sequencing ────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('جديد')) == _('جديد'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'property.tenancy'
                ) or _('جديد')
        return super().create(vals_list)

    # ─── State transitions ────────────────────────────────────
    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('يمكن تأكيد العقد فقط من حالة "جديد".'))
            if not rec.start_date or not rec.end_date:
                raise UserError(_('يجب تحديد تاريخ البداية والنهاية قبل التأكيد.'))
            rec.state = 'confirm'
        return True

    def action_start(self):
        for rec in self:
            if rec.state not in ('confirm', 'draft'):
                raise UserError(_('يمكن بدء العقد فقط من حالة "مؤكد".'))
            rec.state = 'running'
            if rec.property_id and rec.property_id.state == 'draft':
                rec.property_id.state = 'on_rent'
                rec.property_id.tenant_partner_id = rec.partner_id
        return True

    def action_close(self):
        for rec in self:
            rec.state = 'closed'
            if rec.property_id and rec.property_id.state == 'on_rent':
                rec.property_id.state = 'draft'
                rec.property_id.tenant_partner_id = False
        return True

    def action_cancel(self):
        for rec in self:
            rec.state = 'cancelled'
            if rec.property_id and rec.property_id.state == 'on_rent':
                rec.property_id.state = 'draft'
                rec.property_id.tenant_partner_id = False
        return True

    def action_set_to_draft(self):
        for rec in self:
            rec.state = 'draft'
        return True

    # ─── Validation ────────────────────────────────────────────
    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.end_date < rec.start_date:
                raise ValidationError(_('تاريخ النهاية يجب أن يكون بعد تاريخ البداية.'))
