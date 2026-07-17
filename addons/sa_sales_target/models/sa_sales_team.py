# -*- coding: utf-8 -*-
"""فريق مبيعات — مدير + أعضاء، تُبنى عليه أهداف المبيعات الجماعية."""
from odoo import models, fields, api


class SaSalesTeam(models.Model):
    _name = 'sa.sales.team'
    _description = 'فريق مبيعات'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    manager_id = fields.Many2one('res.users', string='مدير الفريق', tracking=True)
    member_ids = fields.Many2many(
        'res.users', 'sa_sales_team_user_rel', 'team_id', 'user_id',
        string='أعضاء الفريق',
    )
    member_count = fields.Integer(compute='_compute_member_count', string='عدد الأعضاء')
    target_ids = fields.One2many('sa.sales.target', 'team_id', string='الأهداف')

    @api.depends('member_ids')
    def _compute_member_count(self):
        for rec in self:
            rec.member_count = len(rec.member_ids)
