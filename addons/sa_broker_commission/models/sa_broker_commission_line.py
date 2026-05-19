# -*- coding: utf-8 -*-
"""دفعة عمولة فردية — مع توليد فاتورة الموردين تلقائياً."""
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaBrokerCommissionLine(models.Model):
    _name = 'sa.broker.commission.line'
    _description = 'دفعة عمولة وسيط'
    _order = 'due_date asc'
    _inherit = ['mail.thread']

    commission_id = fields.Many2one(
        'sa.broker.commission', string='عقد العمولة',
        required=True, ondelete='cascade',
    )
    broker_partner_id = fields.Many2one(
        related='commission_id.broker_partner_id', store=True, readonly=True,
        string='الوسيط',
    )
    tenancy_id = fields.Many2one(
        related='commission_id.tenancy_id', store=True, readonly=True,
        string='عقد الإيجار',
    )
    description = fields.Char(string='الوصف', required=True)
    due_date = fields.Date(string='تاريخ الاستحقاق', required=True, tracking=True)
    amount = fields.Float(string='المبلغ (ريال)', required=True, tracking=True)

    state = fields.Selection([
        ('pending',   'في الانتظار'),
        ('billed',    'مفوتَر'),
        ('paid',      'مُسدَّد'),
        ('cancelled', 'ملغي'),
    ], string='الحالة', default='pending', required=True, tracking=True)

    bill_id = fields.Many2one(
        'account.move', string='فاتورة المورد',
        copy=False, readonly=True, tracking=True,
        help='Vendor bill (in_invoice) للوسيط لهذه الدفعة',
    )
    payment_id = fields.Many2one(
        'account.payment', string='سند الدفع',
        copy=False, readonly=True, tracking=True,
    )

    # ─── Actions ─────────────────────────────────────────────────
    def _get_commission_expense_account(self):
        """يبحث عن حساب مصروف العمولات. يقبل أي حساب expense."""
        co = self.env.company
        # Prefer 'commission' or 'broker' in name
        acc = self.env['account.account'].search([
            '|', ('name', 'ilike', 'commission'),
            ('name', 'ilike', 'broker'),
            ('account_type', '=', 'expense'),
            ('company_id', '=', co.id),
        ], limit=1)
        if acc:
            return acc
        # Fallback: any expense account
        acc = self.env['account.account'].search([
            ('account_type', '=', 'expense'),
            ('company_id', '=', co.id),
        ], limit=1)
        return acc

    def _get_purchase_journal(self):
        co = self.env.company
        return self.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', co.id),
        ], limit=1)

    def action_create_bill(self):
        """يُنشئ vendor bill (in_invoice) للوسيط لهذه الدفعة."""
        for rec in self:
            if rec.state in ('cancelled',):
                raise UserError(_('لا يمكن فوترة دفعة ملغاة'))
            if rec.bill_id and rec.bill_id.state != 'cancel':
                raise UserError(_(
                    'الفاتورة موجودة بالفعل: %s'
                ) % rec.bill_id.name)
            journal = rec._get_purchase_journal()
            if not journal:
                raise UserError(_('لا توجد يومية مشتريات لإصدار الفاتورة'))
            expense_acc = rec._get_commission_expense_account()

            line_vals = {
                'name': _('عمولة %s — %s') % (
                    rec.commission_id.name or '',
                    rec.description or '',
                ),
                'quantity': 1.0,
                'price_unit': rec.amount,
            }
            if expense_acc:
                line_vals['account_id'] = expense_acc.id

            move = self.env['account.move'].create({
                'move_type': 'in_invoice',
                'partner_id': rec.broker_partner_id.id,
                'invoice_date': rec.due_date,
                'date': rec.due_date,
                'journal_id': journal.id,
                'currency_id': journal.currency_id.id or self.env.company.currency_id.id,
                'ref': _('عمولة %s') % rec.commission_id.name,
                'invoice_line_ids': [(0, 0, line_vals)],
            })
            try:
                move.action_post()
            except Exception:
                pass
            rec.bill_id = move.id
            rec.state = 'billed'
            rec.commission_id._refresh_state_from_lines()
        return True

    def action_register_payment(self):
        """يفتح حوار account.payment.register لتسجيل الدفع."""
        self.ensure_one()
        if not self.bill_id:
            raise UserError(_('يجب إنشاء الفاتورة أولاً'))
        if self.bill_id.state != 'posted':
            raise UserError(_('الفاتورة ليست مُرحَّلة'))
        return {
            'name': _('تسجيل دفع للوسيط'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_model': 'account.move',
                'active_ids': [self.bill_id.id],
            },
        }

    def action_mark_paid(self):
        """يضع الحالة "مُسدَّد" يدوياً (للحالات بدون فاتورة)."""
        for rec in self:
            rec.state = 'paid'
            rec.commission_id._refresh_state_from_lines()
        return True

    def action_cancel(self):
        for rec in self:
            if rec.bill_id and rec.bill_id.state == 'posted':
                raise UserError(_(
                    'لا يمكن إلغاء دفعة لها فاتورة مُرحَّلة. الرجاء عكس الفاتورة أولاً.'
                ))
            rec.state = 'cancelled'
            rec.commission_id._refresh_state_from_lines()
        return True

    # Auto-update state when bill is paid
    def write(self, vals):
        res = super().write(vals)
        # If bill was set or its state changed to paid, mark as paid
        for rec in self:
            if rec.bill_id and rec.bill_id.payment_state == 'paid' and rec.state != 'paid':
                rec.state = 'paid'
                rec.commission_id._refresh_state_from_lines()
        return res
