# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PropertyTenancyDeposit(models.Model):
    """امتداد عقد الإيجار — تتبّع تفصيلي للضمان (Deposit Tracking).

    الحقل الأساسي `deposit_amount` موجود في sa_property_base. هنا نضيف:
        - تاريخ استلام الضمان
        - حركة الدفع (account.payment) لاستلام الضمان
        - حالة الضمان (محتجز / مسترد جزئياً / مسترد / مصادر)
        - المبلغ المسترد (يُكتب بواسطة wizard إنهاء العقد لاحقاً)
        - المتبقي (محسوب)
    """
    _inherit = 'property.tenancy'

    # ─── Deposit lifecycle tracking ──────────────────────────────
    deposit_date_paid = fields.Date(
        string='تاريخ استلام الضمان', tracking=True, copy=False,
    )
    deposit_payment_id = fields.Many2one(
        'account.payment', string='سند استلام الضمان',
        copy=False, tracking=True,
        help='قيد المدفوعات الذي سُجِّل عند استلام الضمان من المستأجر',
    )
    deposit_state = fields.Selection([
        ('not_paid',           'لم يُدفع'),
        ('held',               'محتجَز'),
        ('partially_returned', 'مُسترد جزئياً'),
        ('returned',           'مُسترد'),
        ('forfeited',          'مُصادَر'),
    ], string='حالة الضمان', default='not_paid',
       tracking=True, copy=False, required=True)

    deposit_returned_amount = fields.Float(
        string='المبلغ المُسترد (ريال)', tracking=True, copy=False,
        help='يُحدَّث آلياً بواسطة معالج إنهاء العقد',
    )
    deposit_forfeited_amount = fields.Float(
        string='المبلغ المُصادَر (ريال)', tracking=True, copy=False,
        help='ما يُحتفظ به من الضمان كخصومات أو غرامات',
    )
    deposit_remaining = fields.Float(
        string='المتبقي من الضمان (ريال)',
        compute='_compute_deposit_remaining', store=True,
    )
    deposit_notes = fields.Text(string='ملاحظات الضمان')

    @api.depends('deposit_amount',
                 'deposit_returned_amount',
                 'deposit_forfeited_amount')
    def _compute_deposit_remaining(self):
        for rec in self:
            rec.deposit_remaining = (
                (rec.deposit_amount or 0.0)
                - (rec.deposit_returned_amount or 0.0)
                - (rec.deposit_forfeited_amount or 0.0)
            )

    # ─── Actions ─────────────────────────────────────────────────
    def action_register_deposit_receipt(self):
        """فتح account.payment لاستلام الضمان من المستأجر."""
        self.ensure_one()
        if not self.deposit_amount:
            raise UserError(_('يجب تحديد قيمة الضمان أولاً.'))
        if self.deposit_state != 'not_paid':
            raise UserError(_(
                'الضمان مسجَّل بالفعل (الحالة: %s).'
            ) % dict(self._fields['deposit_state'].selection).get(self.deposit_state))
        return {
            'name': _('تسجيل استلام الضمان'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_payment_type':  'inbound',
                'default_partner_type':  'customer',
                'default_partner_id':    self.partner_id.id,
                'default_amount':        self.deposit_amount,
                'default_ref':           _('وديعة ضمان — %s') % (self.name or ''),
                'default_sa_tenancy_deposit_id': self.id,
            },
        }

    def action_mark_deposit_held(self):
        """يُستدعى يدوياً (أو من زرّ بعد account.payment) لتأكيد استلام الضمان."""
        for rec in self:
            if not rec.deposit_amount:
                raise UserError(_('لا يمكن احتجاز ضمان بقيمة صفر'))
            rec.write({
                'deposit_state':     'held',
                'deposit_date_paid': rec.deposit_date_paid or fields.Date.context_today(rec),
            })
        return True

    def action_view_deposit_payment(self):
        self.ensure_one()
        if not self.deposit_payment_id:
            raise UserError(_('لا يوجد سند دفع للضمان'))
        return {
            'name':      _('سند الضمان'),
            'type':      'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'form',
            'res_id':    self.deposit_payment_id.id,
        }


class AccountPaymentDeposit(models.Model):
    """ربط account.payment بعقد الإيجار عند تسجيل سند الضمان.

    عند ترحيل (post) سند الدفع، نُحدِّث الـ tenancy تلقائياً إلى حالة 'held'.
    """
    _inherit = 'account.payment'

    sa_tenancy_deposit_id = fields.Many2one(
        'property.tenancy', string='عقد إيجار (ضمان)',
        help='إذا كان هذا السند يمثّل استلام/إرجاع ضمان لعقد إيجار',
    )

    def action_post(self):
        res = super().action_post()
        for pay in self:
            tenancy = pay.sa_tenancy_deposit_id
            if not tenancy:
                continue
            # Inbound payment: receiving deposit from tenant
            if pay.payment_type == 'inbound' and tenancy.deposit_state == 'not_paid':
                tenancy.write({
                    'deposit_payment_id': pay.id,
                    'deposit_date_paid':  pay.date or fields.Date.context_today(pay),
                    'deposit_state':      'held',
                })
                tenancy.message_post(
                    body=_('تم استلام الضمان: %s ريال (سند %s)') % (
                        pay.amount, pay.name or '/',
                    ),
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )
        return res
