# -*- coding: utf-8 -*-
from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    is_call_center_agent = fields.Boolean(string='موظف مركز اتصال')
    sip_extension = fields.Char(string='الداخلي (SIP Extension)')
    call_center_status = fields.Selection([
        ('available', 'متاح'),
        ('busy', 'مشغول'),
        ('paused', 'متوقف مؤقتاً'),
        ('offline', 'غير متصل'),
    ], string='حالة الوكيل', default='offline')
