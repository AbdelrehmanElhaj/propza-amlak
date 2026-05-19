from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class PropertyProperty(models.Model):
    _inherit = 'property.property'

    # ─── Saudi Location ──────────────────────────────────────────
    sa_region_id = fields.Many2one(
        'sa.region',
        string='المنطقة الإدارية',
        help='Saudi Administrative Region (14 regions)'
    )
    sa_city_id = fields.Many2one(
        'sa.city',
        string='المدينة',
        domain="[('region_id', '=', sa_region_id)]"
    )
    national_address_code = fields.Char(
        string='رقم العنوان الوطني',
        help='Short Address Code (e.g. ABCD1234)'
    )
    building_number = fields.Char(string='رقم المبنى')
    street_ar = fields.Char(string='اسم الشارع (عربي)')
    district = fields.Char(string='الحي')
    district_ar = fields.Char(string='الحي (عربي)')
    postal_code = fields.Char(string='الرمز البريدي')

    # ─── Deed / Title ────────────────────────────────────────────
    deed_number = fields.Char(
        string='رقم الصك',
        help='Property Title Deed Number (رقم صك الملكية)'
    )
    deed_type = fields.Selection([
        ('electronic', 'صك إلكتروني'),
        ('traditional', 'صك تقليدي'),
        ('temporary', 'وثيقة مؤقتة'),
    ], string='نوع الصك')
    deed_date = fields.Date(string='تاريخ الصك')
    municipality_number = fields.Char(string='رقم البلدية')
    plot_number = fields.Char(string='رقم القطعة')
    plan_number = fields.Char(string='رقم المخطط')

    # ─── Ejar Unit Info ──────────────────────────────────────────
    ejar_unit_id = fields.Char(
        string='رقم الوحدة في إيجار',
        readonly=True,
        help='Unit ID assigned by Ejar platform after registration'
    )
    ejar_registered = fields.Boolean(
        string='مسجل في إيجار',
        default=False
    )
    ejar_unit_type = fields.Selection([
        ('residential', 'سكني'),
        ('commercial', 'تجاري'),
        ('industrial', 'صناعي'),
        ('land', 'أرض'),
    ], string='نوع الوحدة في إيجار',
        compute='_compute_ejar_unit_type', store=True
    )

    # ─── Rent Freeze (Riyadh Regulation Sep 2025) ────────────────
    rent_freeze_active = fields.Boolean(
        string='تجميد الإيجار مفعّل',
        compute='_compute_rent_freeze',
        store=True,
        help='Riyadh: Rent increase frozen for 5 years from Sep 25, 2025'
    )
    last_ejar_rent = fields.Float(
        string='آخر إيجار مسجل في إيجار',
        help='Last registered rent value on Ejar (used as rent cap)'
    )

    # ─── Ejar Contract Count ─────────────────────────────────────
    ejar_contract_count = fields.Integer(
        compute='_compute_ejar_contract_count',
        string='عقود إيجار'
    )

    @api.depends('property_type')
    def _compute_ejar_unit_type(self):
        mapping = {
            'residential': 'residential',
            'commercial': 'commercial',
            'industrial': 'industrial',
            'land': 'land',
        }
        for rec in self:
            rec.ejar_unit_type = mapping.get(rec.property_type, 'residential')

    @api.depends('sa_city_id', 'sa_city_id.rent_freeze')
    def _compute_rent_freeze(self):
        for rec in self:
            rec.rent_freeze_active = rec.sa_city_id.rent_freeze if rec.sa_city_id else False

    def _compute_ejar_contract_count(self):
        for rec in self:
            rec.ejar_contract_count = self.env['ejar.contract'].search_count([
                ('property_id', '=', rec.id)
            ])

    def action_view_ejar_contracts(self):
        return {
            'name': 'عقود إيجار',
            'type': 'ir.actions.act_window',
            'res_model': 'ejar.contract',
            'view_mode': 'list,form',
            'domain': [('property_id', '=', self.id)],
            'context': {'default_property_id': self.id},
        }

    @api.constrains('national_address_code')
    def _check_national_address(self):
        for rec in self:
            if rec.national_address_code:
                code = rec.national_address_code.strip().upper()
                if len(code) != 8:
                    raise ValidationError(
                        _('رقم العنوان الوطني يجب أن يكون 8 أحرف (مثال: ABCD1234)')
                    )
