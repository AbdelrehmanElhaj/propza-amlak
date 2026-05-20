from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
import math

_logger = logging.getLogger(__name__)


class EjarContract(models.Model):
    _name = 'ejar.contract'
    _description = 'Ejar Contract (عقد إيجار)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    # ── Company isolation ─────────────────────────────────────────────
    company_id = fields.Many2one(
        'res.company',
        string='الشركة',
        required=True,
        default=lambda self: self.env.company,
        ondelete='restrict',
        tracking=True,
        index=True,
    )

    # ── Identification ────────────────────────────────────────────────
    name = fields.Char(
        string='رقم المرجع',
        default=lambda self: _('مسودة'),
        readonly=True,
        copy=False,
    )

    # ── State machine ─────────────────────────────────────────────────
    ejar_status = fields.Selection([
        ('draft',       'مسودة'),
        ('building',    'جارٍ الإعداد'),
        ('ready',       'جاهز للإرسال'),
        ('submitting',  'جارٍ الإرسال'),
        ('submitted',   'بانتظار الموافقة'),
        ('approved',    'موافق عليه'),
        ('rejected',    'مرفوض'),
        ('expired',     'منتهي'),
        ('cancelled',   'ملغي'),
    ], string='الحالة', default='draft', tracking=True, copy=False, index=True)

    # Terminal states — no further mutations allowed
    _TERMINAL_STATES = {'expired', 'cancelled'}
    # States eligible for cron status polling
    _POLLABLE_STATES = {'submitted'}
    # States from which submission is valid
    _SUBMITTABLE_STATES = {'ready'}

    # ── Contract type ─────────────────────────────────────────────────
    contract_type = fields.Selection([
        ('residential', 'سكني'),
        ('commercial',  'تجاري'),
    ], string='نوع العقد', default='residential', required=True, tracking=True)

    contract_sub_type = fields.Selection([
        ('main',    'رئيسي'),
        ('renewal', 'تجديد'),
        ('sublease', 'تأجير من الباطن'),
    ], string='النوع الفرعي', default='main', required=True)

    use_type = fields.Selection([
        ('residential_families', 'سكن عائلي'),
        ('residential_singles',  'سكن للعزاب'),
        ('commercial',           'تجاري'),
        ('industrial',           'صناعي'),
    ], string='نوع الاستخدام', default='residential_families')

    # ── Relations ─────────────────────────────────────────────────────
    tenancy_id = fields.Many2one(
        'property.tenancy',
        string='الإيجار',
        ondelete='cascade',
        copy=False,
    )
    brokerage_profile_id = fields.Many2one(
        'ejar.brokerage.profile',
        string='ملف مكتب الوساطة',
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )

    # ── Party lists ───────────────────────────────────────────────────
    party_ids = fields.One2many(
        'ejar.contract.party',
        'contract_id',
        string='الأطراف',
        copy=True,
    )
    unit_ids = fields.One2many(
        'ejar.contract.unit',
        'contract_id',
        string='الوحدات',
        copy=True,
    )

    # ── Contract terms ────────────────────────────────────────────────
    start_date = fields.Date(string='تاريخ البداية', required=True, tracking=True)
    end_date = fields.Date(string='تاريخ الانتهاء', required=True, tracking=True)
    rent_amount = fields.Float(
        string='قيمة الإيجار السنوي (ريال)',
        required=True,
        digits=(16, 2),
        tracking=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.ref('base.SAR', raise_if_not_found=False),
        string='العملة',
    )
    payment_schedule = fields.Selection([
        ('monthly',     'شهري'),
        ('quarterly',   'ربع سنوي'),
        ('biannual',    'نصف سنوي'),
        ('annual',      'سنوي'),
    ], string='دورية الدفع', required=True, default='monthly', tracking=True)

    payment_option = fields.Selection([
        ('mada',          'مدى'),
        ('sadad',         'سداد'),
        ('cash',          'نقداً'),
        ('bank_transfer', 'تحويل بنكي'),
    ], string='طريقة الدفع', default='bank_transfer')

    sublease_allowed = fields.Boolean(string='يُسمح بالتأجير من الباطن', default=False)

    # ── Brokerage fee ─────────────────────────────────────────────────
    brokerage_fee = fields.Float(
        string='عمولة الوساطة (ريال)',
        digits=(16, 2),
        help='Max 2.5% of annual rent per RERA',
    )
    brokerage_fee_paid_by = fields.Selection([
        ('lessor',              'المؤجر'),
        ('tenant',              'المستأجر'),
        ('brokerage_office',    'مكتب الوساطة'),
    ], string='تحمّل عمولة الوساطة', default='lessor')

    ejar_fees_paid_by = fields.Selection([
        ('brokerage_office',    'مكتب الوساطة'),
        ('lessor',              'المؤجر'),
        ('tenant',              'المستأجر'),
    ], string='تحمّل رسوم إيجار', default='brokerage_office')

    # ── Documentation fee (computed) ──────────────────────────────────
    doc_fee = fields.Float(
        string='رسوم التوثيق (ريال)',
        compute='_compute_doc_fee',
        store=True,
    )

    # ── Signed document ───────────────────────────────────────────────
    signed_doc = fields.Binary(
        string='العقد الموقّع (PDF)',
        attachment=True,
        copy=False,
    )
    signed_doc_filename = fields.Char(
        string='اسم الملف',
        copy=False,
    )

    # ── Custom terms ──────────────────────────────────────────────────
    custom_terms = fields.Text(string='بنود خاصة')

    # ── Ejar platform references ──────────────────────────────────────
    ejar_contract_id = fields.Char(
        string='معرّف العقد في إيجار (UUID)',
        readonly=True,
        copy=False,
        index=True,
    )
    ejar_contract_number = fields.Char(
        string='رقم العقد في إيجار',
        readonly=True,
        copy=False,
    )

    # ── Rejection ─────────────────────────────────────────────────────
    rejection_reason = fields.Text(
        string='سبب الرفض',
        readonly=True,
        copy=False,
    )

    # ── Submission tracking ───────────────────────────────────────────
    submit_attempt = fields.Integer(
        string='عدد محاولات الإرسال',
        readonly=True,
        default=0,
        copy=False,
    )
    submit_error = fields.Text(
        string='آخر خطأ إرسال',
        readonly=True,
        copy=False,
    )
    ejar_last_sync = fields.Datetime(
        string='آخر مزامنة',
        readonly=True,
        copy=False,
    )
    next_poll_at = fields.Datetime(
        string='الاستطلاع التالي',
        readonly=True,
        copy=False,
        help='Cron will poll Ejar status at or after this datetime',
    )
    poll_count = fields.Integer(
        string='عدد الاستطلاعات',
        readonly=True,
        default=0,
        copy=False,
    )

    # ── Raw API storage ───────────────────────────────────────────────
    ejar_response_raw = fields.Text(
        string='استجابة إيجار الخام',
        readonly=True,
        copy=False,
    )

    # ── Webhook tracking ──────────────────────────────────────────────
    webhook_uuid = fields.Char(
        string='معرّف Webhook',
        readonly=True,
        copy=False,
        index=True,
    )
    webhook_delivered_at = fields.Datetime(
        string='وقت استقبال Webhook',
        readonly=True,
        copy=False,
    )
    webhook_event_type = fields.Selection([
        ('contract.approved', 'العقد موافق عليه'),
        ('contract.rejected', 'العقد مرفوض'),
        ('acknowledgement.completed', 'التحقق من البيانات اكتمل'),
        ('document.verification', 'التحقق من المستند'),
        ('status.update', 'تحديث الحالة'),
    ], string='نوع حدث Webhook', readonly=True, copy=False)
    webhook_correlation_id = fields.Char(
        string='معرّف تتبع Webhook',
        readonly=True,
        copy=False,
        index=True,
    )
    webhook_last_error_at = fields.Datetime(
        string='آخر خطأ في Webhook',
        readonly=True,
        copy=False,
    )
    webhook_last_error_msg = fields.Text(
        string='رسالة آخر خطأ في Webhook',
        readonly=True,
        copy=False,
    )

    # ── Computed ──────────────────────────────────────────────────────
    duration_years = fields.Float(
        string='المدة (سنوات)',
        compute='_compute_duration',
        store=True,
    )
    party_count = fields.Integer(
        string='الأطراف',
        compute='_compute_counts',
    )
    unit_count = fields.Integer(
        string='الوحدات',
        compute='_compute_counts',
    )
    log_count = fields.Integer(
        string='سجلات المزامنة',
        compute='_compute_counts',
    )
    has_lessor = fields.Boolean(compute='_compute_party_flags', store=True)
    has_tenant = fields.Boolean(compute='_compute_party_flags', store=True)
    has_unit = fields.Boolean(compute='_compute_unit_flag', store=True)
    is_ready_to_submit = fields.Boolean(
        string='جاهز للإرسال',
        compute='_compute_is_ready_to_submit',
    )

    # ── Rent freeze ───────────────────────────────────────────────────
    rent_freeze_warning = fields.Boolean(
        string='تحذير تجميد الإيجار',
        compute='_compute_rent_freeze_warning',
        store=False,
    )

    # ─── Sequence ────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('مسودة')) == _('مسودة'):
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('ejar.contract')
                    or _('مسودة')
                )
            # Auto-resolve brokerage profile if not set
            if not vals.get('brokerage_profile_id'):
                company_id = vals.get('company_id', self.env.company.id)
                profile = self.env['ejar.brokerage.profile'].search(
                    [('company_id', '=', company_id)], limit=1
                )
                if profile:
                    vals['brokerage_profile_id'] = profile.id
        return super().create(vals_list)

    # ─── Computed ────────────────────────────────────────────────────

    @api.depends('start_date', 'end_date')
    def _compute_duration(self):
        for rec in self:
            if rec.start_date and rec.end_date:
                delta = rec.end_date - rec.start_date
                rec.duration_years = round(delta.days / 365, 4)
            else:
                rec.duration_years = 0.0

    @api.depends('duration_years')
    def _compute_doc_fee(self):
        for rec in self:
            years = math.ceil(rec.duration_years) or 1
            rec.doc_fee = years * 125.0

    def _compute_counts(self):
        for rec in self:
            rec.party_count = len(rec.party_ids)
            rec.unit_count = len(rec.unit_ids)
            rec.log_count = self.env['ejar.sync.log'].search_count(
                [('contract_id', '=', rec.id)]
            )

    @api.depends('party_ids.role')
    def _compute_party_flags(self):
        for rec in self:
            roles = rec.party_ids.mapped('role')
            rec.has_lessor = 'lessor' in roles
            rec.has_tenant = 'tenant' in roles

    @api.depends('unit_ids')
    def _compute_unit_flag(self):
        for rec in self:
            rec.has_unit = bool(rec.unit_ids)

    @api.depends('has_lessor', 'has_tenant', 'has_unit', 'signed_doc',
                 'brokerage_profile_id', 'start_date', 'end_date', 'rent_amount')
    def _compute_is_ready_to_submit(self):
        for rec in self:
            rec.is_ready_to_submit = all([
                rec.has_lessor,
                rec.has_tenant,
                rec.has_unit,
                rec.signed_doc,
                rec.brokerage_profile_id,
                rec.start_date,
                rec.end_date,
                rec.rent_amount > 0,
            ])

    @api.depends('unit_ids.property_id.sa_city_id.rent_freeze',
                 'rent_amount')
    def _compute_rent_freeze_warning(self):
        for rec in self:
            freeze = False
            for unit in rec.unit_ids:
                city = getattr(unit.property_id, 'sa_city_id', None)
                if city and getattr(city, 'rent_freeze', False):
                    last_rent = getattr(unit.property_id, 'last_ejar_rent', 0)
                    if last_rent and rec.rent_amount > last_rent:
                        freeze = True
                        break
            rec.rent_freeze_warning = freeze

    # ─── Validation ──────────────────────────────────────────────────

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.end_date <= rec.start_date:
                raise ValidationError(_('تاريخ الانتهاء يجب أن يكون بعد تاريخ البداية'))

    @api.constrains('brokerage_fee', 'rent_amount')
    def _check_brokerage_fee_cap(self):
        for rec in self:
            if rec.brokerage_fee and rec.rent_amount:
                cap = rec.rent_amount * 0.025  # 2.5% RERA cap
                if rec.brokerage_fee > cap:
                    raise ValidationError(
                        _('عمولة الوساطة لا يجوز أن تتجاوز 2.5%% من قيمة الإيجار السنوي (%.2f ريال)')
                        % cap
                    )

    @api.constrains('ejar_status')
    def _check_state_transition(self):
        """Enforce allowed transitions — reads old value from DB."""
        allowed: dict[str, set] = {
            'draft':      {'building', 'cancelled'},
            'building':   {'ready', 'draft', 'cancelled'},
            'ready':      {'building', 'submitting', 'cancelled'},
            'submitting': {'submitted', 'ready'},
            'submitted':  {'approved', 'rejected', 'cancelled'},
            'approved':   {'expired', 'cancelled'},
            'rejected':   {'draft', 'cancelled'},
            'expired':    set(),
            'cancelled':  set(),
        }
        for rec in self:
            if not rec.id:
                continue
            old = rec._origin.ejar_status or 'draft'
            new = rec.ejar_status
            if old == new:
                continue
            if new not in allowed.get(old, set()):
                old_label = dict(self._fields['ejar_status'].selection).get(old, old)
                new_label = dict(self._fields['ejar_status'].selection).get(new, new)
                raise ValidationError(
                    _('الانتقال من "%s" إلى "%s" غير مسموح به') % (old_label, new_label)
                )

    # ─── State machine actions ────────────────────────────────────────

    def action_start_building(self):
        """draft → building: user begins filling contract data."""
        self.ensure_one()
        self._assert_not_terminal()
        if self.ejar_status != 'draft':
            raise UserError(_('يمكن بدء الإعداد فقط من حالة المسودة'))
        self._set_status('building')
        self.message_post(body=_('بدأ إعداد العقد'))

    def action_mark_ready(self):
        """building → ready: all data is complete."""
        self.ensure_one()
        self._assert_not_terminal()
        if self.ejar_status != 'building':
            raise UserError(_('العقد يجب أن يكون في مرحلة الإعداد'))
        self._validate_ready_state()
        self._set_status('ready')
        self.message_post(body=_('اكتملت بيانات العقد — جاهز للإرسال'))

    def action_submit_to_ejar(self):
        """Opens the submission wizard."""
        self.ensure_one()
        self._assert_not_terminal()
        if self.ejar_status not in ('ready', 'building'):
            raise UserError(_('يمكن إرسال العقود الجاهزة أو التي في مرحلة الإعداد فقط'))
        # Auto-check readiness and move to ready if all data present
        if self.ejar_status == 'building' and self.is_ready_to_submit:
            self._set_status('ready')

        return {
            'type': 'ir.actions.act_window',
            'name': _('إرسال العقد إلى إيجار'),
            'res_model': 'ejar.submit.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_contract_id': self.id},
        }

    def action_upload_document(self):
        """Opens the document upload wizard."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('رفع العقد الموقّع'),
            'res_model': 'ejar.upload.doc.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_contract_id': self.id},
        }

    def action_check_ejar_status(self):
        """Manually trigger a status poll from Ejar."""
        self.ensure_one()
        if not self.ejar_contract_id:
            raise UserError(_('لا يوجد معرّف عقد إيجار للاستعلام عنه'))
        self._poll_ejar_status()

    def action_reset_to_draft(self):
        """rejected → draft: fix data and resubmit."""
        self.ensure_one()
        if self.ejar_status != 'rejected':
            raise UserError(_('يمكن إعادة الضبط للمسودة فقط من حالة الرفض'))
        self._set_status('draft')
        self.message_post(
            body=_('تمت إعادة ضبط العقد إلى مسودة لإعادة الإرسال')
        )

    def action_cancel(self):
        """Cancel from any non-terminal state."""
        self.ensure_one()
        if self.ejar_status in self._TERMINAL_STATES:
            raise UserError(_('لا يمكن إلغاء عقد في حالة نهائية'))
        self._set_status('cancelled')
        self.message_post(body=_('تم إلغاء العقد'))

    # ─── Internal helpers ─────────────────────────────────────────────

    def _set_status(self, new_status: str) -> None:
        """Write status, bypassing ORM constraint for programmatic transitions."""
        self.write({'ejar_status': new_status})

    def _assert_not_terminal(self) -> None:
        if self.ejar_status in self._TERMINAL_STATES:
            raise UserError(_('لا يمكن تعديل عقد في حالة نهائية'))

    def _validate_ready_state(self) -> None:
        errors = []
        if not self.has_lessor:
            errors.append(_('لم يُضَف المؤجر'))
        if not self.has_tenant:
            errors.append(_('لم يُضَف المستأجر'))
        if not self.has_unit:
            errors.append(_('لم تُضَف أي وحدة'))
        if not self.signed_doc:
            errors.append(_('لم يُرفع العقد الموقّع'))
        if not self.brokerage_profile_id:
            errors.append(_('لم يُحدَّد ملف مكتب الوساطة'))
        if errors:
            raise UserError(
                _('العقد غير مكتمل بعد:\n• %s') % '\n• '.join(errors)
            )

    def _poll_ejar_status(self) -> None:
        """Call Ejar API to get current contract status and update Odoo state."""
        from ..services.lifecycle_service import EjarContractLifecycleService
        svc = EjarContractLifecycleService(self.env)
        result = svc.poll_contract_status(self.id)

        self.write({
            'ejar_last_sync': fields.Datetime.now(),
            'poll_count': self.poll_count + 1,
        })

        ejar_state = result.get('ejar_state', '')
        state_map = {
            'registered': 'approved',
            'active':     'approved',
            'expired':    'expired',
            'terminated': 'cancelled',
            'rejected':   'rejected',
        }
        new_status = state_map.get(ejar_state)
        if new_status and new_status != self.ejar_status:
            if new_status == 'rejected':
                self.write({
                    'rejection_reason': result.get('rejection_reason', ''),
                })
                self.message_post(
                    body=_('رُفض العقد من إيجار. السبب: %s')
                    % result.get('rejection_reason', _('غير محدد')),
                    subtype_xmlid='mail.mt_note',
                )
            elif new_status == 'approved':
                ejar_num = result.get('ejar_contract_number', '')
                if ejar_num:
                    self.write({'ejar_contract_number': ejar_num})
                self.message_post(
                    body=_('تمت الموافقة على العقد من إيجار. رقم العقد: %s') % ejar_num,
                    subtype_xmlid='mail.mt_comment',
                )
            # Bypass state-transition constraint: use raw write via SQL for
            # cron/automated transitions that don't originate from user actions
            self.sudo().write({'ejar_status': new_status})

    # ─── Cron entry point ─────────────────────────────────────────────

    @api.model
    def _cron_poll_submitted_contracts(self) -> None:
        """
        Called every 30 minutes by ir.cron.
        Polls all contracts in 'submitted' state whose next_poll_at has passed.
        """
        import datetime
        now = fields.Datetime.now()
        contracts = self.search([
            ('ejar_status', 'in', list(self._POLLABLE_STATES)),
            '|',
            ('next_poll_at', '=', False),
            ('next_poll_at', '<=', now),
        ])

        _logger.info('Ejar status poll cron: %d contracts to check', len(contracts))

        for contract in contracts:
            try:
                contract._poll_ejar_status()
                # Schedule next poll in 30 minutes
                contract.sudo().write({
                    'next_poll_at': now + datetime.timedelta(minutes=30)
                })
            except Exception as exc:
                _logger.exception(
                    'Ejar status poll failed for contract %s: %s',
                    contract.name,
                    exc,
                )

    # ─── Smart buttons / navigation ──────────────────────────────────

    def action_view_parties(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('أطراف العقد'),
            'res_model': 'ejar.contract.party',
            'view_mode': 'list,form',
            'domain': [('contract_id', '=', self.id)],
            'context': {'default_contract_id': self.id},
        }

    def action_view_units(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('وحدات العقد'),
            'res_model': 'ejar.contract.unit',
            'view_mode': 'list,form',
            'domain': [('contract_id', '=', self.id)],
            'context': {'default_contract_id': self.id},
        }

    def action_view_sync_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('سجلات المزامنة'),
            'res_model': 'ejar.sync.log',
            'view_mode': 'list,form',
            'domain': [('contract_id', '=', self.id)],
        }
