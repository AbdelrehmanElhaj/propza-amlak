from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import date


class SaPaymentWizard(models.TransientModel):
    _name = 'sa.payment.wizard'
    _description = 'تسجيل دفعة إيجار'

    rent_payment_id = fields.Many2one('sa.rent.payment', string='الدفعة', required=True)
    amount_due = fields.Float(related='rent_payment_id.amount', string='المبلغ المستحق', readonly=True)
    amount_paid = fields.Float(string='المبلغ المدفوع', required=True)
    payment_date = fields.Date(string='تاريخ الدفع', default=fields.Date.today, required=True)
    payment_method = fields.Selection([
        ('sadad',         'SADAD'),
        ('mada',          'مدى'),
        ('bank_transfer', 'تحويل بنكي'),
        ('cheque',        'شيك'),
        ('cash',          'نقداً'),
    ], string='طريقة الدفع', required=True, default='bank_transfer')
    reference = fields.Char(string='رقم المرجع / الشيك / SADAD')
    notes = fields.Text(string='ملاحظات')

    @api.onchange('rent_payment_id')
    def _onchange_payment(self):
        if self.rent_payment_id:
            self.amount_paid = self.rent_payment_id.balance

    create_invoice = fields.Boolean(
        string='إنشاء فاتورة محاسبية',
        default=True,
        help='تُنشئ فاتورة (account.move) لربط الدفعة بالدفاتر المحاسبية والـ VAT'
    )

    def action_register_payment(self):
        self.ensure_one()
        payment = self.rent_payment_id
        if self.amount_paid <= 0:
            raise UserError(_('يجب إدخال مبلغ أكبر من صفر'))

        vals = {
            'payment_date': self.payment_date,
            'payment_method': self.payment_method,
            'amount_paid': (payment.amount_paid or 0) + self.amount_paid,
        }

        if self.payment_method == 'sadad':
            vals['sadad_number'] = self.reference
        elif self.payment_method == 'cheque':
            vals['cheque_number'] = self.reference
        elif self.payment_method == 'bank_transfer':
            vals['bank_ref'] = self.reference

        # تحديد الحالة
        total_paid = vals['amount_paid']
        if total_paid >= payment.amount:
            vals['state'] = 'paid'
        else:
            vals['state'] = 'partial'

        payment.write(vals)

        # ─── ربط محاسبي: إنشاء فاتورة إن لم تكن موجودة ───────────
        invoice_msg = ''
        if self.create_invoice and not payment.move_id and payment.payment_type == 'rent':
            try:
                payment.action_create_invoice()
                invoice_msg = _(' وأُصدرت الفاتورة %s') % (
                    payment.move_id.name or '-'
                )
            except Exception as e:
                # لا نوقف العملية لو فشلت الفاتورة — يمكن إصدارها يدوياً لاحقاً
                invoice_msg = _(' (تعذّر إصدار الفاتورة: %s)') % str(e)[:120]

        # ─── توفيق المدفوعات: account.payment + reconcile ────────
        if payment.move_id and payment.move_id.state == 'posted' \
                and payment.amount_paid and payment.move_id.payment_state not in ('paid', 'in_payment'):
            try:
                payment._create_account_payment_and_reconcile()
            except Exception:
                pass  # silent — invoice exists, reconciliation can be redone manually

        payment.tenancy_id.message_post(
            body=_('تم تسجيل دفعة %s ريال بتاريخ %s عبر %s%s') % (
                self.amount_paid, self.payment_date,
                dict(self._fields['payment_method'].selection).get(self.payment_method),
                invoice_msg,
            ),
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('تم تسجيل الدفعة'),
                'message': _('تم تسجيل %s ريال بنجاح') % self.amount_paid,
                'type': 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
