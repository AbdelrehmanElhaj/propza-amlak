# -*- coding: utf-8 -*-
{
    'name': 'إدارة الصيانة',
    'name_en': 'Saudi Property Maintenance',
    'version': '17.0.1.0.0',
    'category': 'Real Estate',
    'summary': 'نظام صيانة العقارات: طلبات، مقاولين، تكاليف تفصيلية، صور قبل/بعد',
    'description': """
        نظام إدارة الصيانة العقارية للسوق السعودي
        ===========================================
        - طلبات صيانة بفئات سعودية (سباكة، كهرباء، تكييف، …)
        - إدارة المقاولين والفنيين مع تخصصاتهم وأسعارهم
        - تتبع تكاليف تفصيلية: مواد، عمالة، مواصلات
        - مرفقات: صور قبل/بعد، عروض أسعار، فواتير المقاول
        - تكامل مع العقار والإيجار من sa_property_base
    """,
    'author': 'Abdelrehman Elhaj',
    'website': 'https://proptech.sa',
    'license': 'LGPL-3',
    'depends': [
        'sa_property_base',
        'sa_security',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/sa_maintenance_security.xml',
        'data/sequence.xml',
        'data/maintenance_skills_data.xml',
        'data/cron.xml',
        'views/menu_root.xml',
        'views/maintenance_skill_views.xml',
        'views/res_partner_views.xml',
        'views/maintenance_contract_views.xml',
        'views/maintenance_work_order_views.xml',
        'views/maintenance_request_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
