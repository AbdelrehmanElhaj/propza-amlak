from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaTenancy(models.Model):
    """
    دورة الإيجار السعودية الكاملة
    من البحث → العقد → التوثيق في إيجار → التحصيل
    """
    _inherit = 'property.tenancy'

    # ─── هوية المستأجر ───────────────────────────────────────────
    # NOTE: tenant_id_type / tenant_national_id / tenant_id_expiry are
    # owned by l10n_sa_ejar (which is a hard dependency of sa_property).
    # We don't redefine them here — that produced duplicate-field warnings.
    sa_tenant_nationality = fields.Many2one(
        'res.country', string='الجنسية'
    )
    sa_tenant_phone = fields.Char(
        string='جوال المستأجر',
        related='partner_id.mobile', readonly=True
    )

    # ─── بيانات العقد السعودي ────────────────────────────────────
    sa_contract_type = fields.Selection([
        ('residential', 'سكني'),
        ('commercial',  'تجاري'),
    ], string='نوع العقد', default='residential', required=True)

    sa_payment_schedule = fields.Selection([
        ('monthly',     'شهري'),
        ('quarterly',   'ربع سنوي'),
        ('semi_annual', 'نصف سنوي'),
        ('annual',      'سنوي'),
        ('one_time',    'مرة واحدة'),
        ('flexible',    'مرن'),
    ], string='دورة الدفع', default='annual', required=True)

    # NOTE: payment_method moved to sa_property_base.
    # NOTE: sublease_allowed moved to l10n_sa_ejar.

    # ─── الوسيط العقاري ─────────────────────────────────────────
    sa_broker_id = fields.Many2one(
        'res.partner', string='الوسيط العقاري',
        domain="[('is_broker','=',True)]"
    )
    sa_broker_license = fields.Char(
        related='sa_broker_id.broker_license',
        string='رقم ترخيص الوسيط', readonly=True
    )

    # ─── رسوم إيجار ─────────────────────────────────────────────
    # NOTE: ejar_doc_fee, ejar_fee_bearer, ejar_contract_number all owned
    # by l10n_sa_ejar. We just expose the workflow status here.

    # ─── حالة إيجار ─────────────────────────────────────────────
    sa_ejar_status = fields.Selection([
        ('not_registered', 'غير مسجل'),
        ('pending',        'في انتظار التوثيق'),
        ('active',         'نشط'),
        ('expired',        'منتهي'),
        ('cancelled',      'ملغي'),
        ('renewed',        'مجدد'),
    ], string='حالة إيجار', default='not_registered', readonly=True)

    # ─── تجميد إيجار الرياض ─────────────────────────────────────
    sa_rent_freeze_warning = fields.Boolean(
        compute='_compute_sa_rent_freeze_warning'
    )

    # NOTE: sadad_invoice_number lives in l10n_sa_ejar.

    # ─── ملاحظات العقد ──────────────────────────────────────────
    sa_contract_notes = fields.Text(string='بنود إضافية في العقد')

    # ─── Computed ────────────────────────────────────────────────
    # NOTE: _compute_ejar_fee removed — l10n_sa_ejar's _compute_ejar_doc_fee
    # already handles the same calculation on its own ejar_doc_fee field.

    @api.depends('property_id', 'rent_amount',
                 'property_id.sa_rent_freeze', 'property_id.sa_last_ejar_rent')
    def _compute_sa_rent_freeze_warning(self):
        # Renamed from _compute_rent_freeze_warning to avoid clashing with
        # l10n_sa_ejar's same-named compute (which manages a different field).
        for rec in self:
            prop = rec.property_id
            if (prop and prop.sa_rent_freeze
                    and prop.sa_last_ejar_rent
                    and rec.rent_amount > prop.sa_last_ejar_rent):
                rec.sa_rent_freeze_warning = True
            else:
                rec.sa_rent_freeze_warning = False

    # ─── إرسال لإيجار ───────────────────────────────────────────
    def action_send_to_ejar(self):
        self.ensure_one()
        if not self.tenant_national_id:
            raise UserError(_('يجب إدخال رقم هوية المستأجر قبل الإرسال لإيجار'))
        if not self.property_id.sa_deed_number:
            raise UserError(_('يجب إدخال رقم صك العقار قبل الإرسال لإيجار'))

        return self.action_create_ejar_contract()
