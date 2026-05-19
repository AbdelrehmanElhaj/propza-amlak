# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class PropertyProperty(models.Model):
    """Saudi-first property model.

    Replaces the third-party dev_property_management.property.property with a
    lean, KSA-shaped base. All Saudi-specific extensions live in
    l10n_sa_ejar / sa_property / sa_rental_cycle.
    """
    _name = 'property.property'
    _description = 'العقار'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    # ─── Identity ──────────────────────────────────────────────
    name = fields.Char(
        string='اسم العقار',
        required=True,
        tracking=True,
        index=True,
    )
    flat_name = fields.Char(
        string='اسم الوحدة',
        tracking=True,
        help='Optional unit-level name shown in name_get composition'
    )
    description = fields.Text(string='الوصف')
    active = fields.Boolean(default=True, tracking=True)

    # ─── Type & Status ─────────────────────────────────────────
    property_type = fields.Selection([
        ('residential', 'سكني'),
        ('commercial',  'تجاري'),
        ('industrial',  'صناعي'),
        ('land',        'أرض'),
    ], string='نوع العقار', required=True, default='residential', tracking=True)

    state = fields.Selection([
        ('draft',   'متاح'),
        ('on_rent', 'مؤجر'),
        ('sold',    'مباع'),
    ], string='الحالة', default='draft', tracking=True, copy=False)

    # ─── Parties ───────────────────────────────────────────────
    owner_partner_id = fields.Many2one(
        'res.partner', string='المالك', tracking=True,
        domain="[('is_property_owner','=',True)]",
    )
    tenant_partner_id = fields.Many2one(
        'res.partner', string='المستأجر الحالي', tracking=True,
        domain="[('is_tenant','=',True)]",
        help='Convenience pointer to the current active tenant'
    )

    # ─── Pricing ───────────────────────────────────────────────
    rent_amount = fields.Float(string='الإيجار الشهري', tracking=True)
    price_amount = fields.Float(string='سعر البيع', tracking=True)
    deposit_amount = fields.Float(string='التأمين', copy=False)
    currency_id = fields.Many2one(
        'res.currency', string='العملة',
        default=lambda self: self.env.company.currency_id,
    )

    # ─── Reverse links (set by extending modules / tenancy) ────
    tenancy_ids = fields.One2many(
        'property.tenancy', 'property_id', string='عقود الإيجار'
    )

    @api.depends('tenancy_ids', 'tenancy_ids.state')
    def _compute_tenancy_count(self):
        for rec in self:
            rec.tenancy_count = len(rec.tenancy_ids)

    tenancy_count = fields.Integer(
        compute='_compute_tenancy_count', string='عدد العقود'
    )

    # ─── Display ───────────────────────────────────────────────
    def name_get(self):
        result = []
        for rec in self:
            base = rec.name or ''
            if rec.flat_name:
                base = f"{base} / {rec.flat_name}"
            result.append((rec.id, base))
        return result

    def action_view_tenancies(self):
        self.ensure_one()
        return {
            'name': _('عقود الإيجار'),
            'type': 'ir.actions.act_window',
            'res_model': 'property.tenancy',
            'view_mode': 'list,form',
            'domain': [('property_id', '=', self.id)],
            'context': {'default_property_id': self.id},
        }
