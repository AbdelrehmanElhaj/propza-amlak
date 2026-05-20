from odoo import models, fields, api, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta
from datetime import date


class SaRentPayment(models.Model):
    """
    جدول دفعات الإيجار السعودي
    يُولَّد تلقائياً عند تأكيد الإيجار
    """
    _name = 'sa.rent.payment'
    _description = 'دفعة إيجار'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'due_date asc'

    name = fields.Char(string='رقم الدفعة', readonly=True,
                       default=lambda self: _('جديد'))
    tenancy_id = fields.Many2one(
        'property.tenancy', string='عقد الإيجار',
        required=True, ondelete='cascade'
    )
    property_id = fields.Many2one(
        related='tenancy_id.property_id',
        string='العقار', store=True
    )
    tenant_id = fields.Many2one(
        related='tenancy_id.partner_id',
        string='المستأجر', store=True
    )

    # ─── بيانات الدفعة ───────────────────────────────────────────
    due_date = fields.Date(string='تاريخ الاستحقاق', required=True)
    amount = fields.Float(string='المبلغ (ريال)', required=True)
    payment_type = fields.Selection([
        ('rent',    'إيجار'),
        ('deposit', 'وديعة ضمان'),
        ('penalty', 'غرامة تأخير'),
        ('other',   'أخرى'),
    ], string='نوع الدفعة', default='rent', required=True)

    # ─── حالة الدفعة ─────────────────────────────────────────────
    state = fields.Selection([
        ('pending',     'في الانتظار'),
        ('overdue',     'متأخرة'),
        ('paid',        'مدفوعة'),
        ('partial',     'مدفوعة جزئياً'),
        ('cancelled',   'ملغاة'),
    ], string='الحالة', default='pending', tracking=True)

    # ─── بيانات الدفع ────────────────────────────────────────────
    payment_date = fields.Date(string='تاريخ الدفع', tracking=True)
    payment_method = fields.Selection([
        ('sadad',         'SADAD'),
        ('mada',          'مدى'),
        ('bank_transfer', 'تحويل بنكي'),
        ('cheque',        'شيك'),
        ('cash',          'نقداً'),
    ], string='طريقة الدفع', tracking=True)
    amount_paid = fields.Float(string='المبلغ المدفوع (ريال)', tracking=True)
    sadad_number = fields.Char(string='رقم SADAD', tracking=True)
    cheque_number = fields.Char(string='رقم الشيك', tracking=True)
    bank_ref = fields.Char(string='رقم المرجع البنكي', tracking=True)
    payment_id = fields.Many2one('account.payment', string='سند الدفع', tracking=True)

    # ─── ربط الفوترة (Accounting / GL) ──────────────────────────
    move_id = fields.Many2one(
        'account.move', string='الفاتورة',
        readonly=True, copy=False, tracking=True,
        help='الفاتورة الصادرة لهذه الدفعة (account.move)'
    )
    move_state = fields.Selection(
        related='move_id.state', string='حالة الفاتورة', store=False
    )

    # ─── Computed ────────────────────────────────────────────────
    days_overdue = fields.Integer(
        string='أيام التأخير',
        compute='_compute_days_overdue', store=True,
    )
    penalty_amount = fields.Float(
        string='غرامة التأخير',
        compute='_compute_penalty', store=True,
    )
    balance = fields.Float(
        string='الرصيد المتبقي',
        compute='_compute_balance', store=True,
    )
    period_label = fields.Char(
        string='الفترة',
        compute='_compute_period_label'
    )

    @api.depends('due_date', 'state')
    def _compute_days_overdue(self):
        today = date.today()
        for rec in self:
            if rec.state in ('pending', 'partial') and rec.due_date and rec.due_date < today:
                rec.days_overdue = (today - rec.due_date).days
            else:
                rec.days_overdue = 0

    @api.depends('amount', 'days_overdue')
    def _compute_penalty(self):
        """غرامة تأخير 2% شهرياً وفق الأعراف السعودية"""
        for rec in self:
            if rec.days_overdue > 0:
                monthly_rate = 0.02
                daily_rate = monthly_rate / 30
                rec.penalty_amount = rec.amount * daily_rate * rec.days_overdue
            else:
                rec.penalty_amount = 0

    @api.depends('amount', 'amount_paid')
    def _compute_balance(self):
        for rec in self:
            rec.balance = rec.amount - (rec.amount_paid or 0)

    @api.depends('due_date', 'payment_type')
    def _compute_period_label(self):
        months_ar = {
            1: 'يناير', 2: 'فبراير', 3: 'مارس', 4: 'أبريل',
            5: 'مايو', 6: 'يونيو', 7: 'يوليو', 8: 'أغسطس',
            9: 'سبتمبر', 10: 'أكتوبر', 11: 'نوفمبر', 12: 'ديسمبر'
        }
        for rec in self:
            if rec.due_date:
                month = months_ar.get(rec.due_date.month, '')
                rec.period_label = f"{month} {rec.due_date.year}"
            else:
                rec.period_label = ''

    # ─── Sequence ────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('جديد')) == _('جديد'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'sa.rent.payment') or _('جديد')
        return super().create(vals_list)

    # ─── Actions ─────────────────────────────────────────────────
    def action_mark_paid(self):
        for rec in self:
            if rec.state in ('cancelled',):
                raise UserError(_('لا يمكن تسجيل دفع لدفعة ملغاة'))
            rec.write({
                'state': 'paid',
                'payment_date': date.today(),
                'amount_paid': rec.amount,
            })

    def action_mark_overdue(self):
        """يُستدعى من الـ cron"""
        today = date.today()
        overdue = self.search([
            ('state', 'in', ['pending', 'partial']),
            ('due_date', '<', today),
        ])
        overdue.write({'state': 'overdue'})
        return len(overdue)

    def action_cancel(self):
        self.state = 'cancelled'

    def action_open_payment_wizard(self):
        return {
            'name': _('تسجيل دفعة'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_rent_payment_id': self.id},
        }

    # ─── Accounting integration: invoice generation ─────────────
    def _get_rental_income_account(self):
        """Locate the 'Space Rental Income' account from the Saudi chart.
        Falls back to the sales journal default if not found.
        """
        co = self.env.company
        # Prefer the explicit 'Space Rental Income' (code 500007 in l10n_sa)
        acc = self.env['account.account'].search([
            ('code', '=', '500007'),
            ('company_id', '=', co.id),
        ], limit=1)
        if acc:
            return acc
        # Fallback: sales journal default
        journal = self.env['account.journal'].search([
            ('type', '=', 'sale'), ('company_id', '=', co.id)
        ], limit=1)
        return journal.default_account_id

    def _get_tax_for_tenancy(self):
        """Pick the right VAT based on contract type.

        Commercial -> 15% VAT (account.2_sa_sales_tax_15)
        Residential -> 0% Exempt Services (account.2_sa_export_services_tax_0)
                       per ZATCA: residential rentals are VAT-exempt in KSA.
        """
        contract_type = self.tenancy_id.sa_contract_type or 'residential'
        if contract_type == 'commercial':
            tax = self.env['account.tax'].search([
                ('amount', '=', 15.0),
                ('type_tax_use', '=', 'sale'),
                ('active', '=', True),
            ], limit=1)
        else:
            # residential = service-rental, exempt from VAT in KSA.
            # Prefer '0% EX S' (Services) — fall back to any 0% exempt sale tax.
            tax = self.env['account.tax'].search([
                ('amount', '=', 0.0),
                ('type_tax_use', '=', 'sale'),
                ('active', '=', True),
                ('name', 'ilike', 'EX S'),
            ], limit=1)
            if not tax:
                tax = self.env['account.tax'].search([
                    ('amount', '=', 0.0),
                    ('type_tax_use', '=', 'sale'),
                    ('active', '=', True),
                    ('name', 'ilike', 'EX'),
                ], limit=1)
        return tax

    def _prepare_invoice_vals(self):
        self.ensure_one()
        co = self.env.company
        journal = self.env['account.journal'].search([
            ('type', '=', 'sale'), ('company_id', '=', co.id)
        ], limit=1)
        if not journal:
            raise UserError(_('لا توجد يومية مبيعات لشركة %s') % co.name)

        partner = self.tenancy_id.partner_id
        income_acc = self._get_rental_income_account()
        tax = self._get_tax_for_tenancy()

        period = self.period_label or ''
        prop_name = self.property_id.display_name or ''
        line_name = _('إيجار %s — %s') % (prop_name, period) if period else \
                    _('إيجار %s') % prop_name

        line_vals = {
            'name': line_name,
            'quantity': 1.0,
            'price_unit': self.amount,
            'account_id': income_acc.id if income_acc else False,
        }
        if tax:
            line_vals['tax_ids'] = [(6, 0, [tax.id])]

        # Invoice date can't be in the future — Odoo enforces invoice_date <= today.
        # If the rent is due later (early payment), use today as invoice date.
        today = fields.Date.context_today(self)
        inv_date = self.due_date or today
        if inv_date and inv_date > today:
            inv_date = today

        return {
            'move_type': 'out_invoice',
            'company_id': co.id,
            'partner_id': partner.id,
            'invoice_date': inv_date,
            'date': inv_date,
            'journal_id': journal.id,
            'currency_id': journal.currency_id.id or co.currency_id.id,
            'ref': self.name or '',
            'invoice_line_ids': [(0, 0, line_vals)],
        }

    def action_create_invoice(self):
        """Create + post an account.move (customer invoice) for this payment."""
        for rec in self:
            if rec.move_id and rec.move_id.state != 'cancel':
                raise UserError(_(
                    'الفاتورة موجودة بالفعل: %s'
                ) % rec.move_id.name)
            if rec.payment_type == 'deposit':
                # deposits are not invoiced as revenue; user can override later
                pass
            move = self.env['account.move'].create(rec._prepare_invoice_vals())
            try:
                move.action_post()
            except Exception as e:
                # leave as draft for manual review
                rec.move_id = move.id
                raise UserError(_('فشل ترحيل الفاتورة: %s') % str(e)[:200])
            rec.move_id = move.id
            rec.tenancy_id.message_post(
                body=_('تم إصدار فاتورة %s بقيمة %s ريال للدفعة %s') % (
                    move.name, move.amount_total, rec.name
                ),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )
        return True

    # ─── Payment + Reconciliation ───────────────────────────────
    def _get_payment_journal(self):
        """Pick the right account.journal for an inbound payment based on method."""
        co = self.env.company
        method = self.payment_method or 'bank_transfer'
        # Cash payments -> cash journal; everything else (sadad/mada/bank/cheque) -> bank journal
        jtype = 'cash' if method == 'cash' else 'bank'
        journal = self.env['account.journal'].search([
            ('company_id', '=', co.id), ('type', '=', jtype),
        ], limit=1)
        # Fallback to any inbound-capable journal
        if not journal:
            journal = self.env['account.journal'].search([
                ('company_id', '=', co.id), ('type', 'in', ('bank', 'cash')),
            ], limit=1)
        return journal

    def _create_account_payment_and_reconcile(self):
        """Register an account.payment, post it, and reconcile with the
        linked invoice's receivable line. No-op if move_id missing or
        already fully reconciled.
        """
        for rec in self:
            if not rec.move_id or rec.move_id.state != 'posted':
                continue
            if rec.move_id.payment_state in ('paid', 'in_payment', 'reversed'):
                continue
            paid_amount = rec.amount_paid or 0.0
            if paid_amount <= 0:
                continue
            journal = rec._get_payment_journal()
            if not journal:
                continue
            # The tenant pays rent + VAT (commercial). amount_paid here is
            # the pre-VAT figure. Scale up to the invoice total so the
            # reconciliation fully clears the invoice.
            inv_total = rec.move_id.amount_total or paid_amount
            if rec.amount > 0:
                ratio = paid_amount / rec.amount
                ap_amount = inv_total * ratio
            else:
                ap_amount = paid_amount
            ap = self.env['account.payment'].create({
                'payment_type': 'inbound',
                'partner_type': 'customer',
                'partner_id': rec.tenancy_id.partner_id.id,
                'amount': ap_amount,
                'date': rec.payment_date or fields.Date.context_today(self),
                'journal_id': journal.id,
                'ref': rec.name or rec.move_id.name or '',
                'company_id': self.env.company.id,
            })
            try:
                ap.action_post()
            except Exception:
                continue
            # Match payment receivable line with invoice receivable line(s)
            inv_recv = rec.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable'
                and not l.reconciled
            )
            pay_recv = ap.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable'
                and not l.reconciled
            )
            try:
                (inv_recv | pay_recv).reconcile()
            except Exception:
                pass
            rec.payment_id = ap.id
        return True

    def action_create_invoice_and_reconcile(self):
        """Helper: create invoice, then reconcile if payment was received."""
        self.action_create_invoice()
        # Only reconcile if amount_paid > 0 and the payment is in paid/partial state
        paid_or_partial = self.filtered(lambda r: r.state in ('paid', 'partial')
                                        and r.amount_paid)
        if paid_or_partial:
            paid_or_partial._create_account_payment_and_reconcile()
        return True

    def action_view_invoice(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_('لا توجد فاتورة لهذه الدفعة بعد'))
        return {
            'name': _('الفاتورة'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
        }


class PropertyTenancyCycle(models.Model):
    """
    امتداد الإيجار — يُضيف دورة الدفع الكاملة
    """
    _inherit = 'property.tenancy'

    # ─── جدول الدفعات ────────────────────────────────────────────
    sa_payment_ids = fields.One2many(
        'sa.rent.payment', 'tenancy_id',
        string='جدول الدفعات'
    )
    sa_payment_count = fields.Integer(
        compute='_compute_payment_stats',
        string='عدد الدفعات'
    )
    sa_paid_count = fields.Integer(
        compute='_compute_payment_stats',
        string='دفعات مسددة'
    )
    sa_overdue_count = fields.Integer(
        compute='_compute_payment_stats',
        string='دفعات متأخرة'
    )
    sa_total_due = fields.Float(
        compute='_compute_payment_stats',
        string='إجمالي المستحق (ريال)'
    )
    sa_total_paid = fields.Float(
        compute='_compute_payment_stats',
        string='إجمالي المدفوع (ريال)'
    )
    sa_total_balance = fields.Float(
        compute='_compute_payment_stats',
        string='الرصيد المتبقي (ريال)'
    )

    # ─── حالة دورة الإيجار ───────────────────────────────────────
    sa_cycle_state = fields.Selection([
        ('draft',       'مسودة'),
        ('confirmed',   'مؤكد'),
        ('ejar_sent',   'أُرسل لإيجار'),
        ('active',      'نشط'),
        ('expiring',    'ينتهي قريباً'),
        ('ended',       'منتهي'),
        ('renewed',     'مجدد'),
    ], string='حالة دورة الإيجار', default='draft', tracking=True)

    sa_days_to_expiry = fields.Integer(
        compute='_compute_days_to_expiry',
        string='أيام حتى الانتهاء'
    )

    @api.depends('sa_payment_ids', 'sa_payment_ids.state',
                 'sa_payment_ids.amount', 'sa_payment_ids.amount_paid')
    def _compute_payment_stats(self):
        for rec in self:
            payments = rec.sa_payment_ids.filtered(
                lambda p: p.state != 'cancelled' and p.payment_type == 'rent'
            )
            rec.sa_payment_count = len(payments)
            rec.sa_paid_count = len(payments.filtered(lambda p: p.state == 'paid'))
            rec.sa_overdue_count = len(payments.filtered(lambda p: p.state == 'overdue'))
            rec.sa_total_due = sum(payments.mapped('amount'))
            rec.sa_total_paid = sum(payments.mapped('amount_paid'))
            rec.sa_total_balance = rec.sa_total_due - rec.sa_total_paid

    @api.depends('end_date')
    def _compute_days_to_expiry(self):
        today = date.today()
        for rec in self:
            if rec.end_date:
                rec.sa_days_to_expiry = (rec.end_date - today).days
            else:
                rec.sa_days_to_expiry = 0

    # ─── توليد جدول الدفعات ──────────────────────────────────────
    def action_generate_payment_schedule(self):
        self.ensure_one()
        if not self.start_date or not self.end_date:
            raise UserError(_('يجب تحديد تاريخ البداية والنهاية'))
        if not self.rent_amount:
            raise UserError(_('يجب تحديد قيمة الإيجار'))

        # حذف الدفعات القديمة غير المدفوعة
        self.sa_payment_ids.filtered(
            lambda p: p.state in ('pending', 'overdue')
        ).unlink()

        schedule = self.sa_payment_schedule or 'monthly'
        intervals = {
            'monthly':      relativedelta(months=1),
            'quarterly':    relativedelta(months=3),
            'semi_annual':  relativedelta(months=6),
            'annual':       relativedelta(years=1),
            'one_time':     None,
        }

        payments_data = []

        if schedule == 'one_time':
            payments_data.append({
                'tenancy_id': self.id,
                'due_date': self.start_date,
                'amount': self.rent_amount * self._get_total_months(),
                'payment_type': 'rent',
            })
        else:
            interval = intervals.get(schedule, relativedelta(months=1))
            amount_per_period = self._get_period_amount(schedule)
            current = self.start_date
            while current <= self.end_date:
                payments_data.append({
                    'tenancy_id': self.id,
                    'due_date': current,
                    'amount': amount_per_period,
                    'payment_type': 'rent',
                })
                current = current + interval

        # إضافة الوديعة
        if self.deposit_amount:
            payments_data.insert(0, {
                'tenancy_id': self.id,
                'due_date': self.start_date,
                'amount': self.deposit_amount,
                'payment_type': 'deposit',
            })

        self.env['sa.rent.payment'].create(payments_data)
        self.sa_cycle_state = 'confirmed'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('تم توليد جدول الدفعات'),
                'message': _('تم إنشاء %d دفعة') % len(payments_data),
                'type': 'success',
            }
        }

    def _get_total_months(self):
        if self.start_date and self.end_date:
            delta = relativedelta(self.end_date, self.start_date)
            return delta.years * 12 + delta.months + 1
        return 12

    def _get_period_amount(self, schedule):
        monthly = self.rent_amount
        return {
            'monthly':      monthly,
            'quarterly':    monthly * 3,
            'semi_annual':  monthly * 6,
            'annual':       monthly * 12,
        }.get(schedule, monthly)

    # ─── إرسال لإيجار من الإيجار مباشرة ─────────────────────────
    def action_send_to_ejar_full(self):
        self.ensure_one()
        if not self.tenant_national_id:
            raise UserError(_('يجب إدخال رقم هوية المستأجر'))
        if not self.property_id.sa_deed_number:
            raise UserError(_('يجب إدخال رقم صك العقار'))

        return self.tenancy_id.action_create_ejar_contract()

    # ─── إنهاء الإيجار ───────────────────────────────────────────
    def action_open_end_wizard(self):
        return {
            'name': _('إنهاء عقد الإيجار'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.end.tenancy.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_tenancy_id': self.id},
        }
