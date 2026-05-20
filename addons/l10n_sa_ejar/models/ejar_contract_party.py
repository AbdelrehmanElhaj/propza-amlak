from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import re
import logging

_logger = logging.getLogger(__name__)


class EjarContractParty(models.Model):
    """
    A lessor, tenant, or representative attached to an Ejar contract.

    Stores both Odoo partner data and the Ejar API references returned
    after successful entity/party creation.
    """

    _name = 'ejar.contract.party'
    _description = 'طرف عقد إيجار'
    _order = 'role, id'
    _rec_name = 'display_name'

    # ── Parent contract ───────────────────────────────────────────────
    contract_id = fields.Many2one(
        'ejar.contract',
        string='العقد',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        related='contract_id.company_id',
        store=True,
        index=True,
    )

    # ── Role & entity type ────────────────────────────────────────────
    role = fields.Selection([
        ('lessor',                  'مؤجر'),
        ('tenant',                  'مستأجر'),
        ('lessor_representative',   'ممثل المؤجر'),
        ('tenant_representative',   'ممثل المستأجر'),
    ], string='الدور', required=True, tracking=True)

    entity_type = fields.Selection([
        ('individual',    'فرد'),
        ('organization',  'شركة / مؤسسة'),
    ], string='نوع الجهة', required=True, default='individual')

    # ── Odoo partner link ─────────────────────────────────────────────
    partner_id = fields.Many2one(
        'res.partner',
        string='الشريك',
        ondelete='restrict',
    )

    # ── Identity (individual) ─────────────────────────────────────────
    id_number = fields.Char(
        string='رقم الهوية',
        help='رقم الهوية الوطنية أو الإقامة أو جواز السفر',
    )
    id_type = fields.Selection([
        ('national_id', 'هوية وطنية'),
        ('iqama',       'إقامة'),
        ('passport',    'جواز سفر'),
        ('gcc_id',      'هوية خليجي'),
    ], string='نوع الهوية', default='national_id')
    id_expiry = fields.Date(string='تاريخ انتهاء الهوية')
    date_of_birth = fields.Date(string='تاريخ الميلاد')
    nationality = fields.Char(string='الجنسية', default='SA')

    # ── Contact ───────────────────────────────────────────────────────
    mobile = fields.Char(string='رقم الجوال')
    email = fields.Char(string='البريد الإلكتروني')
    full_name_ar = fields.Char(string='الاسم الكامل (عربي)')
    full_name_en = fields.Char(string='Full Name (English)')

    # ── Organization fields ───────────────────────────────────────────
    cr_number = fields.Char(string='رقم السجل التجاري', size=10)
    unified_number = fields.Char(string='الرقم الموحد', size=10)

    # ── IBAN (lessor only) ────────────────────────────────────────────
    iban = fields.Char(
        string='رقم الآيبان',
        size=24,
        help='SA + 22 alphanumeric characters (required for lessor)',
    )

    # ── Proxy document (representatives only) ─────────────────────────
    proxy_doc = fields.Binary(
        string='وثيقة التوكيل',
        attachment=True,
    )
    proxy_doc_filename = fields.Char(string='اسم ملف التوكيل')
    proxy_doc_type = fields.Selection([
        ('e_poa',       'توكيل إلكتروني (نجيز)'),
        ('paper_poa',   'توكيل ورقي'),
        ('court_order', 'قرار محكمة'),
    ], string='نوع وثيقة التوكيل', default='paper_poa')

    # ── Ejar API references ───────────────────────────────────────────
    ejar_entity_id = fields.Char(
        string='معرّف الجهة في إيجار',
        readonly=True,
        copy=False,
        help='UUID assigned by Ejar for individual/organization entity',
    )
    ejar_party_id = fields.Char(
        string='معرّف الطرف في إيجار',
        readonly=True,
        copy=False,
        help='UUID assigned by Ejar for this party on this contract',
    )
    ejar_proxy_doc_id = fields.Char(
        string='معرّف وثيقة التوكيل في إيجار',
        readonly=True,
        copy=False,
    )

    # ── Sync state ────────────────────────────────────────────────────
    sync_state = fields.Selection([
        ('pending',     'في الانتظار'),
        ('synced',      'تمت المزامنة'),
        ('failed',      'فشل'),
    ], string='حالة المزامنة', default='pending', readonly=True)
    sync_error = fields.Text(string='خطأ المزامنة', readonly=True)

    # ── Display name ──────────────────────────────────────────────────
    display_name = fields.Char(
        string='الاسم',
        compute='_compute_display_name',
        store=True,
    )

    @api.depends('partner_id', 'full_name_ar', 'role')
    def _compute_display_name(self):
        role_label = dict(self._fields['role'].selection)
        for rec in self:
            name = rec.full_name_ar or (rec.partner_id.name if rec.partner_id else '')
            role = role_label.get(rec.role, '')
            rec.display_name = f"{name} ({role})" if name else role

    # ── Auto-populate from partner ────────────────────────────────────

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if not self.partner_id:
            return
        p = self.partner_id
        self.full_name_ar = p.name
        self.mobile = p.mobile or p.phone
        self.email = p.email
        if hasattr(p, 'sa_national_id') and p.sa_national_id:
            self.id_number = p.sa_national_id
        if hasattr(p, 'sa_id_type') and p.sa_id_type:
            mapping = {
                'national_id': 'national_id',
                'iqama': 'iqama',
                'passport': 'passport',
                'gcc_id': 'gcc_id',
            }
            self.id_type = mapping.get(p.sa_id_type, 'national_id')
        if hasattr(p, 'sa_iban') and p.sa_iban:
            self.iban = p.sa_iban
        if hasattr(p, 'sa_cr_number') and p.sa_cr_number:
            self.cr_number = p.sa_cr_number

    # ── Validation ────────────────────────────────────────────────────

    @api.constrains('id_number', 'id_type')
    def _check_id_number(self):
        for rec in self:
            if not rec.id_number:
                continue
            if rec.id_type == 'national_id' and not re.fullmatch(r'1\d{9}', rec.id_number):
                raise ValidationError(
                    _('الهوية الوطنية يجب أن تبدأ بـ 1 وتتكون من 10 أرقام')
                )
            if rec.id_type == 'iqama' and not re.fullmatch(r'2\d{9}', rec.id_number):
                raise ValidationError(
                    _('رقم الإقامة يجب أن يبدأ بـ 2 وتتكون من 10 أرقام')
                )

    @api.constrains('iban')
    def _check_iban(self):
        for rec in self:
            if rec.iban and not re.fullmatch(r'SA\w{22}', rec.iban):
                raise ValidationError(
                    _('رقم الآيبان السعودي يجب أن يبدأ بـ SA ويتكون من 24 حرفاً')
                )

    @api.constrains('role', 'proxy_doc')
    def _check_proxy_doc(self):
        representative_roles = {'lessor_representative', 'tenant_representative'}
        for rec in self:
            if rec.role in representative_roles and not rec.proxy_doc:
                # Warning only — don't block save, validate at submission time
                pass

    def validate_for_submission(self):
        """Called by lifecycle service before API calls."""
        self.ensure_one()
        errors = []

        if self.entity_type == 'individual':
            if not self.id_number:
                errors.append(_('رقم الهوية'))
            if not self.mobile:
                errors.append(_('رقم الجوال'))
            if not self.full_name_ar:
                errors.append(_('الاسم الكامل'))

        if self.entity_type == 'organization':
            if not self.cr_number and not self.unified_number:
                errors.append(_('رقم السجل التجاري أو الرقم الموحد'))

        if self.role == 'lessor' and not self.iban:
            errors.append(_('رقم الآيبان (مطلوب للمؤجر)'))

        representative_roles = {'lessor_representative', 'tenant_representative'}
        if self.role in representative_roles and not self.proxy_doc:
            errors.append(_('وثيقة التوكيل (مطلوبة للممثل)'))

        if errors:
            role_label = dict(self._fields['role'].selection).get(self.role, self.role)
            raise ValidationError(
                _('بيانات %s غير مكتملة:\n• %s')
                % (role_label, '\n• '.join(errors))
            )
