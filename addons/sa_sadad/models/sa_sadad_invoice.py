# -*- coding: utf-8 -*-
"""فاتورة SADAD محاكاة.

تنسيق رقم الفاتورة: 4 خانات biller_code + 11 خانة customer reference = 15 خانة
الـ customer ref يُولَّد من ID الدفعة + Luhn check digit (محاكاة).
"""
import base64
import io
from datetime import date, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError

try:
    import qrcode
except ImportError:
    qrcode = None


class SaSadadInvoice(models.Model):
    _name = 'sa.sadad.invoice'
    _description = 'فاتورة SADAD'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'issue_date desc, id desc'

    # ─── Identity ─────────────────────────────────────────────
    name = fields.Char(
        string='المرجع', required=True, copy=False,
        readonly=True, default=lambda s: _('جديد'), tracking=True,
    )
    bill_number = fields.Char(
        string='رقم الفاتورة SADAD', readonly=True, copy=False,
        tracking=True,
        help='15 رقم بصيغة SADAD: 4 رمز المُصدِر + 11 مرجع العميل',
    )

    # ─── Linkage ──────────────────────────────────────────────
    rent_payment_id = fields.Many2one(
        'sa.rent.payment', string='دفعة الإيجار',
        required=True, ondelete='cascade', tracking=True,
    )
    tenancy_id = fields.Many2one(
        'property.tenancy', string='عقد الإيجار',
        related='rent_payment_id.tenancy_id', store=True, readonly=True,
    )
    partner_id = fields.Many2one(
        'res.partner', string='المستأجر',
        related='rent_payment_id.tenant_id', store=True, readonly=True,
    )
    property_id = fields.Many2one(
        'property.property', string='العقار',
        related='rent_payment_id.property_id', store=True, readonly=True,
    )

    # ─── Money & dates ────────────────────────────────────────
    amount = fields.Float(
        string='المبلغ (ريال)', required=True,
        related='rent_payment_id.amount', store=True, readonly=True,
    )
    issue_date = fields.Date(
        string='تاريخ الإصدار', required=True,
        default=fields.Date.context_today, tracking=True,
    )
    expiry_date = fields.Date(
        string='تاريخ انتهاء الصلاحية', tracking=True,
    )
    biller_code = fields.Char(
        string='رمز المُصدِر', required=True, default='9999',
    )

    # ─── State ────────────────────────────────────────────────
    state = fields.Selection([
        ('pending',   'قيد الانتظار'),
        ('paid',      'مدفوعة'),
        ('cancelled', 'ملغاة'),
        ('expired',   'منتهية الصلاحية'),
    ], string='الحالة', default='pending', required=True, tracking=True)

    # ─── Payment data (filled when webhook fires) ─────────────
    paid_date = fields.Datetime(string='تاريخ السداد', readonly=True, copy=False)
    payment_ref = fields.Char(
        string='مرجع السداد البنكي', readonly=True, copy=False,
        help='يُملأ من webhook عند السداد',
    )
    payment_channel = fields.Char(
        string='قناة الدفع', readonly=True, copy=False,
        help='ATM / Online / App / Branch',
    )

    # ─── QR code (generated automatically) ────────────────────
    qr_code = fields.Binary(string='QR Code', readonly=True, attachment=True)
    qr_payload = fields.Char(
        string='محتوى QR', readonly=True, copy=False,
        help='النص المُشفَّر داخل الـ QR',
    )

    # ─── Sequencing ───────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('جديد')) == _('جديد'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'sa.sadad.invoice'
                ) or _('جديد')
        records = super().create(vals_list)
        # Generate bill_number, expiry_date, QR
        for rec in records:
            if not rec.bill_number:
                rec._generate_bill_number()
            if not rec.expiry_date:
                expiry_days = int(self.env['ir.config_parameter'].sudo().get_param(
                    'sa_sadad.expiry_days', '30'
                ))
                rec.expiry_date = rec.issue_date + timedelta(days=expiry_days)
            rec._generate_qr()
        return records

    # ─── Bill number generation ──────────────────────────────
    @staticmethod
    def _luhn_check_digit(payload):
        """Standard Luhn check digit (single digit 0-9)."""
        s = 0
        n = len(payload)
        for i, ch in enumerate(payload):
            d = int(ch)
            if (n - i) % 2 == 0:  # double odd-positioned digits from right
                d *= 2
                if d > 9:
                    d -= 9
            s += d
        return (10 - s % 10) % 10

    def _generate_bill_number(self):
        """يُولّد رقم فاتورة SADAD 15 خانة:
            * 4 خانات biller_code
            * 10 خانات: ID الدفعة محشو بأصفار + ID المستأجر
            * خانة Luhn check digit
        """
        for rec in self:
            biller = (rec.biller_code or '9999').zfill(4)[:4]
            base = '%05d%05d' % (rec.rent_payment_id.id or 0, rec.partner_id.id or 0)
            base = base[:10]  # 10 digits
            check = rec._luhn_check_digit(biller + base)
            rec.bill_number = '%s%s%d' % (biller, base, check)

    # ─── QR generation ────────────────────────────────────────
    def _generate_qr(self):
        """يُولّد QR code يحوي رابط الدفع المحاكي."""
        for rec in self:
            base_url = rec.env['ir.config_parameter'].sudo().get_param(
                'web.base.url', 'http://localhost:8069'
            )
            payload = '%s/sadad/pay/%s' % (base_url, rec.bill_number or '')
            rec.qr_payload = payload

            if qrcode is None:
                # qrcode library not installed — store URL only
                rec.qr_code = False
                continue
            try:
                img = qrcode.make(payload, box_size=8, border=2)
                buf = io.BytesIO()
                img.save(buf, format='PNG')
                rec.qr_code = base64.b64encode(buf.getvalue())
            except Exception:
                rec.qr_code = False

    def action_regenerate_qr(self):
        """زر يدوي لإعادة توليد الـ QR (إذا تغير base URL مثلاً)."""
        for rec in self:
            rec._generate_qr()
        return True

    # ─── State actions ────────────────────────────────────────
    def action_cancel(self):
        for rec in self:
            if rec.state == 'paid':
                raise UserError(_('لا يمكن إلغاء فاتورة مدفوعة'))
            rec.state = 'cancelled'
        return True

    def action_simulate_payment(self):
        """محاكاة سداد الفاتورة من زرّ في الواجهة (للاختبار)."""
        for rec in self:
            if rec.state != 'pending':
                raise UserError(_('الفاتورة ليست في حالة انتظار السداد'))
            rec._mark_paid(payment_ref='SIM-%s' % rec.id, channel='Simulation')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('تمت المحاكاة'),
                'message': _('تم تسجيل الدفع وتحديث دفعة الإيجار'),
                'type': 'success',
                'sticky': False,
            }
        }

    def _mark_paid(self, payment_ref=None, channel=None, paid_at=None):
        """يُستدعى من webhook أو من زرّ المحاكاة."""
        for rec in self:
            if rec.state == 'paid':
                continue
            rec.write({
                'state': 'paid',
                'paid_date': paid_at or fields.Datetime.now(),
                'payment_ref': payment_ref or '',
                'payment_channel': channel or '',
            })
            # Update the rent payment
            rp = rec.rent_payment_id
            if rp and rp.state in ('pending', 'overdue', 'partial'):
                rp.write({
                    'state': 'paid',
                    'amount_paid': rp.amount,
                    'payment_date': fields.Date.context_today(rec),
                    'payment_method': 'sadad',
                    'sadad_number': rec.bill_number,
                    'bank_ref': payment_ref or '',
                })
                # Trigger invoice + reconciliation if available
                try:
                    rp.action_create_invoice_and_reconcile()
                except Exception:
                    pass
            # Log to chatter
            rec.message_post(
                body=_(
                    '<b>تم سداد فاتورة SADAD</b><br/>'
                    'المبلغ: %s ريال<br/>'
                    'القناة: %s<br/>'
                    'المرجع: %s<br/>'
                    'الوقت: %s'
                ) % (rec.amount, channel or '/', payment_ref or '/', rec.paid_date),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )
        return True

    @api.model
    def cron_expire_old_invoices(self):
        """يُحدّث حالة الفواتير المنتهية الصلاحية يومياً."""
        today = fields.Date.context_today(self)
        expired = self.search([
            ('state', '=', 'pending'),
            ('expiry_date', '<', today),
        ])
        expired.write({'state': 'expired'})
        return len(expired)
