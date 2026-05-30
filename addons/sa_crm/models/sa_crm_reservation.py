# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaCrmReservation(models.Model):
    _name = 'sa.crm.reservation'
    _description = 'حجز وحدة'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc'

    name = fields.Char(
        string='رقم الحجز',
        readonly=True, copy=False,
        default=lambda s: _('جديد'),
    )
    lead_id = fields.Many2one(
        'sa.crm.lead', string='الطلب',
        required=True, ondelete='restrict', tracking=True,
    )
    partner_id = fields.Many2one(
        'res.partner', string='العميل',
        related='lead_id.partner_id', store=True,
    )
    property_id = fields.Many2one(
        'property.property', string='العقار',
        required=True, tracking=True,
    )
    user_id = fields.Many2one(
        'res.users', string='الموظف المسؤول',
        default=lambda s: s.env.user, tracking=True,
    )

    state = fields.Selection([
        ('draft',     'مسودة'),
        ('active',    'محجوز'),
        ('expired',   'منتهي الصلاحية'),
        ('cancelled', 'ملغى'),
        ('converted', 'تحوّل لصفقة'),
    ], string='الحالة', default='draft', tracking=True, copy=False)

    date_start = fields.Date(
        string='تاريخ بدء الحجز',
        default=fields.Date.today, required=True,
    )
    date_end = fields.Date(
        string='تاريخ انتهاء الحجز',
        required=True,
    )
    duration_days = fields.Integer(
        string='مدة الحجز (أيام)',
        compute='_compute_duration', store=True,
    )
    days_remaining = fields.Integer(
        string='الأيام المتبقية',
        compute='_compute_days_remaining',
    )

    deposit_amount = fields.Float(string='مبلغ الحجز', tracking=True)
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda s: s.env.company.currency_id,
    )
    deposit_paid = fields.Boolean(string='تم سداد مبلغ الحجز', tracking=True)

    cancel_reason = fields.Text(string='سبب الإلغاء')
    notes = fields.Text(string='ملاحظات')

    # ─── Sequencing ────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('جديد')) == _('جديد'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'sa.crm.reservation'
                ) or _('جديد')
        return super().create(vals_list)

    # ─── Computed ──────────────────────────────────────────────
    @api.depends('date_start', 'date_end')
    def _compute_duration(self):
        for rec in self:
            if rec.date_start and rec.date_end:
                rec.duration_days = (rec.date_end - rec.date_start).days
            else:
                rec.duration_days = 0

    @api.depends('date_end', 'state')
    def _compute_days_remaining(self):
        today = fields.Date.today()
        for rec in self:
            if rec.state == 'active' and rec.date_end:
                rec.days_remaining = (rec.date_end - today).days
            else:
                rec.days_remaining = 0

    # ─── Actions ───────────────────────────────────────────────
    def action_activate(self):
        for rec in self:
            conflict = self.search([
                ('property_id', '=', rec.property_id.id),
                ('state', '=', 'active'),
                ('id', '!=', rec.id),
            ], limit=1)
            if conflict:
                raise UserError(
                    _('العقار "%s" محجوز بالفعل للعميل %s حتى %s.') % (
                        rec.property_id.name,
                        conflict.partner_id.name,
                        conflict.date_end,
                    )
                )
            rec.state = 'active'
            rec.lead_id.lead_category = 'opportunity'
            rec.property_id._compute_is_reserved()

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        self.mapped('property_id')._compute_is_reserved()

    def action_convert_to_deal(self):
        for rec in self:
            rec.state = 'converted'
            rec.lead_id.action_mark_won()
        self.mapped('property_id')._compute_is_reserved()

    @api.model
    def _cron_expire_reservations(self):
        today = fields.Date.today()
        expired = self.search([
            ('state', '=', 'active'),
            ('date_end', '<', today),
        ])
        if expired:
            expired.write({'state': 'expired'})
            expired.mapped('property_id')._compute_is_reserved()


class PropertyPropertyReservation(models.Model):
    _inherit = 'property.property'

    reservation_ids = fields.One2many(
        'sa.crm.reservation', 'property_id', string='الحجوزات',
    )
    is_reserved = fields.Boolean(
        string='محجوز',
        compute='_compute_is_reserved', store=True,
    )
    active_reservation_id = fields.Many2one(
        'sa.crm.reservation', string='الحجز النشط',
        compute='_compute_is_reserved', store=True,
    )

    @api.depends('reservation_ids.state')
    def _compute_is_reserved(self):
        for rec in self:
            active = rec.reservation_ids.filtered(lambda r: r.state == 'active')
            rec.is_reserved = bool(active)
            rec.active_reservation_id = active[:1]
