# -*- coding: utf-8 -*-
"""قيود عدم الحذف لامتثال ZATCA Phase 2.

الفواتير المُرحَّلة وسندات الدفع المُرحَّلة لا يجب حذفها بل إلغاؤها فقط.
هذا متوافق مع متطلبات الفاتورة الإلكترونية لـ ZATCA.
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountMoveZatca(models.Model):
    _inherit = 'account.move'

    def unlink(self):
        for move in self:
            # Block deletion of posted invoices (already enforced by Odoo,
            # but we add a friendly Saudi-specific message).
            if move.state == 'posted':
                raise UserError(_(
                    'لا يمكن حذف فاتورة مُرحَّلة (%s).\n'
                    'وفقاً لمتطلبات الفاتورة الإلكترونية ZATCA Phase 2، '
                    'يجب إلغاء الفاتورة وعكسها بدل حذفها.\n'
                    'استخدم "Reset to Draft" ثم "Cancel" أو "Reverse".'
                ) % move.name)
        return super().unlink()


class AccountPaymentZatca(models.Model):
    _inherit = 'account.payment'

    def unlink(self):
        for pay in self:
            if pay.state == 'posted':
                raise UserError(_(
                    'لا يمكن حذف سند دفع مُرحَّل (%s).\n'
                    'يجب إلغاؤه أولاً، ثم حذفه إذا لم يكن مرتبطاً بقيد محاسبي مُرحَّل.'
                ) % (pay.name or pay.id))
        return super().unlink()


class SaRentPaymentZatca(models.Model):
    """منع حذف دفعة إيجار لها فاتورة مُرحَّلة."""
    _inherit = 'sa.rent.payment'

    def unlink(self):
        for rec in self:
            if rec.move_id and rec.move_id.state == 'posted':
                raise UserError(_(
                    'لا يمكن حذف دفعة إيجار (%s) لها فاتورة مُرحَّلة (%s).\n'
                    'يجب إلغاء الفاتورة أولاً.'
                ) % (rec.name or '/', rec.move_id.name))
        return super().unlink()
