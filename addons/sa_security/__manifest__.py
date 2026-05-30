# -*- coding: utf-8 -*-
{
    'name': 'الأمن والصلاحيات لإدارة العقارات',
    'name_en': 'Saudi PMS Security & Roles',
    'version': '17.0.1.0.0',
    'category': 'Real Estate',
    'summary': 'نظام أدوار وصلاحيات متكامل: 7 أدوار + record rules + بوابة',
    'description': """
        Saudi PMS Security
        ==================
        7 أدوار:
            * مدير النظام  (Admin)
            * مدير العقارات (Manager)
            * محاسب عقارات (Accountant)
            * موظف خدمة عملاء (Agent)
            * مالك عقار (Owner) — مستخدم داخلي
            * فني صيانة (Technician)
            * مستأجر (Tenant Portal)

        - Record rules تفرض رؤية البيانات الخاصة فقط لكل دور
        - Tenant portal مع وصول /my/...
        - بنية صلاحيات متوافقة مع ZATCA Phase 2
    """,
    'author': 'Abdelrehman Elhaj',
    'website': 'https://proptech.sa',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'portal',
        'contacts',
        'sa_property_base',
        'sa_property',
        'l10n_sa_ejar',
        'sa_rental_cycle',
        'sa_maintenance',
        'sa_crm',
        'account',
    ],
    'data': [
        'data/res_groups_data.xml',
        'security/ir.model.access.csv',
        'data/ir_rule_data.xml',
        'views/res_partner_views.xml',
        'views/role_admin_views.xml',
        'views/field_security_views.xml',
        'views/audit_log_views.xml',
        'data/menu_overrides.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
