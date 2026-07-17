# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    sa_call_talk_duration_total = fields.Integer(
        string='إجمالي وقت التحدث (ثانية)',
        compute='_compute_sa_call_stats',
    )
    sa_call_repeat_count = fields.Integer(
        string='مكالمات مكررة',
        compute='_compute_sa_call_stats',
    )
    sa_call_first_contact_date = fields.Datetime(
        string='أول تواصل',
        compute='_compute_sa_call_stats',
    )
    sa_call_last_contact_date = fields.Datetime(
        string='آخر تواصل',
        compute='_compute_sa_call_stats',
    )

    @api.depends('sa_call_ids.state', 'sa_call_ids.talk_duration', 'sa_call_ids.start_datetime')
    def _compute_sa_call_stats(self):
        Call = self.env['sa.call.center.call']
        # استعلام read_group واحد مُجمَّع لكامل المجموعة (self.ids) — وليس
        # حلقة بايثون تستدعي read_group لكل عميل على حدة.
        # يُستخدم اسم مستعار "name:agg(field)" لكل من min/max على نفس الحقل
        # (start_datetime)، لأن read_group في أودو يُبقي على تجميع واحد فقط
        # لكل اسم حقل عند التصادم — استخدام اسم مستعار مختلف لكل تجميع
        # يتجنّب أن يُطغى أحدهما على الآخر.
        groups = Call.read_group(
            [
                ('partner_id', 'in', self.ids),
                ('state', 'in', ('answered', 'ended')),
            ],
            [
                'talk_duration:sum',
                'first_contact:min(start_datetime)',
                'last_contact:max(start_datetime)',
            ],
            ['partner_id'],
            lazy=False,
        )
        by_partner = {g['partner_id'][0]: g for g in groups if g['partner_id']}
        for partner in self:
            g = by_partner.get(partner.id)
            partner.sa_call_talk_duration_total = g['talk_duration'] if g else 0
            partner.sa_call_repeat_count = max(g['__count'] - 1, 0) if g else 0
            partner.sa_call_first_contact_date = g['first_contact'] if g else False
            partner.sa_call_last_contact_date = g['last_contact'] if g else False
