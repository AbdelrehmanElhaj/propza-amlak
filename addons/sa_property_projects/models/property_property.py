# -*- coding: utf-8 -*-
from odoo import models, fields


class PropertyPropertyProject(models.Model):
    _inherit = 'property.property'

    project_id = fields.Many2one(
        'sa.project', string='المشروع العقاري', tracking=True, index=True,
    )
