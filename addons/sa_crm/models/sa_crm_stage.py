# -*- coding: utf-8 -*-
from odoo import models, fields


class SaCrmStage(models.Model):
    _name = 'sa.crm.stage'
    _description = 'مرحلة CRM'
    _order = 'sequence, id'

    name = fields.Char(string='المرحلة', required=True, translate=True)
    sequence = fields.Integer(string='الترتيب', default=10)
    fold = fields.Boolean(string='مطوي في كانبان', default=False)
    is_won = fields.Boolean(string='مرحلة الفوز', default=False)
    probability = fields.Float(string='نسبة الاحتمال', default=20.0)
    lead_ids = fields.One2many('sa.crm.lead', 'stage_id', string='الطلبات')
