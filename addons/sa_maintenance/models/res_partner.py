# -*- coding: utf-8 -*-
from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ─── حقول المقاول/الفني ─────────────────────────────────────
    is_technician = fields.Boolean(string='فني/مقاول صيانة')
    sa_skill_ids = fields.Many2many(
        'sa.maintenance.skill',
        'partner_skill_rel', 'partner_id', 'skill_id',
        string='التخصصات'
    )
    sa_hourly_rate = fields.Float(
        string='السعر بالساعة (ريال)',
        help='التعرفة الافتراضية للساعة لهذا المقاول'
    )
    sa_call_out_fee = fields.Float(
        string='رسوم الزيارة (ريال)',
        help='رسوم ثابتة للزيارة بغض النظر عن المدة'
    )
    sa_response_hours = fields.Integer(
        string='زمن الاستجابة المتوقع (ساعات)',
        help='كم يستغرق المقاول للوصول بعد الطلب (تقديري)'
    )
    sa_active_request_count = fields.Integer(
        string='طلبات صيانة جارية',
        compute='_compute_maintenance_stats'
    )
    sa_total_request_count = fields.Integer(
        string='إجمالي الطلبات',
        compute='_compute_maintenance_stats'
    )

    def _compute_maintenance_stats(self):
        Request = self.env['sa.maintenance.request']
        for p in self:
            if p.is_technician:
                p.sa_active_request_count = Request.search_count([
                    ('supplier_partner_id', '=', p.id),
                    ('state', 'in', ('new', 'scheduled', 'in_progress')),
                ])
                p.sa_total_request_count = Request.search_count([
                    ('supplier_partner_id', '=', p.id),
                ])
            else:
                p.sa_active_request_count = 0
                p.sa_total_request_count = 0
