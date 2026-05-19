from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class PropertyTenancy(models.Model):
    _inherit = 'property.tenancy'

    # ─── Ejar Contract Info ──────────────────────────────────────
    ejar_contract_id = fields.Many2one(
        'ejar.contract',
        string='عقد إيجار',
        readonly=True
    )
    ejar_contract_number = fields.Char(
        string='رقم عقد إيجار',
        related='ejar_contract_id.ejar_contract_number',
        readonly=True, store=True
    )
    ejar_contract_status = fields.Selection(
        related='ejar_contract_id.ejar_status',
        string='حالة العقد في إيجار',
        readonly=True
    )

    # ─── Tenant ID Fields ────────────────────────────────────────
    tenant_id_type = fields.Selection([
        ('national_id', 'هوية وطنية'),
        ('iqama', 'إقامة'),
        ('gcc', 'هوية خليجي'),
        ('passport', 'جواز سفر'),
    ], string='نوع هوية المستأجر', default='national_id')

    tenant_national_id = fields.Char(
        string='رقم هوية المستأجر',
        help='National ID / Iqama number'
    )
    tenant_id_expiry = fields.Date(string='تاريخ انتهاء الهوية')

    # NOTE: payment_method moved to sa_property_base. Keep sadad invoice
    # number specific to Ejar/SADAD flow here.
    sadad_invoice_number = fields.Char(string='رقم فاتورة SADAD')

    # ─── Payment Schedule Type (Ejar standard) ───────────────────
    ejar_payment_schedule = fields.Selection([
        ('flexible', 'مرن'),
        ('one_time', 'مرة واحدة'),
        ('monthly', 'شهري'),
        ('quarterly', 'ربع سنوي'),
        ('semi_annual', 'نصف سنوي'),
        ('annual', 'سنوي'),
    ], string='جدول دفع إيجار', default='monthly')

    # ─── Sublease ────────────────────────────────────────────────
    sublease_allowed = fields.Boolean(
        string='يُسمح بالتأجير من الباطن',
        default=False
    )

    # ─── Documentation Fee ───────────────────────────────────────
    ejar_doc_fee = fields.Float(
        string='رسوم توثيق إيجار (ريال)',
        compute='_compute_ejar_doc_fee',
        help='125 SAR per year, partial years rounded up'
    )
    ejar_fee_bearer = fields.Selection([
        ('lessor', 'المؤجر'),
        ('broker', 'مكتب الوساطة'),
    ], string='من يتحمل رسوم التوثيق', default='lessor')

    # ─── Rent Freeze Check ───────────────────────────────────────
    rent_freeze_warning = fields.Boolean(
        compute='_compute_rent_freeze_warning'
    )

    @api.depends('duration', 'interval_type')
    def _compute_ejar_doc_fee(self):
        for rec in self:
            import math
            if rec.interval_type == 'years':
                years = rec.duration or 1
            else:
                years = math.ceil((rec.duration or 12) / 12)
            rec.ejar_doc_fee = years * 125.0

    @api.depends('property_id', 'property_id.rent_freeze_active',
                 'property_id.last_ejar_rent', 'rent_amount')
    def _compute_rent_freeze_warning(self):
        for rec in self:
            if (rec.property_id and rec.property_id.rent_freeze_active
                    and rec.property_id.last_ejar_rent
                    and rec.rent_amount > rec.property_id.last_ejar_rent):
                rec.rent_freeze_warning = True
            else:
                rec.rent_freeze_warning = False

    def action_create_ejar_contract(self):
        """Create Ejar contract record from tenancy"""
        self.ensure_one()
        if self.ejar_contract_id:
            raise UserError(_('عقد إيجار موجود بالفعل لهذا الإيجار'))

        contract = self.env['ejar.contract'].create({
            'tenancy_id': self.id,
            'property_id': self.property_id.id,
            'lessor_partner_id': self.owner_partner_id.id,
            'tenant_partner_id': self.partner_id.id,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'rent_amount': self.rent_amount,
            'payment_schedule': self.ejar_payment_schedule,
            'tenant_id_type': self.tenant_id_type,
            'tenant_national_id': self.tenant_national_id,
            'sublease_allowed': self.sublease_allowed,
            'fee_bearer': self.ejar_fee_bearer,
        })
        self.ejar_contract_id = contract.id
        return {
            'name': 'عقد إيجار',
            'type': 'ir.actions.act_window',
            'res_model': 'ejar.contract',
            'res_id': contract.id,
            'view_mode': 'form',
        }
