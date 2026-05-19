# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaEndTenancyWizard(models.TransientModel):
    """معالج إنهاء العقد + احتساب خصومات الضمان.

    يدعم:
        * استيراد بنود الخصم من معاينة التسليم (move_out)
        * احتساب الإرجاع تلقائياً = الضمان − إجمالي الخصومات
        * توليد account.payment (outbound) لإرجاع الباقي للمستأجر
        * توليد account.move (out_invoice) لإصدار فاتورة بقيمة الخصومات
        * تحديث حالة الضمان على عقد الإيجار (returned / partially_returned / forfeited)
    """
    _name = 'sa.end.tenancy.wizard'
    _description = 'إنهاء عقد الإيجار'

    # ─── Linkage ──────────────────────────────────────────────────
    tenancy_id = fields.Many2one(
        'property.tenancy', string='عقد الإيجار', required=True,
    )
    end_date = fields.Date(
        string='تاريخ الإنهاء الفعلي',
        default=fields.Date.context_today, required=True,
    )
    end_reason = fields.Selection([
        ('expired',     'انتهاء مدة العقد'),
        ('mutual',      'اتفاق مشترك'),
        ('tenant_exit', 'رغبة المستأجر'),
        ('owner_exit',  'رغبة المالك'),
        ('violation',   'مخالفة شروط العقد'),
    ], string='سبب الإنهاء', required=True, default='expired')

    property_condition = fields.Selection([
        ('excellent', 'ممتاز'),
        ('good',      'جيد'),
        ('fair',      'مقبول'),
        ('damaged',   'تلف'),
    ], string='حالة العقار عند التسليم', default='good')

    # ─── Inspection link ──────────────────────────────────────────
    move_out_inspection_id = fields.Many2one(
        'sa.property.inspection', string='معاينة التسليم',
        domain="[('tenancy_id','=',tenancy_id),('inspection_type','=','move_out')]",
        help='اختر معاينة التسليم لاستيراد بنود الخصم تلقائياً',
    )

    # ─── Money: deposit & deductions ──────────────────────────────
    deposit_amount = fields.Float(
        string='قيمة الضمان (ريال)',
        related='tenancy_id.deposit_amount', readonly=True,
    )
    deduction_line_ids = fields.One2many(
        'sa.end.tenancy.deduction.line', 'wizard_id',
        string='بنود الخصم',
    )
    total_deductions = fields.Float(
        string='إجمالي الخصومات (ريال)',
        compute='_compute_totals', store=False,
    )
    refund_amount = fields.Float(
        string='المبلغ المسترد للمستأجر (ريال)',
        compute='_compute_totals', store=False,
    )
    forfeit_remaining = fields.Boolean(
        string='مصادرة المتبقي (لا يُرجع شيء)',
        default=False,
        help='إذا فُعّل، يُحتسب كامل الضمان كمُصادَر بدلاً من إرجاعه',
    )

    # ─── Outstanding rent balance (already-existing rent payments) ─
    outstanding_balance = fields.Float(
        string='الرصيد المتبقي', compute='_compute_outstanding',
    )

    # ─── Output controls ──────────────────────────────────────────
    create_refund_payment = fields.Boolean(
        string='توليد سند إرجاع الضمان',
        default=True,
        help='يُنشئ account.payment outbound بقيمة الإرجاع',
    )
    create_deduction_invoice = fields.Boolean(
        string='توليد فاتورة بقيمة الخصومات',
        default=False,
        help='يُنشئ account.move (out_invoice) بقيمة إجمالي الخصومات على المستأجر',
    )

    notes = fields.Text(string='ملاحظات الإنهاء')

    # ─── Computed ─────────────────────────────────────────────────
    @api.depends('tenancy_id')
    def _compute_outstanding(self):
        for rec in self:
            rec.outstanding_balance = (
                rec.tenancy_id.sa_total_balance if rec.tenancy_id else 0.0
            )

    @api.depends('deduction_line_ids.amount',
                 'deposit_amount', 'forfeit_remaining')
    def _compute_totals(self):
        for rec in self:
            total_ded = sum(rec.deduction_line_ids.mapped('amount'))
            rec.total_deductions = total_ded
            if rec.forfeit_remaining:
                rec.refund_amount = 0.0
            else:
                rec.refund_amount = max(
                    (rec.deposit_amount or 0.0) - total_ded, 0.0
                )

    # ─── Actions ──────────────────────────────────────────────────
    def action_import_from_inspection(self):
        """استيراد بنود التلف من معاينة التسليم كخصومات."""
        self.ensure_one()
        if not self.move_out_inspection_id:
            raise UserError(_('الرجاء اختيار معاينة التسليم أولاً'))

        # Clear existing imported lines (preserve manually-added ones with no inspection_line_id)
        self.deduction_line_ids.filtered(
            lambda l: l.inspection_line_id
        ).unlink()

        Line = self.env['sa.end.tenancy.deduction.line']
        new_lines = []
        for ins_line in self.move_out_inspection_id.line_ids:
            if ins_line.damage_cost <= 0:
                continue
            # Map inspection line condition → deduction category
            cat = 'damage'
            if ins_line.condition == 'missing':
                cat = 'damage'
            elif ins_line.condition == 'needs_repair':
                cat = 'damage'
            description = _('%s — %s') % (
                dict(ins_line._fields['room'].selection).get(ins_line.room, ''),
                ins_line.item or '',
            )
            new_lines.append({
                'wizard_id':          self.id,
                'description':        description,
                'category':           cat,
                'amount':             ins_line.damage_cost,
                'inspection_line_id': ins_line.id,
            })

        if not new_lines:
            raise UserError(_('لا توجد بنود تلف في المعاينة المحددة'))

        Line.create(new_lines)

        # Re-open the wizard to refresh
        return {
            'type':      'ir.actions.act_window',
            'res_model': self._name,
            'res_id':    self.id,
            'view_mode': 'form',
            'target':    'new',
        }

    def action_end_tenancy(self):
        self.ensure_one()
        tenancy = self.tenancy_id

        # ── Sanity checks ─────────────────────────────────────────
        if self.outstanding_balance > 0:
            raise UserError(_(
                'يوجد رصيد إيجار متبقي غير مسدد: %s ريال. يجب تسوية الدفعات أولاً.'
            ) % self.outstanding_balance)
        if self.total_deductions > (self.deposit_amount or 0.0):
            raise UserError(_(
                'إجمالي الخصومات (%s ريال) يتجاوز قيمة الضمان (%s ريال). '
                'الفرق يحتاج فاتورة منفصلة على المستأجر.'
            ) % (self.total_deductions, self.deposit_amount))

        # ── Generate accounting artifacts BEFORE state change ────
        deduction_move = False
        refund_payment = False
        if self.create_deduction_invoice and self.total_deductions > 0:
            deduction_move = self._create_deduction_invoice()
        if self.create_refund_payment and self.refund_amount > 0:
            refund_payment = self._create_refund_payment()

        # ── Compute deposit_state ─────────────────────────────────
        deposit_amt = self.deposit_amount or 0.0
        if deposit_amt <= 0:
            new_state = tenancy.deposit_state  # nothing to do
        elif self.forfeit_remaining and self.total_deductions <= 0:
            new_state = 'forfeited'
        elif self.refund_amount >= deposit_amt:
            new_state = 'returned'
        elif self.refund_amount <= 0:
            new_state = 'forfeited'
        else:
            new_state = 'partially_returned'

        # ── Update tenancy ────────────────────────────────────────
        tenancy.write({
            'state':                    'closed',
            'sa_cycle_state':           'ended',
            'deposit_returned_amount':  (tenancy.deposit_returned_amount or 0.0)
                                        + self.refund_amount,
            'deposit_forfeited_amount': (tenancy.deposit_forfeited_amount or 0.0)
                                        + self.total_deductions,
            'deposit_state':            new_state,
        })
        # Free the property
        if tenancy.property_id and tenancy.property_id.state == 'on_rent':
            tenancy.property_id.write({'state': 'draft'})

        # ── Build chatter narrative ──────────────────────────────
        ded_summary = ''
        for line in self.deduction_line_ids:
            ded_summary += '<li>%s — %s ريال</li>' % (
                line.description or '/', line.amount
            )
        if ded_summary:
            ded_summary = '<ul>%s</ul>' % ded_summary

        body = _(
            '<p><b>تم إنهاء عقد الإيجار</b></p>'
            '<ul>'
            '<li>تاريخ الإنهاء: %s</li>'
            '<li>السبب: %s</li>'
            '<li>حالة العقار: %s</li>'
            '<li>الضمان: %s ريال</li>'
            '<li>إجمالي الخصومات: %s ريال</li>'
            '<li>المُسترد للمستأجر: %s ريال</li>'
            '<li>حالة الضمان: %s</li>'
            '</ul>'
            '%s'
        ) % (
            self.end_date,
            dict(self._fields['end_reason'].selection).get(self.end_reason),
            dict(self._fields['property_condition'].selection).get(self.property_condition),
            deposit_amt,
            self.total_deductions,
            self.refund_amount,
            dict(tenancy._fields['deposit_state'].selection).get(new_state),
            ded_summary,
        )
        tenancy.message_post(
            body=body, message_type='notification', subtype_xmlid='mail.mt_note',
        )

        # ── Build response action ────────────────────────────────
        msg = _('تم إنهاء عقد الإيجار بنجاح')
        if refund_payment:
            msg += _('. سند إرجاع: %s') % refund_payment.name
        if deduction_move:
            msg += _('. فاتورة خصومات: %s') % deduction_move.name

        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('تم إنهاء العقد'),
                'message': msg,
                'type':    'success',
                'next':    {'type': 'ir.actions.act_window_close'},
            }
        }

    # ─── Accounting helpers ──────────────────────────────────────
    def _get_payment_journal(self):
        """يومية البنك الافتراضية للإرجاع."""
        co = self.env.company
        return self.env['account.journal'].search([
            ('company_id', '=', co.id),
            ('type', 'in', ('bank', 'cash')),
        ], limit=1)

    def _get_sales_journal(self):
        co = self.env.company
        return self.env['account.journal'].search([
            ('company_id', '=', co.id), ('type', '=', 'sale'),
        ], limit=1)

    def _create_refund_payment(self):
        """يُنشئ account.payment outbound لإرجاع الضمان."""
        self.ensure_one()
        if self.refund_amount <= 0:
            return False
        journal = self._get_payment_journal()
        if not journal:
            raise UserError(_('لا توجد يومية بنك/نقد لإصدار سند الإرجاع'))
        ap = self.env['account.payment'].create({
            'payment_type': 'outbound',
            'partner_type': 'customer',
            'partner_id':   self.tenancy_id.partner_id.id,
            'amount':       self.refund_amount,
            'date':         self.end_date,
            'journal_id':   journal.id,
            'ref':          _('إرجاع ضمان — %s') % (self.tenancy_id.name or ''),
            'company_id':   self.env.company.id,
            'sa_tenancy_deposit_id': self.tenancy_id.id,
        })
        try:
            ap.action_post()
        except Exception:
            # leave as draft for manual review
            pass
        return ap

    def _create_deduction_invoice(self):
        """يُنشئ account.move (out_invoice) بقيمة الخصومات على المستأجر."""
        self.ensure_one()
        if self.total_deductions <= 0:
            return False
        journal = self._get_sales_journal()
        if not journal:
            raise UserError(_('لا توجد يومية مبيعات'))
        # Use rental income account as fallback
        income_acc = self.env['account.account'].search([
            ('code', '=', '500007'),
            ('company_id', '=', self.env.company.id),
        ], limit=1) or journal.default_account_id

        line_vals = []
        for line in self.deduction_line_ids:
            line_vals.append((0, 0, {
                'name':       line.description or _('خصم'),
                'quantity':   1.0,
                'price_unit': line.amount,
                'account_id': income_acc.id if income_acc else False,
            }))

        move = self.env['account.move'].create({
            'move_type':      'out_invoice',
            'company_id':     self.env.company.id,
            'partner_id':     self.tenancy_id.partner_id.id,
            'invoice_date':   self.end_date,
            'date':           self.end_date,
            'journal_id':     journal.id,
            'currency_id':    journal.currency_id.id or self.env.company.currency_id.id,
            'ref':            _('خصومات ضمان — %s') % (self.tenancy_id.name or ''),
            'invoice_line_ids': line_vals,
        })
        try:
            move.action_post()
        except Exception:
            pass
        return move


class SaEndTenancyDeductionLine(models.TransientModel):
    """سطر خصم من الضمان (يُولَّد يدوياً أو من معاينة التسليم)."""
    _name = 'sa.end.tenancy.deduction.line'
    _description = 'سطر خصم ضمان'
    _order = 'id'

    wizard_id = fields.Many2one(
        'sa.end.tenancy.wizard', string='المعالج',
        required=True, ondelete='cascade',
    )
    description = fields.Char(string='الوصف', required=True)
    category = fields.Selection([
        ('damage',       'تلف/كسر'),
        ('cleaning',     'تنظيف'),
        ('utility',      'فواتير خدمات'),
        ('penalty',      'غرامة'),
        ('unpaid_rent',  'إيجار غير مسدد'),
        ('key',          'مفاتيح/ريموت'),
        ('other',        'أخرى'),
    ], string='التصنيف', default='damage', required=True)
    amount = fields.Float(string='المبلغ (ريال)', required=True)
    inspection_line_id = fields.Many2one(
        'sa.property.inspection.line', string='بند المعاينة',
        ondelete='set null',
        help='البند الأصلي في معاينة التسليم (إن وُجد)',
    )
