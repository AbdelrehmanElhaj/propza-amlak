# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SaUserDocument(models.Model):
    _name = 'sa.user.document'
    _description = 'وثائق المستخدم'
    _order = 'upload_date desc'
    _rec_name = 'name'

    partner_id = fields.Many2one(
        'res.partner', string='الشخص',
        required=True, ondelete='cascade', index=True,
    )
    doc_type = fields.Selection([
        ('national_id',    'هوية وطنية / إقامة'),
        ('passport',       'جواز سفر'),
        ('commercial_reg', 'سجل تجاري'),
        ('lease_contract', 'عقد إيجار'),
        ('ownership_deed', 'صك ملكية'),
        ('broker_license', 'ترخيص وساطة'),
        ('other',          'أخرى'),
    ], string='نوع الوثيقة', required=True, default='other')

    name = fields.Char(string='الاسم / العنوان', required=True)
    datas = fields.Binary(string='الملف', attachment=True)
    filename = fields.Char(string='اسم الملف')
    upload_date = fields.Date(string='تاريخ الرفع', default=fields.Date.today)
    expiry_date = fields.Date(string='تاريخ الانتهاء')
    notes = fields.Char(string='ملاحظات')

    state = fields.Selection([
        ('active',         'ساري'),
        ('expiring_soon',  'ينتهي قريباً'),
        ('expired',        'منتهي'),
        ('archived',       'مؤرشف'),
    ], string='الحالة', compute='_compute_state', store=True)

    @api.depends('expiry_date')
    def _compute_state(self):
        today = fields.Date.today()
        for doc in self:
            if doc.state == 'archived':
                continue
            if not doc.expiry_date:
                doc.state = 'active'
            elif doc.expiry_date < today:
                doc.state = 'expired'
            elif (doc.expiry_date - today).days <= 30:
                doc.state = 'expiring_soon'
            else:
                doc.state = 'active'

    def action_archive(self):
        self.write({'state': 'archived'})

    def action_restore(self):
        # Re-compute by clearing archived flag
        for doc in self:
            doc.state = 'active'
            doc._compute_state()
