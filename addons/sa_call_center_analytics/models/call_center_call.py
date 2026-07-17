# -*- coding: utf-8 -*-
from odoo import models, api
from odoo.osv import expression


class SaCallCenterCall(models.Model):
    _inherit = 'sa.call.center.call'

    @api.model
    def get_communication_stats(self, domain):
        """إحصاءات تواصل مجمّعة (عملاء فريدون / مكالمات مكررة / إجمالي وقت التحدث).

        يستخدم استعلام read_group واحد فقط (lazy=False) — لا حلقات بايثون
        على تسجيلات المكالمات.
        """
        contact_domain = expression.AND([
            domain,
            [('state', 'in', ('answered', 'ended')), ('partner_id', '!=', False)],
        ])
        # ملاحظة: lazy=False يضمن أن مفتاح العدّ في كل مجموعة هو '__count'
        # (وإلا فإن read_group الافتراضي (lazy=True) مع مجموعة تجميع واحدة
        # فقط يعيد المفتاح 'partner_id_count' بدلاً من '__count').
        groups = self.read_group(
            contact_domain, ['talk_duration:sum'], ['partner_id'], lazy=False,
        )
        unique_customers = len(groups)
        total_contact_calls = sum(g['__count'] for g in groups)
        total_talk_duration = sum(g['talk_duration'] for g in groups)
        return {
            'unique_customers': unique_customers,
            'total_contact_calls': total_contact_calls,
            'repeated_calls': total_contact_calls - unique_customers,
            'total_talk_duration': total_talk_duration,
        }
