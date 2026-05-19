# -*- coding: utf-8 -*-
{
    'name': 'بوابة المستأجر',
    'name_en': 'Saudi PMS Tenant Portal',
    'version': '17.0.1.0.0',
    'category': 'Real Estate',
    'summary': 'بوابة /my/... للمستأجرين: عقد، دفعات، صيانة، معاينات',
    'description': """
        Tenant Portal
        =============
        صفحات بوابة مخصَّصة:
        * /my/contracts        — عقد الإيجار + معلومات العقار
        * /my/payments         — جدول الدفعات + كشف حساب
        * /my/maintenance      — طلبات الصيانة + إنشاء طلب جديد
        * /my/inspections      — تقارير المعاينة (للقراءة فقط)

        تستخدم record rules من sa_security لتقييد الرؤية.
    """,
    'author': 'Abdelrehman Elhaj',
    'website': 'https://proptech.sa',
    'license': 'LGPL-3',
    'depends': [
        'portal',
        'sa_security',
        'sa_property_base',
        'sa_rental_cycle',
        'sa_maintenance',
    ],
    'data': [
        'views/portal_templates.xml',
    ],
    'assets': {
        'web.assets_frontend_lazy': [
            'sa_portal/static/src/js/portal_counter_fix.js',
        ],
    },
    'installable': True,
    'auto_install': False,
}
