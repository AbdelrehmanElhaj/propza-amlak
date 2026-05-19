# -*- coding: utf-8 -*-
"""ربط عقد الإيجار بعمولات الوسطاء."""
from odoo import models, fields, api, _


class PropertyTenancyBrokerCommission(models.Model):
    _inherit = 'property.tenancy'

    commission_ids = fields.One2many(
        'sa.broker.commission', 'tenancy_id',
        string='عمولات الوسطاء',
    )
    commission_count = fields.Integer(
        string='عدد العمولات',
        compute='_compute_commission_count',
    )
    total_commissions = fields.Float(
        string='إجمالي العمولات (ريال)',
        compute='_compute_commission_count',
    )

    @api.depends('commission_ids', 'commission_ids.commission_amount')
    def _compute_commission_count(self):
        for rec in self:
            rec.commission_count = len(rec.commission_ids)
            rec.total_commissions = sum(rec.commission_ids.mapped('commission_amount'))

    def action_create_commission(self):
        self.ensure_one()
        return {
            'name': _('عمولة وسيط جديدة'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.broker.commission',
            'view_mode': 'form',
            'context': {
                'default_tenancy_id': self.id,
                'default_date_signed': self.start_date,
            },
        }

    def action_view_commissions(self):
        self.ensure_one()
        return {
            'name': _('عمولات هذا العقد'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.broker.commission',
            'view_mode': 'tree,form',
            'domain': [('tenancy_id', '=', self.id)],
            'context': {'default_tenancy_id': self.id},
        }
