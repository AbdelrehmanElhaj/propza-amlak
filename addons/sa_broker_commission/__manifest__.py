# -*- coding: utf-8 -*-
{
    'name': 'عمولات الوسطاء العقاريين',
    'name_en': 'Saudi Broker Commissions',
    'version': '17.0.1.0.0',
    'category': 'Real Estate',
    'summary': 'إدارة عمولات الوسطاء: نسبة من الإيجار، جدول دفع، سندات تلقائية',
    'description': """
        Saudi Broker Commissions
        ========================
        إدارة كاملة لعمولات الوسطاء العقاريين:
            * عقد عمولة لكل عقد إيجار يأتي عبر وسيط
            * نسبة من الإيجار السنوي أو مبلغ ثابت
            * 3 أنماط دفع: مرة واحدة عند التوقيع / شهري / مقسَّط
            * توليد فواتير الموردين (vendor bills) تلقائياً
            * تقرير عمولات الوسيط الشهري والسنوي
            * تكامل كامل مع المحاسبة + تخصيص الجولة 5 (الصلاحيات)
    """,
    'author': 'Abdelrehman Elhaj',
    'website': 'https://proptech.sa',
    'license': 'LGPL-3',
    'depends': [
        'mail',
        'account',
        'sa_property_base',
        'sa_property',
        'sa_rental_cycle',
        'sa_security',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/sa_broker_commission_views.xml',
        'views/property_tenancy_views.xml',
        'views/res_partner_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'auto_install': False,
}
