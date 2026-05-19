# -*- coding: utf-8 -*-
"""دوال مساعدة على res.users لربط الأدوار."""
from odoo import models, fields, api


class ResUsers(models.Model):
    _inherit = 'res.users'

    pms_role_label = fields.Char(
        string='دور PMS',
        compute='_compute_pms_role_label', store=False,
    )

    def _compute_pms_role_label(self):
        """يعرض دور المستخدم في النظام بطريقة مختصرة."""
        roles = [
            ('sa_security.group_pms_admin',         'مدير نظام'),
            ('sa_security.group_pms_manager',       'مدير عقارات'),
            ('sa_security.group_pms_accountant',    'محاسب'),
            ('sa_security.group_pms_agent',         'موظف خدمة عملاء'),
            ('sa_security.group_pms_owner',         'مالك'),
            ('sa_security.group_pms_technician',    'فني صيانة'),
            ('sa_security.group_pms_tenant_portal', 'مستأجر (بوابة)'),
        ]
        # Collect group ids
        group_ids = {}
        for xml_id, label in roles:
            grp = self.env.ref(xml_id, raise_if_not_found=False)
            if grp:
                group_ids[grp.id] = label

        for u in self:
            label = ''
            for gid, lbl in group_ids.items():
                if gid in u.groups_id.ids:
                    label = lbl
                    break  # picks the first/highest-priority match
            u.pms_role_label = label
