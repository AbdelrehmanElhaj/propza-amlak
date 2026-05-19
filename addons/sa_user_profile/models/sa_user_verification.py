# -*- coding: utf-8 -*-
import re
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaUserVerification(models.Model):
    _name = 'sa.user.verification'
    _description = 'توثيق هوية المستخدم'
    _order = 'id desc'
    _rec_name = 'partner_id'

    partner_id = fields.Many2one(
        'res.partner', string='الشخص',
        required=True, ondelete='cascade', index=True,
    )
    id_type = fields.Selection([
        ('national_id', 'هوية وطنية'),
        ('iqama',       'إقامة'),
        ('gcc',         'هوية خليجي'),
        ('passport',    'جواز سفر'),
        ('commercial',  'سجل تجاري'),
    ], string='نوع الوثيقة', required=True)

    id_number = fields.Char(string='رقم الوثيقة', required=True)
    id_expiry = fields.Date(string='تاريخ الانتهاء')

    id_scan = fields.Binary(string='صورة الوثيقة', attachment=True)
    id_scan_name = fields.Char(string='اسم الملف')

    state = fields.Selection([
        ('draft',     'مسودة'),
        ('submitted', 'مقدَّم'),
        ('verified',  'موثَّق'),
        ('rejected',  'مرفوض'),
    ], string='الحالة', default='draft', tracking=True)

    rejection_reason = fields.Char(string='سبب الرفض')
    verified_date = fields.Datetime(string='تاريخ التوثيق', readonly=True)
    submission_date = fields.Datetime(string='تاريخ التقديم', readonly=True)

    # ─── Actions ─────────────────────────────────────────────────

    def action_submit(self):
        for rec in self:
            if rec.state not in ('draft', 'rejected'):
                raise UserError(_('يمكن تقديم الطلب من حالة مسودة أو مرفوض فقط.'))
            rec.submission_date = fields.Datetime.now()
            rec._auto_verify()

    def action_reset(self):
        self.write({'state': 'draft', 'rejection_reason': False, 'verified_date': False})

    # ─── Auto-verification logic ──────────────────────────────────

    def _auto_verify(self):
        for rec in self:
            errors = []
            id_num = re.sub(r'[\s\-]', '', rec.id_number or '')

            if rec.id_type == 'national_id':
                if not re.match(r'^1\d{9}$', id_num):
                    errors.append('رقم الهوية الوطنية: 10 أرقام يبدأ بـ 1')

            elif rec.id_type == 'iqama':
                if not re.match(r'^2\d{9}$', id_num):
                    errors.append('رقم الإقامة: 10 أرقام يبدأ بـ 2')

            elif rec.id_type == 'gcc':
                if not id_num.isdigit() or len(id_num) < 8:
                    errors.append('رقم الهوية الخليجية: 8 أرقام على الأقل')

            elif rec.id_type == 'passport':
                if len(id_num) < 6:
                    errors.append('رقم جواز السفر: 6 خانات على الأقل')

            elif rec.id_type == 'commercial':
                if not re.match(r'^\d{10}$', id_num):
                    errors.append('رقم السجل التجاري: 10 أرقام')

            if rec.id_expiry and rec.id_expiry < fields.Date.today():
                errors.append('الوثيقة منتهية الصلاحية')

            if not rec.id_scan:
                errors.append('يجب رفع صورة الوثيقة')

            if errors:
                rec.write({
                    'state': 'rejected',
                    'rejection_reason': ' | '.join(errors),
                    'verified_date': False,
                })
            else:
                rec.write({
                    'state': 'verified',
                    'rejection_reason': False,
                    'verified_date': fields.Datetime.now(),
                })
                # Sync back to partner identity fields
                rec.partner_id.write({
                    'sa_id_type':     rec.id_type,
                    'sa_national_id': rec.id_number,
                    'sa_id_expiry':   rec.id_expiry,
                    'sa_id_verified': True,
                })
