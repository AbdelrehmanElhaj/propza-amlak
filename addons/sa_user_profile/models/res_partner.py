# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ─── Personal Info ────────────────────────────────────────────
    gender = fields.Selection([
        ('male',   'ذكر'),
        ('female', 'أنثى'),
    ], string='الجنس')

    date_of_birth = fields.Date(string='تاريخ الميلاد')

    bio = fields.Text(string='نبذة شخصية')

    # ─── National Address (Saudi short-address standard) ─────────
    sa_region_id = fields.Many2one(
        'sa.region',
        string='المنطقة الإدارية',
    )
    sa_district = fields.Char(string='الحي')
    sa_building_no = fields.Char(string='رقم المبنى')
    sa_unit_no = fields.Char(string='رقم الوحدة')
    sa_additional_no = fields.Char(string='الرقم الإضافي')
    sa_postal_code = fields.Char(string='الرمز البريدي')
    sa_national_address = fields.Char(string='رقم العنوان الوطني (Short Address)')

    # ─── Relations ────────────────────────────────────────────────
    verification_ids = fields.One2many(
        'sa.user.verification', 'partner_id',
        string='سجلات التوثيق',
    )
    document_ids = fields.One2many(
        'sa.user.document', 'partner_id',
        string='الوثائق',
    )

    # ─── Computed ─────────────────────────────────────────────────
    verification_state = fields.Selection([
        ('unverified', 'غير موثَّق'),
        ('pending',    'قيد المراجعة'),
        ('verified',   'موثَّق ✓'),
        ('rejected',   'مرفوض'),
    ], string='حالة التوثيق', compute='_compute_verification_state', store=True)

    profile_completion = fields.Integer(
        string='اكتمال الملف %',
        compute='_compute_profile_completion',
    )

    @api.depends('verification_ids.state')
    def _compute_verification_state(self):
        for p in self:
            verifs = p.verification_ids.sorted('id', reverse=True)
            if not verifs:
                p.verification_state = 'unverified'
            else:
                latest = verifs[0]
                mapping = {
                    'draft':     'unverified',
                    'submitted': 'pending',
                    'verified':  'verified',
                    'rejected':  'rejected',
                }
                p.verification_state = mapping.get(latest.state, 'unverified')

    def _compute_profile_completion(self):
        fields_checked = [
            'name', 'phone', 'email', 'image_1920',
            'gender', 'date_of_birth',
            'sa_id_type', 'sa_national_id',
            'sa_region_id', 'city', 'sa_district',
            'sa_national_address',
        ]
        for p in self:
            filled = sum(1 for f in fields_checked if getattr(p, f, False))
            verified_bonus = 10 if p.verification_state == 'verified' else 0
            doc_bonus = 5 if p.document_ids else 0
            score = int(filled / len(fields_checked) * 85) + verified_bonus + doc_bonus
            p.profile_completion = min(score, 100)
