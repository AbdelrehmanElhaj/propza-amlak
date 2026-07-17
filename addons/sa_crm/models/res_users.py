# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    sa_lead_rotation_eligible = fields.Boolean(
        string='مؤهل لتوزيع الطلبات التلقائي', default=True,
        help='إذا لم يُفعَّل، لن يستقبل هذا الموظف طلبات جديدة عبر التوزيع الآلي حسب الحمل.',
    )
