# -*- coding: utf-8 -*-
"""إضافة حقول الصور قبل/بعد للعمل الميداني."""
from odoo import models, fields


class SaMaintenanceWorkOrderMobile(models.Model):
    _inherit = 'sa.maintenance.work_order'

    image_before = fields.Binary(
        string='صورة قبل العمل', attachment=True,
        help='صورة من الكاميرا تُلتقَط قبل البدء بالتنفيذ',
    )
    image_after = fields.Binary(
        string='صورة بعد العمل', attachment=True,
        help='صورة من الكاميرا تُلتقَط بعد الإنجاز',
    )
    field_notes = fields.Text(
        string='ملاحظات الميدان',
        help='ملاحظات سريعة من موقع العمل (مختصر للموبايل)',
    )
