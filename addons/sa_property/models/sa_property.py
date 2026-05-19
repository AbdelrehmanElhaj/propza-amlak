from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SaProperty(models.Model):
    """
    امتداد نموذج العقار للسوق السعودي
    يُضيف الهوية السعودية كأولوية ويُعيد تنظيم الحقول
    """
    _inherit = 'property.property'

    # ─── نوع العقار السعودي ──────────────────────────────────────
    sa_property_subtype = fields.Selection([
        # سكني
        ('villa',       'فيلا'),
        ('apartment',   'شقة'),
        ('floor',       'دور'),
        ('annex',       'ملحق / استراحة'),
        ('room',        'غرفة'),
        ('duplex',      'دوبلكس'),
        # تجاري
        ('shop',        'محل تجاري'),
        ('office',      'مكتب'),
        ('showroom',    'معرض'),
        ('clinic',      'عيادة'),
        # صناعي / لوجستي
        ('warehouse',   'مستودع'),
        ('factory',     'مصنع'),
        # أراضي
        ('land_res',    'أرض سكنية'),
        ('land_com',    'أرض تجارية'),
        ('land_agr',    'أرض زراعية'),
        ('land_ind',    'أرض صناعية'),
    ], string='نوع العقار التفصيلي', tracking=True)

    # ─── الصك والهوية القانونية ──────────────────────────────────
    sa_deed_number = fields.Char(
        string='رقم الصك',
        required=False,
        tracking=True,
        help='رقم صك الملكية الصادر من وزارة العدل'
    )
    sa_deed_type = fields.Selection([
        ('electronic',  'صك إلكتروني'),
        ('traditional', 'صك ورقي'),
        ('temp',        'وثيقة مؤقتة'),
        ('inherit',     'إرث'),
        ('gift',        'هبة'),
    ], string='نوع الصك', tracking=True)
    sa_deed_date = fields.Date(string='تاريخ الصك (هجري)')
    sa_deed_area = fields.Float(string='مساحة الصك (م²)')
    sa_plan_number = fields.Char(string='رقم المخطط')
    sa_plot_number = fields.Char(string='رقم القطعة')
    sa_municipality_number = fields.Char(string='رقم البلدية')

    # ─── العنوان الوطني ─────────────────────────────────────────
    sa_national_address = fields.Char(
        string='رقم العنوان الوطني',
        help='8 أحرف: 4 حروف + 4 أرقام مثال RIYD1234'
    )
    sa_region_id = fields.Many2one(
        'sa.region', string='المنطقة الإدارية'
    )
    sa_city_id = fields.Many2one(
        'sa.city', string='المدينة',
        domain="[('region_id','=',sa_region_id)]"
    )
    sa_district = fields.Char(string='الحي')
    sa_street = fields.Char(string='الشارع')
    sa_building_no = fields.Char(string='رقم المبنى')
    sa_secondary_no = fields.Char(string='الرقم الإضافي')
    sa_postal_code = fields.Char(string='الرمز البريدي')

    # ─── بيانات المالك ──────────────────────────────────────────
    sa_owner_id_type = fields.Selection(
        related='owner_partner_id.sa_id_type',
        string='نوع هوية المالك', readonly=True
    )
    sa_owner_national_id = fields.Char(
        related='owner_partner_id.sa_national_id',
        string='هوية المالك', readonly=True
    )
    sa_owner_iban = fields.Char(
        related='owner_partner_id.sa_iban',
        string='IBAN المالك', readonly=True
    )

    # ─── التسعير السعودي ─────────────────────────────────────────
    sa_rent_annual = fields.Float(
        string='الإيجار السنوي (ريال)',
        compute='_compute_sa_rent_annual',
        store=True
    )
    sa_price_sqm = fields.Float(
        string='السعر لكل م²',
        compute='_compute_price_sqm',
        store=True
    )
    sa_rent_freeze = fields.Boolean(
        string='تجميد إيجار الرياض',
        related='sa_city_id.rent_freeze',
        readonly=True
    )
    sa_last_ejar_rent = fields.Float(
        string='آخر إيجار مسجل في إيجار (ريال)',
        help='السقف السعري وفق لائحة الرياض 2025'
    )

    # ─── إيجار ──────────────────────────────────────────────────
    sa_ejar_unit_id = fields.Char(
        string='رقم الوحدة في إيجار',
        readonly=True
    )
    sa_ejar_registered = fields.Boolean(
        string='مسجل في إيجار',
        default=False,
        tracking=True
    )

    # ─── مواصفات سعودية ─────────────────────────────────────────
    sa_area_sqm = fields.Float(string='المساحة الإجمالية (م²)')
    sa_floor_number = fields.Integer(string='رقم الطابق')
    sa_total_floors = fields.Integer(string='إجمالي الطوابق')
    sa_rooms = fields.Integer(string='عدد الغرف')
    sa_bathrooms = fields.Integer(string='عدد دورات المياه')
    sa_majlis = fields.Boolean(string='مجلس')
    sa_maid_room = fields.Boolean(string='غرفة خادمة')
    sa_driver_room = fields.Boolean(string='غرفة سائق')
    sa_storage = fields.Boolean(string='مستودع / مخزن')
    sa_parking = fields.Integer(string='مواقف السيارات')
    sa_pool = fields.Boolean(string='مسبح')
    sa_garden = fields.Boolean(string='حديقة / فناء')
    sa_elevator = fields.Boolean(string='مصعد')
    sa_furnished = fields.Selection([
        ('unfurnished',  'غير مؤثث'),
        ('semi',         'نصف مؤثث'),
        ('fully',        'مؤثث بالكامل'),
    ], string='التأثيث', default='unfurnished')
    sa_year_built = fields.Integer(string='سنة البناء')
    sa_condition = fields.Selection([
        ('new',          'جديد'),
        ('excellent',    'ممتاز'),
        ('good',         'جيد'),
        ('needs_work',   'يحتاج صيانة'),
    ], string='حالة العقار', default='new')

    # ─── Computed ────────────────────────────────────────────────
    @api.depends('rent_amount')
    def _compute_sa_rent_annual(self):
        for rec in self:
            rec.sa_rent_annual = (rec.rent_amount or 0) * 12

    @api.depends('rent_amount', 'sa_area_sqm')
    def _compute_price_sqm(self):
        for rec in self:
            if rec.sa_area_sqm and rec.rent_amount:
                rec.sa_price_sqm = rec.rent_amount / rec.sa_area_sqm
            else:
                rec.sa_price_sqm = 0

    # ─── اسم العرض العربي ────────────────────────────────────────
    def name_get(self):
        result = []
        subtypes = dict(self._fields['sa_property_subtype'].selection)
        for rec in self:
            subtype = subtypes.get(rec.sa_property_subtype, '')
            city = rec.sa_city_id.name_ar if rec.sa_city_id else ''
            district = rec.sa_district or ''
            parts = [p for p in [subtype, district, city] if p]
            name = rec.flat_name or rec.name or ''
            if parts:
                name = f"{name} — {' / '.join(parts)}"
            result.append((rec.id, name))
        return result

    # ─── التحقق ──────────────────────────────────────────────────
    @api.constrains('sa_national_address')
    def _check_national_address(self):
        for rec in self:
            if rec.sa_national_address:
                addr = rec.sa_national_address.strip().upper()
                if len(addr) != 8:
                    raise ValidationError(
                        _('رقم العنوان الوطني يجب أن يكون 8 أحرف (4 حروف + 4 أرقام)')
                    )

    @api.onchange('sa_region_id')
    def _onchange_region(self):
        self.sa_city_id = False
        return {'domain': {'sa_city_id': [('region_id', '=', self.sa_region_id.id)]}}

    @api.onchange('sa_property_subtype')
    def _onchange_subtype(self):
        """تحديث property_type تلقائياً"""
        residential = ['villa', 'apartment', 'floor', 'annex', 'room', 'duplex']
        commercial = ['shop', 'office', 'showroom', 'clinic']
        industrial = ['warehouse', 'factory']
        land = ['land_res', 'land_com', 'land_agr', 'land_ind']
        if self.sa_property_subtype in residential:
            self.property_type = 'residential'
        elif self.sa_property_subtype in commercial:
            self.property_type = 'commercial'
        elif self.sa_property_subtype in industrial:
            self.property_type = 'industrial'
        elif self.sa_property_subtype in land:
            self.property_type = 'land'
