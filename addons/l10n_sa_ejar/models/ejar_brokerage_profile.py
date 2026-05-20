from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging
import re

_logger = logging.getLogger(__name__)


class EjarBrokerageProfile(models.Model):
    """
    Per-company brokerage identity used in every Ejar contract.

    This is the legal entity that appears in Ejar contracts — never Propza.
    One profile per Odoo company; enforced by SQL constraint.
    """

    _name = 'ejar.brokerage.profile'
    _description = 'Ejar Brokerage Profile (ملف مكتب الوساطة)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'office_name_ar'

    # ── Company isolation ────────────────────────────────────────────
    company_id = fields.Many2one(
        'res.company',
        string='الشركة',
        required=True,
        default=lambda self: self.env.company,
        ondelete='cascade',
    )

    # ── Office identity ──────────────────────────────────────────────
    office_name_ar = fields.Char(
        string='اسم المكتب (عربي)',
        required=True,
        tracking=True,
    )
    office_name_en = fields.Char(
        string='Office Name (English)',
        tracking=True,
    )
    cr_number = fields.Char(
        string='رقم السجل التجاري',
        size=10,
        tracking=True,
        help='Commercial Registration number — 10 digits',
    )
    unified_number = fields.Char(
        string='الرقم الموحد',
        size=10,
        tracking=True,
        help='Unified organization number — 10 digits',
    )
    license_number = fields.Char(
        string='رقم الترخيص (ريرا)',
        tracking=True,
        help='RERA brokerage license number',
    )
    license_expiry = fields.Date(
        string='تاريخ انتهاء الترخيص',
        tracking=True,
    )
    vat_number = fields.Char(
        string='رقم تسجيل ضريبة القيمة المضافة',
        size=15,
        tracking=True,
    )

    # ── Representative ───────────────────────────────────────────────
    representative_partner_id = fields.Many2one(
        'res.partner',
        string='الممثل القانوني',
        tracking=True,
        help='Authorized signatory for Ejar contracts',
    )
    representative_id_number = fields.Char(
        related='representative_partner_id.sa_national_id',
        string='هوية الممثل',
        readonly=True,
    )
    representative_mobile = fields.Char(
        related='representative_partner_id.mobile',
        string='جوال الممثل',
        readonly=True,
    )

    # ── National address ─────────────────────────────────────────────
    national_address_code = fields.Char(
        string='رمز العنوان الوطني',
        size=8,
        tracking=True,
        help='4 letters + 4 digits (e.g. ABCD1234)',
    )
    building_number = fields.Char(string='رقم المبنى', size=4)
    street_ar = fields.Char(string='الشارع')
    district_ar = fields.Char(string='الحي')
    sa_city_id = fields.Many2one('sa.city', string='المدينة')
    sa_region_id = fields.Many2one('sa.region', string='المنطقة')
    postal_code = fields.Char(string='الرمز البريدي', size=5)

    # ── Ejar platform references ─────────────────────────────────────
    ejar_office_id = fields.Char(
        string='معرّف المكتب في إيجار',
        readonly=True,
        copy=False,
        help='Office UUID assigned by Ejar platform',
    )
    ejar_registered = fields.Boolean(
        string='مسجّل في إيجار',
        default=False,
        readonly=True,
        tracking=True,
    )

    # ── Status ───────────────────────────────────────────────────────
    active = fields.Boolean(default=True)
    is_verified = fields.Boolean(
        string='تم التحقق',
        default=False,
        tracking=True,
        help='Profile verified by Propza operations team',
    )

    # ── Computed ─────────────────────────────────────────────────────
    contract_count = fields.Integer(
        string='عدد العقود',
        compute='_compute_contract_count',
    )
    license_expired = fields.Boolean(
        string='الترخيص منتهي',
        compute='_compute_license_expired',
        store=False,
    )

    _sql_constraints = [
        (
            'company_unique',
            'UNIQUE(company_id)',
            'يوجد ملف وساطة بالفعل لهذه الشركة',
        )
    ]

    # ── Compute ──────────────────────────────────────────────────────

    @api.depends()
    def _compute_contract_count(self):
        for rec in self:
            rec.contract_count = self.env['ejar.contract'].search_count(
                [('company_id', '=', rec.company_id.id)]
            )

    @api.depends('license_expiry')
    def _compute_license_expired(self):
        today = fields.Date.today()
        for rec in self:
            rec.license_expired = bool(rec.license_expiry and rec.license_expiry < today)

    # ── Validation ───────────────────────────────────────────────────

    @api.constrains('cr_number')
    def _check_cr_number(self):
        for rec in self:
            if rec.cr_number and not re.fullmatch(r'\d{10}', rec.cr_number):
                raise ValidationError(_('رقم السجل التجاري يجب أن يكون 10 أرقام'))

    @api.constrains('unified_number')
    def _check_unified_number(self):
        for rec in self:
            if rec.unified_number and not re.fullmatch(r'\d{10}', rec.unified_number):
                raise ValidationError(_('الرقم الموحد يجب أن يكون 10 أرقام'))

    @api.constrains('vat_number')
    def _check_vat_number(self):
        for rec in self:
            if rec.vat_number and not re.fullmatch(r'\d{15}', rec.vat_number):
                raise ValidationError(_('رقم ضريبة القيمة المضافة يجب أن يكون 15 رقماً'))

    @api.constrains('national_address_code')
    def _check_national_address(self):
        for rec in self:
            if rec.national_address_code and not re.fullmatch(
                r'[A-Za-z]{4}\d{4}', rec.national_address_code
            ):
                raise ValidationError(
                    _('رمز العنوان الوطني يجب أن يكون 4 أحرف + 4 أرقام (مثال: ABCD1234)')
                )

    # ── Pre-flight validation (called by lifecycle service) ──────────

    def validate_for_submission(self):
        """
        Raise ValidationError listing every missing field required by Ejar.
        Called before any API call is made.
        """
        self.ensure_one()
        errors = []
        if not self.cr_number:
            errors.append(_('رقم السجل التجاري'))
        if not self.unified_number:
            errors.append(_('الرقم الموحد'))
        if not self.license_number:
            errors.append(_('رقم الترخيص (ريرا)'))
        if self.license_expired:
            errors.append(_('ترخيص ريرا منتهي الصلاحية'))
        if not self.representative_partner_id:
            errors.append(_('الممثل القانوني'))
        if not self.representative_partner_id.sa_national_id:
            errors.append(_('هوية الممثل القانوني'))
        if not self.office_name_ar:
            errors.append(_('اسم المكتب (عربي)'))

        if errors:
            raise ValidationError(
                _('ملف الوساطة غير مكتمل. الحقول المطلوبة:\n• %s')
                % '\n• '.join(errors)
            )

    # ── Smart button ─────────────────────────────────────────────────

    def action_view_contracts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('عقود إيجار'),
            'res_model': 'ejar.contract',
            'view_mode': 'list,form',
            'domain': [('company_id', '=', self.company_id.id)],
            'context': {'default_company_id': self.company_id.id},
        }
