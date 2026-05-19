# -*- coding: utf-8 -*-
from odoo import models, fields


class SaMaintenanceSkill(models.Model):
    """تخصصات الصيانة (سباكة، كهرباء، تكييف...)
    تُستخدم كـ Many2many tags على المقاولين والطلبات.
    """
    _name = 'sa.maintenance.skill'
    _description = 'تخصص صيانة'
    _order = 'sequence,name'

    name = fields.Char(string='الاسم', required=True, translate=True)
    code = fields.Char(string='الكود', required=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(string='اللون', default=0)
    description = fields.Text(string='الوصف')

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'كود التخصص يجب أن يكون فريداً.'),
    ]
