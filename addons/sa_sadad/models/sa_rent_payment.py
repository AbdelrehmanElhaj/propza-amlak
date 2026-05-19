# -*- coding: utf-8 -*-
"""ربط دفعة الإيجار بفاتورة SADAD + زر إصدار."""
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaRentPaymentSadad(models.Model):
    _inherit = 'sa.rent.payment'

    sadad_invoice_ids = fields.One2many(
        'sa.sadad.invoice', 'rent_payment_id',
        string='فواتير SADAD',
    )
    has_active_sadad = fields.Boolean(
        string='عنده فاتورة SADAD نشطة',
        compute='_compute_has_active_sadad',
    )

    @api.depends('sadad_invoice_ids', 'sadad_invoice_ids.state')
    def _compute_has_active_sadad(self):
        for rec in self:
            rec.has_active_sadad = bool(rec.sadad_invoice_ids.filtered(
                lambda i: i.state == 'pending'
            ))

    def action_generate_sadad(self):
        """يُنشئ فاتورة SADAD جديدة لهذه الدفعة."""
        self.ensure_one()
        if self.state in ('paid', 'cancelled'):
            raise UserError(_('لا يمكن إصدار فاتورة SADAD لدفعة مدفوعة أو ملغاة'))
        if self.has_active_sadad:
            raise UserError(_(
                'يوجد فاتورة SADAD نشطة بالفعل. ألغها أولاً قبل إصدار جديدة.'
            ))
        biller_code = self.env['ir.config_parameter'].sudo().get_param(
            'sa_sadad.biller_code', '9999'
        )
        invoice = self.env['sa.sadad.invoice'].create({
            'rent_payment_id': self.id,
            'biller_code': biller_code,
        })
        return {
            'name': _('فاتورة SADAD'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.sadad.invoice',
            'view_mode': 'form',
            'res_id': invoice.id,
            'target': 'current',
        }

    def action_view_sadad_invoices(self):
        self.ensure_one()
        return {
            'name': _('فواتير SADAD لهذه الدفعة'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.sadad.invoice',
            'view_mode': 'tree,form',
            'domain': [('rent_payment_id', '=', self.id)],
        }
