# -*- coding: utf-8 -*-
from . import models


def post_init_hook(env):
    """يُعبّئ salesperson_user_id لعقود العمولة القائمة التي لا تملك بعد
    مستخدماً مرتبطاً، بالاعتماد على المستخدم المرتبط بجهة اتصال الوسيط
    (broker_partner_id.user_ids). يعمل هذا فقط عند أول تثبيت للموديول
    (new_install) على السجلات الموجودة مسبقاً.

    ملاحظة على التوقيع: في Odoo 17 يستدعي المُحمِّل post_init_hook بوسيط
    واحد فقط هو `env` (وليس `cr, registry` كما في إصدارات أقدم) —
    راجع odoo/modules/loading.py: `getattr(py_module, post_init)(env)`.
    """
    commissions = env['sa.broker.commission'].search([
        ('salesperson_user_id', '=', False),
    ])
    for comm in commissions:
        users = comm.broker_partner_id.user_ids
        if users:
            comm.salesperson_user_id = users[0].id
