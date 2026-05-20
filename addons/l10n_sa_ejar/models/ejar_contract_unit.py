from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class EjarContractUnit(models.Model):
    """
    A property unit attached to an Ejar contract.

    Stores both Odoo property references and the Ejar UUIDs
    returned after successful unit registration.
    """

    _name = 'ejar.contract.unit'
    _description = 'وحدة عقد إيجار'
    _order = 'id'
    _rec_name = 'unit_label'

    # ── Parent ────────────────────────────────────────────────────────
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

    # ── Property link ─────────────────────────────────────────────────
    property_id = fields.Many2one(
        'property.property',
        string='العقار',
        required=True,
        ondelete='restrict',
    )

    # ── Unit details ──────────────────────────────────────────────────
    unit_number = fields.Char(
        string='رقم الوحدة',
        required=True,
    )
    unit_type = fields.Selection([
        ('villa',       'فيلا'),
        ('apartment',   'شقة'),
        ('floor',       'طابق'),
        ('room',        'غرفة'),
        ('office',      'مكتب'),
        ('store',       'محل تجاري'),
        ('warehouse',   'مستودع'),
        ('land',        'أرض'),
    ], string='نوع الوحدة', default='apartment', required=True)

    area = fields.Float(
        string='المساحة (م²)',
        digits=(10, 2),
    )
    floor_number = fields.Integer(
        string='رقم الطابق',
        default=0,
    )
    bedrooms = fields.Integer(string='عدد غرف النوم')
    bathrooms = fields.Integer(string='عدد دورات المياه')
    parking_spaces = fields.Integer(string='عدد مواقف السيارات')

    finishing = fields.Selection([
        ('finished',        'مكتمل التشطيب'),
        ('semi_finished',   'نصف تشطيب'),
        ('unfinished',      'غير مشطّب'),
    ], string='مستوى التشطيب', default='finished')

    furnishing = fields.Selection([
        ('furnish_new',     'مفروش (جديد)'),
        ('furnish_old',     'مفروش (مستعمل)'),
        ('unfurnished',     'غير مفروش'),
    ], string='التأثيث', default='unfurnished')

    direction = fields.Selection([
        ('north', 'شمال'), ('south', 'جنوب'),
        ('east',  'شرق'),  ('west',  'غرب'),
    ], string='الاتجاه')

    # ── Deed / registration ───────────────────────────────────────────
    deed_number = fields.Char(
        related='property_id.deed_number',
        string='رقم الصك',
        readonly=True,
        store=True,
    )
    national_address_code = fields.Char(
        related='property_id.national_address_code',
        string='رمز العنوان الوطني',
        readonly=True,
        store=True,
    )

    # ── Ejar API references ───────────────────────────────────────────
    ejar_property_id = fields.Char(
        string='معرّف العقار في إيجار',
        readonly=True,
        copy=False,
        help='Property UUID assigned by Ejar',
    )
    ejar_unit_id = fields.Char(
        string='معرّف الوحدة في إيجار',
        readonly=True,
        copy=False,
        help='Unit UUID assigned by Ejar',
    )
    ejar_contract_unit_id = fields.Char(
        string='معرّف وحدة العقد في إيجار',
        readonly=True,
        copy=False,
        help='Contract-unit relationship UUID from Ejar',
    )

    # ── Sync state ────────────────────────────────────────────────────
    sync_state = fields.Selection([
        ('pending', 'في الانتظار'),
        ('synced',  'تمت المزامنة'),
        ('failed',  'فشل'),
    ], string='حالة المزامنة', default='pending', readonly=True)
    sync_error = fields.Text(string='خطأ المزامنة', readonly=True)

    # ── Display name ──────────────────────────────────────────────────
    unit_label = fields.Char(
        string='الوحدة',
        compute='_compute_unit_label',
        store=True,
    )

    @api.depends('property_id', 'unit_number', 'unit_type')
    def _compute_unit_label(self):
        type_labels = dict(self._fields['unit_type'].selection)
        for rec in self:
            prop = rec.property_id.name if rec.property_id else ''
            type_name = type_labels.get(rec.unit_type, '')
            unit = rec.unit_number or ''
            rec.unit_label = f"{prop} — {type_name} {unit}".strip(' —')

    # ── Auto-fill from property ───────────────────────────────────────

    @api.onchange('property_id')
    def _onchange_property_id(self):
        if not self.property_id:
            return
        p = self.property_id
        # Pre-fill unit type from property ejar_unit_type if available
        if hasattr(p, 'ejar_unit_type') and p.ejar_unit_type:
            type_map = {
                'residential': 'apartment',
                'commercial': 'office',
                'industrial': 'warehouse',
                'land': 'land',
            }
            self.unit_type = type_map.get(p.ejar_unit_type, 'apartment')

    # ── Validation ────────────────────────────────────────────────────

    @api.constrains('unit_number')
    def _check_unit_number(self):
        for rec in self:
            if not rec.unit_number or not rec.unit_number.strip():
                raise ValidationError(_('رقم الوحدة مطلوب'))

    def validate_for_submission(self):
        """Called by lifecycle service before API calls."""
        self.ensure_one()
        errors = []
        if not self.deed_number:
            errors.append(_('رقم الصك (مفقود في العقار)'))
        if not self.national_address_code:
            errors.append(_('رمز العنوان الوطني (مفقود في العقار)'))
        if not self.area:
            errors.append(_('مساحة الوحدة'))
        if errors:
            raise ValidationError(
                _('بيانات الوحدة %s غير مكتملة:\n• %s')
                % (self.unit_label, '\n• '.join(errors))
            )
