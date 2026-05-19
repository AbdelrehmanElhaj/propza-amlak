# -*- coding: utf-8 -*-
"""لوحة المالك — KPIs محسوبة على res.partner.

تجميعات مالية وتشغيلية لكل مالك:
    * عدد العقارات (إجمالي / مؤجَّر / شاغر)
    * إجمالي العقود السارية + الإيرادات الشهرية
    * الدفعات المتأخرة (عدد + مبلغ)
    * العقود التي تنتهي خلال 60 يوم
"""
from odoo import models, fields, api, _
from datetime import date, timedelta


class ResPartnerDashboard(models.Model):
    _inherit = 'res.partner'

    # ─── Property counts ──────────────────────────────────────────
    sa_total_properties = fields.Integer(
        string='إجمالي العقارات',
        compute='_compute_owner_kpis',
    )
    sa_occupied_properties = fields.Integer(
        string='عقارات مؤجَّرة',
        compute='_compute_owner_kpis',
    )
    sa_vacant_properties = fields.Integer(
        string='عقارات شاغرة',
        compute='_compute_owner_kpis',
    )

    # ─── Tenancy counts ───────────────────────────────────────────
    sa_active_tenancies = fields.Integer(
        string='عقود سارية',
        compute='_compute_owner_kpis',
    )
    sa_expiring_60d = fields.Integer(
        string='تنتهي خلال 60 يوم',
        compute='_compute_owner_kpis',
    )

    # ─── Money KPIs ───────────────────────────────────────────────
    sa_monthly_revenue = fields.Float(
        string='إيراد شهري متوقع (ريال)',
        compute='_compute_owner_kpis',
        help='مجموع قيم إيجارات العقود السارية',
    )
    sa_overdue_count = fields.Integer(
        string='دفعات متأخرة',
        compute='_compute_owner_kpis',
    )
    sa_overdue_total = fields.Float(
        string='إجمالي المتأخرات (ريال)',
        compute='_compute_owner_kpis',
    )
    sa_total_collected = fields.Float(
        string='إجمالي التحصيل YTD (ريال)',
        compute='_compute_owner_kpis',
        help='مجموع المدفوعات منذ بداية السنة الحالية',
    )

    @api.depends('is_property_owner')
    def _compute_owner_kpis(self):
        Property = self.env['property.property']
        Tenancy = self.env['property.tenancy']
        Payment = self.env['sa.rent.payment']
        today = date.today()
        year_start = date(today.year, 1, 1)
        soon = today + timedelta(days=60)

        for rec in self:
            if not rec.is_property_owner:
                rec.sa_total_properties = 0
                rec.sa_occupied_properties = 0
                rec.sa_vacant_properties = 0
                rec.sa_active_tenancies = 0
                rec.sa_expiring_60d = 0
                rec.sa_monthly_revenue = 0.0
                rec.sa_overdue_count = 0
                rec.sa_overdue_total = 0.0
                rec.sa_total_collected = 0.0
                continue

            props = Property.search([('owner_partner_id', '=', rec.id)])
            rec.sa_total_properties = len(props)
            rec.sa_occupied_properties = len(props.filtered(
                lambda p: p.state == 'on_rent'
            ))
            rec.sa_vacant_properties = len(props.filtered(
                lambda p: p.state == 'draft'
            ))

            active = Tenancy.search([
                ('owner_partner_id', '=', rec.id),
                ('state', '=', 'running'),
            ])
            rec.sa_active_tenancies = len(active)
            rec.sa_expiring_60d = len(active.filtered(
                lambda t: t.end_date and today <= t.end_date <= soon
            ))
            rec.sa_monthly_revenue = sum(active.mapped('rent_amount'))

            tenancy_ids = Tenancy.search([
                ('owner_partner_id', '=', rec.id),
            ]).ids

            overdue = Payment.search([
                ('tenancy_id', 'in', tenancy_ids),
                ('state', 'in', ('overdue', 'pending')),
                ('due_date', '<', today),
            ])
            rec.sa_overdue_count = len(overdue)
            rec.sa_overdue_total = sum(overdue.mapped('balance'))

            collected = Payment.search([
                ('tenancy_id', 'in', tenancy_ids),
                ('state', 'in', ('paid', 'partial')),
                ('payment_date', '>=', year_start),
                ('payment_date', '<=', today),
            ])
            rec.sa_total_collected = sum(collected.mapped('amount_paid'))

    # ─── Drill-down actions ──────────────────────────────────────
    def action_view_my_properties(self):
        self.ensure_one()
        return {
            'name': _('عقارات %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'property.property',
            'view_mode': 'tree,form,kanban',
            'domain': [('owner_partner_id', '=', self.id)],
        }

    def action_view_my_tenancies(self):
        self.ensure_one()
        return {
            'name': _('عقود إيجار %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'property.tenancy',
            'view_mode': 'tree,form',
            'domain': [('owner_partner_id', '=', self.id)],
        }

    def action_view_my_overdue(self):
        self.ensure_one()
        tenancy_ids = self.env['property.tenancy'].search([
            ('owner_partner_id', '=', self.id),
        ]).ids
        return {
            'name': _('دفعات متأخرة — %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'sa.rent.payment',
            'view_mode': 'tree,form',
            'domain': [
                ('tenancy_id', 'in', tenancy_ids),
                ('state', 'in', ('overdue', 'pending')),
                ('due_date', '<', fields.Date.today()),
            ],
        }
