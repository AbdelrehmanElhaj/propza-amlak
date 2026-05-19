# -*- coding: utf-8 -*-
"""تصدير تقارير Excel — يستخدم xlsxwriter المُضمَّن في Odoo.

كل دالة تبني ملف xlsx، تحفظه كـ ir.attachment، وترجع act_url لتنزيله.
"""
import base64
import io
from datetime import date

from odoo import models, fields, _
from odoo.exceptions import UserError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


# ════════════════════════════════════════════════════════════════
#  Helper
# ════════════════════════════════════════════════════════════════
def _ensure_xlsxwriter():
    if xlsxwriter is None:
        raise UserError(_(
            'مكتبة xlsxwriter غير متوفرة. شغّل: pip install xlsxwriter'
        ))


def _build_attachment(env, filename, data, res_model=False, res_id=False):
    """يبني ir.attachment ويُرجع act_url للتنزيل."""
    att = env['ir.attachment'].create({
        'name':      filename,
        'type':      'binary',
        'datas':     base64.b64encode(data),
        'res_model': res_model or False,
        'res_id':    res_id or False,
        'mimetype':  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    return {
        'type':   'ir.actions.act_url',
        'url':    '/web/content/%s?download=true' % att.id,
        'target': 'self',
    }


# ════════════════════════════════════════════════════════════════
#  1. Tenant statement — Excel
# ════════════════════════════════════════════════════════════════
class PropertyTenancyXlsx(models.Model):
    _inherit = 'property.tenancy'

    def action_export_statement_xlsx(self):
        self.ensure_one()
        _ensure_xlsxwriter()
        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = wb.add_worksheet('كشف حساب')
        ws.right_to_left()  # RTL for Arabic

        # Formats
        title_fmt = wb.add_format({'bold': True, 'font_size': 16, 'align': 'center'})
        h_fmt = wb.add_format({'bold': True, 'bg_color': '#dddddd', 'border': 1})
        hdr_fmt = wb.add_format({'bold': True, 'bg_color': '#f5f5f5', 'border': 1, 'align': 'center'})
        cell_fmt = wb.add_format({'border': 1})
        money_fmt = wb.add_format({'border': 1, 'num_format': '#,##0.00'})
        total_fmt = wb.add_format({'border': 1, 'bold': True, 'bg_color': '#fff8dc',
                                    'num_format': '#,##0.00'})

        # Title
        ws.merge_range(0, 0, 0, 8, _('كشف حساب المستأجر'), title_fmt)
        ws.set_row(0, 28)

        # Tenancy info
        row = 2
        info = [
            (_('رقم العقد'), self.name),
            (_('المستأجر'),   self.partner_id.name or ''),
            (_('المالك'),     self.owner_partner_id.name or ''),
            (_('العقار'),     self.property_id.display_name or ''),
            (_('تاريخ البداية'), str(self.start_date or '')),
            (_('تاريخ النهاية'), str(self.end_date or '')),
            (_('قيمة الإيجار'),  self.rent_amount or 0.0),
            (_('الضمان'),       self.deposit_amount or 0.0),
        ]
        for label, value in info:
            ws.write(row, 0, label, h_fmt)
            ws.write(row, 1, value, cell_fmt)
            row += 1

        # Summary
        row += 1
        ws.write(row, 0, _('إجمالي المستحق'), h_fmt)
        ws.write(row, 1, self.sa_total_due or 0.0, money_fmt)
        ws.write(row, 2, _('إجمالي المدفوع'), h_fmt)
        ws.write(row, 3, self.sa_total_paid or 0.0, money_fmt)
        ws.write(row, 4, _('الرصيد المتبقي'), h_fmt)
        ws.write(row, 5, self.sa_total_balance or 0.0, money_fmt)

        # Payment schedule
        row += 2
        ws.merge_range(row, 0, row, 8, _('جدول الدفعات'), title_fmt)
        ws.set_row(row, 22)
        row += 1
        headers = ['#', _('الفترة'), _('تاريخ الاستحقاق'), _('النوع'),
                   _('المستحق'), _('المدفوع'), _('الرصيد'), _('تاريخ الدفع'), _('الحالة')]
        for col, h in enumerate(headers):
            ws.write(row, col, h, hdr_fmt)
        row += 1

        type_labels = dict(self._fields['payment_method'].selection or [])
        # Payment fields: payment_type, state
        for i, p in enumerate(self.sa_payment_ids.sorted(key=lambda x: x.due_date or date.min), 1):
            ws.write(row, 0, i, cell_fmt)
            ws.write(row, 1, p.period_label or '', cell_fmt)
            ws.write(row, 2, str(p.due_date or ''), cell_fmt)
            ws.write(row, 3, dict(p._fields['payment_type'].selection).get(p.payment_type, ''), cell_fmt)
            ws.write(row, 4, p.amount or 0.0, money_fmt)
            ws.write(row, 5, p.amount_paid or 0.0, money_fmt)
            ws.write(row, 6, p.balance or 0.0, money_fmt)
            ws.write(row, 7, str(p.payment_date or ''), cell_fmt)
            ws.write(row, 8, dict(p._fields['state'].selection).get(p.state, ''), cell_fmt)
            row += 1

        # Totals row
        ws.write(row, 0, '', total_fmt)
        ws.write(row, 1, '', total_fmt)
        ws.write(row, 2, '', total_fmt)
        ws.write(row, 3, _('الإجمالي'), total_fmt)
        ws.write(row, 4, self.sa_total_due or 0.0, total_fmt)
        ws.write(row, 5, self.sa_total_paid or 0.0, total_fmt)
        ws.write(row, 6, self.sa_total_balance or 0.0, total_fmt)
        ws.write(row, 7, '', total_fmt)
        ws.write(row, 8, '', total_fmt)

        # Column widths
        widths = [4, 12, 14, 10, 12, 12, 12, 14, 12]
        for col, w in enumerate(widths):
            ws.set_column(col, col, w)

        wb.close()
        filename = 'كشف حساب %s.xlsx' % (self.name or 'tenancy')
        return _build_attachment(
            self.env, filename, output.getvalue(),
            res_model='property.tenancy', res_id=self.id,
        )


# ════════════════════════════════════════════════════════════════
#  2. Owner P&L — Excel
# ════════════════════════════════════════════════════════════════
class ResPartnerXlsxExports(models.Model):
    _inherit = 'res.partner'

    def action_export_owner_pnl_xlsx(self):
        """تقرير ربح/خسارة المالك: إيرادات الإيجار - تكاليف الصيانة."""
        self.ensure_one()
        if not self.is_property_owner:
            raise UserError(_('هذا الجهة ليست مالكاً'))
        _ensure_xlsxwriter()

        Property = self.env['property.property']
        Tenancy = self.env['property.tenancy']
        Payment = self.env['sa.rent.payment']
        Maint = self.env['sa.maintenance.request']

        properties = Property.search([('owner_partner_id', '=', self.id)])
        if not properties:
            raise UserError(_('لا توجد عقارات لهذا المالك'))

        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = wb.add_worksheet('P&L')
        ws.right_to_left()

        title = wb.add_format({'bold': True, 'font_size': 16, 'align': 'center'})
        hdr = wb.add_format({'bold': True, 'bg_color': '#f5f5f5', 'border': 1, 'align': 'center'})
        cell = wb.add_format({'border': 1})
        money = wb.add_format({'border': 1, 'num_format': '#,##0.00'})
        total = wb.add_format({'border': 1, 'bold': True, 'bg_color': '#fff8dc',
                                'num_format': '#,##0.00'})
        green = wb.add_format({'border': 1, 'bold': True, 'bg_color': '#e8f5e9',
                                'num_format': '#,##0.00'})
        red = wb.add_format({'border': 1, 'bold': True, 'bg_color': '#ffebee',
                              'num_format': '#,##0.00'})

        ws.merge_range(0, 0, 0, 5, _('تقرير الربح والخسارة — %s') % self.name, title)
        ws.set_row(0, 28)

        row = 2
        for col, h in enumerate([_('العقار'), _('عقود سارية'),
                                 _('إيراد محصَّل'), _('إيراد مستحق'),
                                 _('تكاليف الصيانة'), _('الصافي')]):
            ws.write(row, col, h, hdr)
        row += 1

        total_collected = total_pending = total_maint = 0.0
        for prop in properties:
            tenancy_ids = Tenancy.search([
                ('property_id', '=', prop.id),
            ]).ids
            active_count = Tenancy.search_count([
                ('property_id', '=', prop.id),
                ('state', '=', 'running'),
            ])
            paid = sum(Payment.search([
                ('tenancy_id', 'in', tenancy_ids),
                ('state', 'in', ('paid', 'partial')),
            ]).mapped('amount_paid'))
            pending = sum(Payment.search([
                ('tenancy_id', 'in', tenancy_ids),
                ('state', 'in', ('pending', 'overdue', 'partial')),
            ]).mapped('balance'))
            maint = sum(Maint.search([
                ('property_id', '=', prop.id),
                ('state', '=', 'done'),
                ('cost_bearer', '=', 'owner'),
            ]).mapped('cost'))

            net = paid - maint
            ws.write(row, 0, prop.display_name or '', cell)
            ws.write(row, 1, active_count, cell)
            ws.write(row, 2, paid, money)
            ws.write(row, 3, pending, money)
            ws.write(row, 4, maint, money)
            ws.write(row, 5, net, green if net >= 0 else red)

            total_collected += paid
            total_pending += pending
            total_maint += maint
            row += 1

        # Grand total
        net_total = total_collected - total_maint
        ws.write(row, 0, _('الإجمالي'), total)
        ws.write(row, 1, '', total)
        ws.write(row, 2, total_collected, total)
        ws.write(row, 3, total_pending, total)
        ws.write(row, 4, total_maint, total)
        ws.write(row, 5, net_total, green if net_total >= 0 else red)

        for col, w in enumerate([28, 12, 14, 14, 14, 14]):
            ws.set_column(col, col, w)

        wb.close()
        filename = 'تقرير ربح %s.xlsx' % self.name
        return _build_attachment(
            self.env, filename, output.getvalue(),
            res_model='res.partner', res_id=self.id,
        )


# ════════════════════════════════════════════════════════════════
#  3. Payments report — Excel (system-wide)
# ════════════════════════════════════════════════════════════════
class SaRentPaymentXlsx(models.Model):
    _inherit = 'sa.rent.payment'

    def action_export_payments_xlsx(self):
        """يصدّر السجلات المُحدَّدة (أو كلها) إلى xlsx."""
        _ensure_xlsxwriter()
        records = self or self.search([])
        if not records:
            raise UserError(_('لا توجد دفعات للتصدير'))

        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = wb.add_worksheet('Payments')
        ws.right_to_left()

        title = wb.add_format({'bold': True, 'font_size': 14, 'align': 'center'})
        hdr = wb.add_format({'bold': True, 'bg_color': '#f5f5f5', 'border': 1, 'align': 'center'})
        cell = wb.add_format({'border': 1})
        money = wb.add_format({'border': 1, 'num_format': '#,##0.00'})

        ws.merge_range(0, 0, 0, 9, _('تقرير الدفعات'), title)
        ws.set_row(0, 24)

        row = 2
        headers = ['#', _('رقم الدفعة'), _('العقار'), _('المستأجر'),
                   _('الفترة'), _('تاريخ الاستحقاق'),
                   _('المستحق'), _('المدفوع'), _('الرصيد'), _('الحالة')]
        for col, h in enumerate(headers):
            ws.write(row, col, h, hdr)
        row += 1

        state_label = dict(self._fields['state'].selection)
        for i, p in enumerate(records.sorted(key=lambda x: x.due_date or date.min), 1):
            ws.write(row, 0, i, cell)
            ws.write(row, 1, p.name or '', cell)
            ws.write(row, 2, (p.property_id.display_name or ''), cell)
            ws.write(row, 3, (p.tenant_id.name or ''), cell)
            ws.write(row, 4, p.period_label or '', cell)
            ws.write(row, 5, str(p.due_date or ''), cell)
            ws.write(row, 6, p.amount or 0.0, money)
            ws.write(row, 7, p.amount_paid or 0.0, money)
            ws.write(row, 8, p.balance or 0.0, money)
            ws.write(row, 9, state_label.get(p.state, ''), cell)
            row += 1

        for col, w in enumerate([4, 14, 24, 22, 12, 14, 12, 12, 12, 12]):
            ws.set_column(col, col, w)

        wb.close()
        filename = 'تقرير الدفعات %s.xlsx' % fields.Date.context_today(self).isoformat()
        return _build_attachment(
            self.env, filename, output.getvalue(),
            res_model='sa.rent.payment',
        )
