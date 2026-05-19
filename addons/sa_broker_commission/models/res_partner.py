# -*- coding: utf-8 -*-
"""إحصائيات العمولات على res.partner للوسطاء."""
from odoo import models, fields, api, _
from datetime import date


class ResPartnerBrokerStats(models.Model):
    _inherit = 'res.partner'

    broker_commission_ids = fields.One2many(
        'sa.broker.commission', 'broker_partner_id',
        string='عمولات الوسيط',
    )
    broker_active_commissions = fields.Integer(
        string='عمولات نشطة',
        compute='_compute_broker_stats',
    )
    broker_total_earned = fields.Float(
        string='إجمالي العمولات المُسدَّدة (ريال)',
        compute='_compute_broker_stats',
    )
    broker_total_pending = fields.Float(
        string='عمولات مستحقة (ريال)',
        compute='_compute_broker_stats',
    )
    broker_ytd_earned = fields.Float(
        string='عمولات السنة الحالية (ريال)',
        compute='_compute_broker_stats',
    )

    @api.depends('broker_commission_ids',
                 'broker_commission_ids.state',
                 'broker_commission_ids.paid_amount',
                 'broker_commission_ids.remaining_amount')
    def _compute_broker_stats(self):
        today = date.today()
        ytd_start = date(today.year, 1, 1)
        for rec in self:
            if not rec.is_broker:
                rec.broker_active_commissions = 0
                rec.broker_total_earned = 0.0
                rec.broker_total_pending = 0.0
                rec.broker_ytd_earned = 0.0
                continue
            commissions = rec.broker_commission_ids
            rec.broker_active_commissions = len(
                commissions.filtered(lambda c: c.state in ('confirmed', 'partial'))
            )
            rec.broker_total_earned = sum(commissions.mapped('paid_amount'))
            rec.broker_total_pending = sum(commissions.mapped('remaining_amount'))

            # YTD: lines paid this year
            ytd_paid = 0.0
            for c in commissions:
                paid_lines_ytd = c.line_ids.filtered(
                    lambda l: l.state == 'paid' and l.due_date and l.due_date >= ytd_start
                )
                ytd_paid += sum(paid_lines_ytd.mapped('amount'))
            rec.broker_ytd_earned = ytd_paid

    def action_view_broker_commissions(self):
        self.ensure_one()
        return {
            'name': _('عمولات %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'sa.broker.commission',
            'view_mode': 'tree,form',
            'domain': [('broker_partner_id', '=', self.id)],
            'context': {'default_broker_partner_id': self.id},
        }
