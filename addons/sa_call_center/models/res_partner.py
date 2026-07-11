# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    sa_call_ids = fields.One2many('sa.call.center.call', 'partner_id', string='المكالمات')
    sa_call_count = fields.Integer(string='عدد المكالمات', compute='_compute_sa_call_count')

    @api.depends('sa_call_ids')
    def _compute_sa_call_count(self):
        for rec in self:
            rec.sa_call_count = len(rec.sa_call_ids)

    def action_view_calls(self):
        self.ensure_one()
        return {
            'name': _('مكالمات — %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'sa.call.center.call',
            'view_mode': 'tree,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }
