# -*- coding: utf-8 -*-
"""Maintenance-side extension on property.tenancy.

The base tenancy lives in sa_property_base. The maintenance integration
(O2M back-reference, count, quick-create button) belongs in this module
since it's only meaningful when sa_maintenance is installed.
"""
from odoo import models, fields, api, _


class PropertyTenancy(models.Model):
    _inherit = 'property.tenancy'

    sa_maintenance_ids = fields.One2many(
        'sa.maintenance.request', 'tenancy_id',
        string='طلبات الصيانة'
    )
    sa_maintenance_count = fields.Integer(
        compute='_compute_sa_maintenance_count',
        string='عدد طلبات الصيانة'
    )

    @api.depends('sa_maintenance_ids', 'sa_maintenance_ids.state')
    def _compute_sa_maintenance_count(self):
        for rec in self:
            rec.sa_maintenance_count = len(rec.sa_maintenance_ids.filtered(
                lambda m: m.state not in ('done', 'cancelled')
            ))

    def action_new_maintenance(self):
        self.ensure_one()
        return {
            'name': _('طلب صيانة جديد'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.maintenance.request',
            'view_mode': 'form',
            'context': {
                'default_tenancy_id': self.id,
                'default_property_id': self.property_id.id,
            },
        }

    def action_view_maintenance(self):
        self.ensure_one()
        return {
            'name': _('طلبات الصيانة'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.maintenance.request',
            'view_mode': 'tree,form',
            'domain': [('tenancy_id', '=', self.id)],
            'context': {
                'default_tenancy_id': self.id,
                'default_property_id': self.property_id.id,
            },
        }
