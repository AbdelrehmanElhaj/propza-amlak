# -*- coding: utf-8 -*-
{
    'name': 'لوحة تحكم إدارة العقارات',
    'name_en': 'Saudi PMS Dashboard',
    'version': '17.0.1.0.0',
    'category': 'Real Estate',
    'summary': 'لوحة تحكم تفاعلية بـ Chart.js: KPIs + اتجاهات الإيرادات + إشغال + صيانة',
    'description': """
        Saudi PMS Dashboard 2.0
        =======================
        لوحة تفاعلية لإدارة العقارات:
            * KPIs عليا: عقارات / مؤجَّر / إيراد / متأخرات
            * Revenue trend chart (12 شهر)
            * Property occupancy donut
            * Maintenance cost by category
            * Top 5 overdue tenants
            * Top 5 expiring contracts

        تستخدم Chart.js من CDN مع تكامل كامل مع record rules
        (المستخدم يرى ما يحق له فقط).
    """,
    'author': 'Abdelrehman Elhaj',
    'website': 'https://proptech.sa',
    'license': 'LGPL-3',
    'depends': [
        'sa_property_base',
        'sa_property',
        'sa_rental_cycle',
        'sa_maintenance',
        'sa_security',
        'sa_broker_commission',
    ],
    'data': [
        'views/dashboard_template.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sa_dashboard/static/src/dashboard_action.js',
            'sa_dashboard/static/src/dashboard_action.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
}
