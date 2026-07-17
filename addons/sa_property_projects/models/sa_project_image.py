# -*- coding: utf-8 -*-
import base64

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools.mimetypes import guess_mimetype


class SaProjectImage(models.Model):
    """وسائط المشروع العقاري — صور، مخططات طوابق، مخطط عام، بروشورات."""
    _name = 'sa.project.image'
    _description = 'وسائط المشروع العقاري (صور / مخططات)'
    _order = 'sequence, id'

    project_id = fields.Many2one(
        'sa.project', string='المشروع', required=True,
        ondelete='cascade', index=True,
    )
    sequence = fields.Integer(string='التسلسل', default=10)
    name = fields.Char(string='العنوان')
    media_type = fields.Selection([
        ('photo', 'صورة المشروع'),
        ('floor_plan', 'مخطط الطابق'),
        ('site_plan', 'المخطط العام'),
        ('brochure', 'بروشور / كتيّب'),
    ], string='النوع', required=True, default='photo')

    image = fields.Binary(string='الملف', attachment=True, required=True)
    image_filename = fields.Char(string='اسم الملف')
    mimetype = fields.Char(string='نوع الملف', compute='_compute_mimetype', store=True)
    is_image = fields.Boolean(string='صورة؟', compute='_compute_mimetype', store=True)

    @api.depends('image')
    def _compute_mimetype(self):
        for rec in self:
            if rec.image:
                raw = base64.b64decode(rec.image)
                mt = guess_mimetype(raw, default='application/octet-stream')
                rec.mimetype = mt
                rec.is_image = mt.startswith('image/')
            else:
                rec.mimetype = False
                rec.is_image = False

    @api.constrains('image', 'media_type')
    def _check_file(self):
        max_bytes = 10 * 1024 * 1024
        for rec in self:
            if not rec.image:
                continue
            raw = base64.b64decode(rec.image)
            if len(raw) > max_bytes:
                raise ValidationError(_('الملف أكبر من الحد المسموح (10 ميجابايت)'))
            if rec.media_type == 'floor_plan' and rec.mimetype not in (
                'application/pdf', 'image/jpeg', 'image/png', 'image/webp',
            ):
                raise ValidationError(_('مخطط الطابق يجب أن يكون صورة أو ملف PDF'))
            if rec.media_type == 'photo' and not rec.is_image:
                raise ValidationError(_('صورة المشروع يجب أن تكون ملف صورة'))
