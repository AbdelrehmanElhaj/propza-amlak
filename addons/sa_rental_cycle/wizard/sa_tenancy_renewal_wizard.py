# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta
from datetime import timedelta


class SaTenancyRenewalWizard(models.TransientModel):
    """معالج تجديد عقد الإيجار يدوياً.

    يسمح للمستخدم بمراجعة:
        * تواريخ بداية ونهاية العقد الجديد
        * قيمة الإيجار الجديد (مع التحقق من قانون تجميد الرياض)
        * نسخ خصائص الإيجار من العقد الأصلي (الضمان، طريقة الدفع، إلخ)

    قبل تأكيد التجديد.
    """
    _name = 'sa.tenancy.renewal.wizard'
    _description = 'تجديد عقد الإيجار'

    tenancy_id = fields.Many2one(
        'property.tenancy', string='العقد الأصلي',
        required=True, readonly=True,
    )
    property_id = fields.Many2one(
        'property.property', string='العقار',
        related='tenancy_id.property_id', readonly=True,
    )
    partner_id = fields.Many2one(
        'res.partner', string='المستأجر',
        related='tenancy_id.partner_id', readonly=True,
    )

    # ─── Dates ────────────────────────────────────────────────────
    new_start_date = fields.Date(
        string='تاريخ بداية العقد الجديد', required=True,
        compute='_compute_default_dates', store=True, readonly=False,
    )
    period_months = fields.Integer(
        string='مدة العقد الجديد (أشهر)', required=True,
        compute='_compute_default_period', store=True, readonly=False,
    )
    new_end_date = fields.Date(
        string='تاريخ نهاية العقد الجديد',
        compute='_compute_new_end_date', store=False,
    )

    # ─── Rent ─────────────────────────────────────────────────────
    current_rent = fields.Float(
        string='الإيجار الحالي (ريال)',
        related='tenancy_id.rent_amount', readonly=True,
    )
    rent_increase_pct = fields.Float(
        string='نسبة الزيادة (٪)', default=0.0,
        compute='_compute_default_increase', store=True, readonly=False,
    )
    new_rent = fields.Float(
        string='الإيجار الجديد (ريال)', required=True,
        compute='_compute_new_rent', store=True, readonly=False,
    )

    # ─── Riyadh freeze warning ────────────────────────────────────
    rent_freeze_active = fields.Boolean(
        string='تجميد الإيجار مُفعَّل',
        related='property_id.rent_freeze_active', readonly=True,
    )
    rent_freeze_warning = fields.Boolean(
        string='تحذير تجميد', compute='_compute_freeze_warning',
    )

    notes = fields.Text(string='ملاحظات على التجديد')

    # ─── Computed ─────────────────────────────────────────────────
    @api.depends('tenancy_id')
    def _compute_default_dates(self):
        for rec in self:
            if rec.tenancy_id and rec.tenancy_id.end_date:
                rec.new_start_date = rec.tenancy_id.end_date + timedelta(days=1)
            else:
                rec.new_start_date = fields.Date.context_today(rec)

    @api.depends('tenancy_id')
    def _compute_default_period(self):
        for rec in self:
            rec.period_months = rec.tenancy_id.renewal_period_months or 12

    @api.depends('tenancy_id', 'rent_freeze_active')
    def _compute_default_increase(self):
        for rec in self:
            if rec.rent_freeze_active:
                rec.rent_increase_pct = 0.0
            else:
                rec.rent_increase_pct = rec.tenancy_id.renewal_rent_increase_pct or 0.0

    @api.depends('current_rent', 'rent_increase_pct')
    def _compute_new_rent(self):
        for rec in self:
            rec.new_rent = (rec.current_rent or 0.0) * (
                1 + (rec.rent_increase_pct or 0.0) / 100.0
            )

    @api.depends('new_start_date', 'period_months')
    def _compute_new_end_date(self):
        for rec in self:
            if rec.new_start_date and rec.period_months:
                rec.new_end_date = (
                    rec.new_start_date
                    + relativedelta(months=rec.period_months)
                    - timedelta(days=1)
                )
            else:
                rec.new_end_date = False

    @api.depends('rent_freeze_active', 'rent_increase_pct')
    def _compute_freeze_warning(self):
        for rec in self:
            rec.rent_freeze_warning = bool(
                rec.rent_freeze_active and (rec.rent_increase_pct or 0) > 0
            )

    # ─── Action ───────────────────────────────────────────────────
    def action_renew(self):
        self.ensure_one()
        if self.rent_freeze_warning:
            raise UserError(_(
                'لا يُسمح بزيادة الإيجار في عقارات الرياض حتى سبتمبر 2030 '
                '(قانون تجميد الإيجار). أبقِ النسبة عند 0٪ أو ألغِ التجديد.'
            ))
        if self.new_rent <= 0:
            raise UserError(_('قيمة الإيجار الجديد غير صحيحة'))
        if not self.new_start_date or not self.period_months:
            raise UserError(_('يجب تحديد تاريخ البداية والمدة'))

        new_tenancy = self.tenancy_id._do_renewal(
            new_rent=self.new_rent,
            period_months=self.period_months,
            new_start_date=self.new_start_date,
            auto=False,
        )
        if self.notes:
            new_tenancy.message_post(
                body=_('ملاحظات التجديد: %s') % self.notes,
                message_type='notification', subtype_xmlid='mail.mt_note',
            )
        # Open the new tenancy
        return {
            'name': _('عقد التجديد'),
            'type': 'ir.actions.act_window',
            'res_model': 'property.tenancy',
            'view_mode': 'form',
            'res_id': new_tenancy.id,
            'target': 'current',
        }
