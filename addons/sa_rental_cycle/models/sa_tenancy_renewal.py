# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta
from datetime import date, timedelta


class PropertyTenancyRenewal(models.Model):
    """امتداد عقد الإيجار — تجديد تلقائي/يدوي للعقد.

    يدعم:
        * `auto_renew`: علامة التجديد التلقائي
        * `renewal_period_months`: مدة التجديد القادم
        * `renewal_rent_increase_pct`: نسبة الزيادة (تتحقق من تجميد الرياض)
        * Cron يومي يُنشئ tenancy جديد قبل end_date بـ renewal_notice_days
        * زر يدوي لفتح wizard التجديد
    """
    _inherit = 'property.tenancy'

    # ─── Auto-renewal config ──────────────────────────────────────
    auto_renew = fields.Boolean(
        string='تجديد تلقائي', tracking=True,
        help='عند تفعيله، سيُنشئ النظام عقد إيجار جديد تلقائياً قبل انتهاء العقد',
    )
    renewal_period_months = fields.Integer(
        string='مدة التجديد (أشهر)', default=12, tracking=True,
    )
    renewal_rent_increase_pct = fields.Float(
        string='نسبة زيادة الإيجار (٪)', default=0.0, tracking=True,
        help='نسبة الزيادة المطبَّقة عند التجديد. الرياض: ممنوع تجاوز 0%',
    )
    renewal_notice_days = fields.Integer(
        string='التنبيه قبل (أيام)', default=30, tracking=True,
        help='قبل كم يوم من end_date يبدأ توليد العقد الجديد',
    )

    # ─── Renewal links ────────────────────────────────────────────
    renewed_to_id = fields.Many2one(
        'property.tenancy', string='جُدِّد لـ',
        copy=False, readonly=True, ondelete='set null',
    )
    renewed_from_id = fields.Many2one(
        'property.tenancy', string='مُجدَّد من',
        copy=False, readonly=True, ondelete='set null',
    )
    is_renewed = fields.Boolean(
        string='مُجدَّد', compute='_compute_is_renewed',
    )

    @api.depends('renewed_to_id')
    def _compute_is_renewed(self):
        for rec in self:
            rec.is_renewed = bool(rec.renewed_to_id)

    # ─── Validation ───────────────────────────────────────────────
    @api.constrains('renewal_rent_increase_pct')
    def _check_rent_freeze(self):
        for rec in self:
            if (rec.renewal_rent_increase_pct
                    and rec.property_id
                    and getattr(rec.property_id, 'rent_freeze_active', False)
                    and rec.renewal_rent_increase_pct > 0):
                raise UserError(_(
                    'لا يُسمح بزيادة الإيجار في عقارات الرياض حتى سبتمبر 2030 '
                    '(قانون تجميد الإيجار). أبقِ النسبة عند 0٪.'
                ))

    # ─── Manual renewal action ────────────────────────────────────
    def action_open_renewal_wizard(self):
        self.ensure_one()
        if self.renewed_to_id:
            raise UserError(_('هذا العقد مُجدَّد بالفعل: %s') % self.renewed_to_id.name)
        if self.state not in ('running', 'closed'):
            raise UserError(_('يمكن تجديد العقود السارية أو المنتهية فقط'))
        return {
            'name': _('تجديد عقد الإيجار'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.tenancy.renewal.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_tenancy_id': self.id},
        }

    def action_view_renewal(self):
        self.ensure_one()
        if not self.renewed_to_id:
            raise UserError(_('لا يوجد عقد مُجدَّد'))
        return {
            'name': _('العقد المُجدَّد'),
            'type': 'ir.actions.act_window',
            'res_model': 'property.tenancy',
            'view_mode': 'form',
            'res_id': self.renewed_to_id.id,
        }

    def action_view_original(self):
        self.ensure_one()
        if not self.renewed_from_id:
            raise UserError(_('لا يوجد عقد أصلي'))
        return {
            'name': _('العقد الأصلي'),
            'type': 'ir.actions.act_window',
            'res_model': 'property.tenancy',
            'view_mode': 'form',
            'res_id': self.renewed_from_id.id,
        }

    # ─── Renewal core logic ──────────────────────────────────────
    def _build_renewal_vals(self, new_rent=None, period_months=None,
                             new_start_date=None):
        """يبني قيم العقد الجديد من العقد الحالي."""
        self.ensure_one()
        period = period_months or self.renewal_period_months or 12
        start = new_start_date or (self.end_date + timedelta(days=1)) \
                if self.end_date else fields.Date.context_today(self)
        end = start + relativedelta(months=period) - timedelta(days=1)

        if new_rent is None:
            base_rent = self.rent_amount or 0.0
            increase = self.renewal_rent_increase_pct or 0.0
            # Riyadh freeze override
            if (self.property_id
                    and getattr(self.property_id, 'rent_freeze_active', False)):
                increase = 0.0
            new_rent = base_rent * (1 + increase / 100.0)

        return {
            'property_id':        self.property_id.id,
            'partner_id':         self.partner_id.id,
            'start_date':         start,
            'end_date':           end,
            'duration':           period,
            'interval_type':      'months',
            'rent_amount':        new_rent,
            'deposit_amount':     self.deposit_amount,
            'payment_method':     self.payment_method,
            'auto_renew':         self.auto_renew,
            'renewal_period_months':       self.renewal_period_months,
            'renewal_rent_increase_pct':   self.renewal_rent_increase_pct,
            'renewal_notice_days':         self.renewal_notice_days,
            'renewed_from_id':    self.id,
            'state':              'draft',
        }

    def _do_renewal(self, new_rent=None, period_months=None,
                    new_start_date=None, auto=False):
        """ينفّذ التجديد ويرجع العقد الجديد."""
        self.ensure_one()
        if self.renewed_to_id:
            raise UserError(_('العقد مُجدَّد بالفعل'))
        vals = self._build_renewal_vals(
            new_rent=new_rent,
            period_months=period_months,
            new_start_date=new_start_date,
        )
        new_tenancy = self.create(vals)
        self.write({
            'renewed_to_id': new_tenancy.id,
            'sa_cycle_state': 'renewed',
        })
        msg = _(
            '<p><b>تم إنشاء عقد التجديد</b> %s</p>'
            '<ul>'
            '<li>الفترة: %s → %s</li>'
            '<li>الإيجار الجديد: %s ريال (السابق %s)</li>'
            '<li>الطريقة: %s</li>'
            '</ul>'
        ) % (
            new_tenancy.name,
            new_tenancy.start_date, new_tenancy.end_date,
            new_tenancy.rent_amount, self.rent_amount,
            _('تلقائي (cron)') if auto else _('يدوي'),
        )
        self.message_post(body=msg, message_type='notification',
                          subtype_xmlid='mail.mt_note')
        new_tenancy.message_post(
            body=_('وُلد هذا العقد تلقائياً من تجديد %s') % self.name,
            message_type='notification', subtype_xmlid='mail.mt_note',
        )
        # Activity reminder for the manager
        try:
            new_tenancy.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('تأكيد عقد تجديد %s') % new_tenancy.name,
                note=_('عقد مُولَّد تلقائياً من نظام التجديد. الرجاء المراجعة والتأكيد.'),
                user_id=self.env.user.id,
            )
        except Exception:
            pass
        return new_tenancy

    # ─── Cron entry-point ────────────────────────────────────────
    @api.model
    def cron_auto_renew_tenancies(self):
        """يُستدعى يومياً — يُجدّد العقود التي حلّ موعد تجديدها."""
        today = date.today()
        # Find candidates: running, auto_renew, not yet renewed,
        # and within renewal_notice_days of end_date
        candidates = self.search([
            ('state', '=', 'running'),
            ('auto_renew', '=', True),
            ('renewed_to_id', '=', False),
            ('end_date', '!=', False),
        ])
        renewed = self.browse()
        for rec in candidates:
            notice = rec.renewal_notice_days or 30
            days_left = (rec.end_date - today).days
            if days_left > notice or days_left < 0:
                continue
            try:
                new_tenancy = rec._do_renewal(auto=True)
                renewed |= new_tenancy
            except Exception:
                # Don't fail the whole batch — log on the original tenancy
                rec.message_post(
                    body=_('فشل التجديد التلقائي. الرجاء المراجعة يدوياً.'),
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )
        return len(renewed)
