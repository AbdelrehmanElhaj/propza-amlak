# -*- coding: utf-8 -*-
from odoo import models, fields


class SaCrmLead(models.Model):
    _inherit = 'sa.crm.lead'

    sa_call_talk_duration_total = fields.Integer(
        string='إجمالي وقت التحدث (ثانية)',
        related='partner_id.sa_call_talk_duration_total',
        readonly=True,
    )
    sa_call_repeat_count = fields.Integer(
        string='مكالمات مكررة',
        related='partner_id.sa_call_repeat_count',
        readonly=True,
    )
