# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class SaCallCenterQueue(models.Model):
    _name = 'sa.call.center.queue'
    _description = 'قائمة انتظار مركز الاتصال'
    _order = 'sequence, name'

    name = fields.Char(string='اسم القائمة', required=True)
    code = fields.Char(
        string='رمز القائمة', required=True, copy=False,
        help='الرمز كما هو معرَّف في نظام PBX/الاتصالات — يُستخدم لمطابقة أحداث الـ webhook',
    )
    sequence = fields.Integer(string='الترتيب', default=10)
    member_ids = fields.Many2many('res.users', string='أعضاء القائمة')
    active = fields.Boolean(default=True)
    call_count = fields.Integer(string='عدد المكالمات', compute='_compute_call_count')

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'رمز القائمة مستخدم بالفعل.'),
    ]

    def _compute_call_count(self):
        Call = self.env['sa.call.center.call']
        for rec in self:
            rec.call_count = Call.search_count([('queue_id', '=', rec.id)])

    def action_view_calls(self):
        self.ensure_one()
        return {
            'name': _('مكالمات — %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'sa.call.center.call',
            'view_mode': 'tree,form',
            'domain': [('queue_id', '=', self.id)],
        }
