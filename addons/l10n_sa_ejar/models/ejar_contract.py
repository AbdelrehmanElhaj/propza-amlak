from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class EjarContract(models.Model):
    _name = 'ejar.contract'
    _description = 'Ejar Contract (عقد إيجار)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    # ─── Identification ──────────────────────────────────────────
    name = fields.Char(
        string='رقم المرجع',
        default=lambda self: _('مسودة'),
        readonly=True, copy=False
    )
    ejar_contract_number = fields.Char(
        string='رقم عقد إيجار',
        readonly=True,
        help='Contract number assigned by Ejar platform'
    )
    ejar_status = fields.Selection([
        ('draft',       'مسودة'),
        ('pending',     'في انتظار التوثيق'),
        ('active',      'نشط'),
        ('expired',     'منتهي'),
        ('cancelled',   'ملغي'),
        ('renewed',     'مجدد'),
    ], string='حالة إيجار', default='draft',
        tracking=True
    )

    # ─── Relations ───────────────────────────────────────────────
    tenancy_id = fields.Many2one(
        'property.tenancy',
        string='الإيجار',
        ondelete='cascade'
    )
    property_id = fields.Many2one(
        'property.property',
        string='العقار',
        required=True
    )
    lessor_partner_id = fields.Many2one(
        'res.partner',
        string='المؤجر',
        required=True
    )
    tenant_partner_id = fields.Many2one(
        'res.partner',
        string='المستأجر',
        required=True
    )
    broker_partner_id = fields.Many2one(
        'res.partner',
        string='الوسيط العقاري',
        domain="[('is_broker', '=', True)]"
    )

    # ─── Contract Terms ──────────────────────────────────────────
    start_date = fields.Date(string='تاريخ البداية', required=True)
    end_date = fields.Date(string='تاريخ الانتهاء', required=True)
    rent_amount = fields.Float(string='قيمة الإيجار السنوي', required=True)
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.ref('base.SAR', raise_if_not_found=False)
    )
    payment_schedule = fields.Selection([
        ('flexible',    'مرن'),
        ('one_time',    'مرة واحدة'),
        ('monthly',     'شهري'),
        ('quarterly',   'ربع سنوي'),
        ('semi_annual', 'نصف سنوي'),
        ('annual',      'سنوي'),
    ], string='جدول الدفع', required=True, default='monthly')

    sublease_allowed = fields.Boolean(string='يُسمح بالتأجير من الباطن', default=False)

    # ─── Tenant Identity ─────────────────────────────────────────
    tenant_id_type = fields.Selection([
        ('national_id', 'هوية وطنية'),
        ('iqama',       'إقامة'),
        ('gcc',         'هوية خليجي'),
        ('passport',    'جواز سفر'),
    ], string='نوع الهوية', default='national_id')
    tenant_national_id = fields.Char(string='رقم الهوية')

    # ─── Documentation Fee ───────────────────────────────────────
    doc_fee = fields.Float(
        string='رسوم التوثيق (ريال)',
        compute='_compute_doc_fee'
    )
    fee_bearer = fields.Selection([
        ('lessor', 'المؤجر'),
        ('broker', 'مكتب الوساطة'),
    ], string='من يتحمل الرسوم', default='lessor')

    # ─── API Response Storage ────────────────────────────────────
    ejar_response_raw = fields.Text(
        string='استجابة API إيجار',
        readonly=True,
        help='Raw JSON response from Ejar API'
    )
    ejar_last_sync = fields.Datetime(
        string='آخر مزامنة مع إيجار',
        readonly=True
    )
    ejar_error_msg = fields.Char(
        string='رسالة خطأ إيجار',
        readonly=True
    )

    # ─── Computed ────────────────────────────────────────────────
    duration_years = fields.Float(
        string='المدة (سنوات)',
        compute='_compute_duration'
    )

    @api.depends('start_date', 'end_date')
    def _compute_duration(self):
        for rec in self:
            if rec.start_date and rec.end_date:
                delta = rec.end_date - rec.start_date
                rec.duration_years = round(delta.days / 365, 2)
            else:
                rec.duration_years = 0

    @api.depends('duration_years')
    def _compute_doc_fee(self):
        import math
        for rec in self:
            years = math.ceil(rec.duration_years) or 1
            rec.doc_fee = years * 125.0

    # ─── Sequence ────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('مسودة')) == _('مسودة'):
                vals['name'] = self.env['ir.sequence'].next_by_code('ejar.contract') or _('مسودة')
        return super().create(vals_list)

    # ─── Actions ─────────────────────────────────────────────────
    def action_submit_to_ejar(self):
        """Submit contract to Ejar API"""
        self.ensure_one()
        if self.ejar_status != 'draft':
            raise UserError(_('يمكن إرسال العقود في حالة مسودة فقط'))

        # Validate required fields
        if not self.property_id.deed_number:
            raise UserError(_('يجب إدخال رقم الصك قبل الإرسال لإيجار'))
        if not self.tenant_national_id:
            raise UserError(_('يجب إدخال رقم هوية المستأجر'))

        # Call API connector
        api = self.env['ejar.api.connector']
        result = api.submit_contract(self)

        if result.get('success'):
            self.write({
                'ejar_contract_number': result.get('contract_number'),
                'ejar_status': 'pending',
                'ejar_response_raw': str(result),
                'ejar_last_sync': fields.Datetime.now(),
                'ejar_error_msg': False,
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('تم الإرسال'),
                    'message': _('تم إرسال العقد لإيجار بنجاح. رقم العقد: %s') % result.get('contract_number'),
                    'type': 'success',
                }
            }
        else:
            self.write({
                'ejar_error_msg': result.get('error'),
                'ejar_last_sync': fields.Datetime.now(),
            })
            raise UserError(_('خطأ في إيجار: %s') % result.get('error'))

    def action_check_ejar_status(self):
        """Check contract status from Ejar API"""
        self.ensure_one()
        if not self.ejar_contract_number:
            raise UserError(_('لا يوجد رقم عقد إيجار للتحقق منه'))

        api = self.env['ejar.api.connector']
        result = api.get_contract_status(self.ejar_contract_number)

        if result.get('success'):
            status_map = {
                'ACTIVE': 'active',
                'PENDING': 'pending',
                'EXPIRED': 'expired',
                'CANCELLED': 'cancelled',
            }
            new_status = status_map.get(result.get('status'), self.ejar_status)
            self.write({
                'ejar_status': new_status,
                'ejar_last_sync': fields.Datetime.now(),
                'ejar_error_msg': False,
            })

    def action_cancel_ejar_contract(self):
        self.ensure_one()
        self.ejar_status = 'cancelled'
        self.message_post(body=_('تم إلغاء العقد'))
