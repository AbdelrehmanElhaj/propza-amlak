# -*- coding: utf-8 -*-
{
    'name': 'نظام التنبيهات لإدارة العقارات',
    'name_en': 'Saudi PMS Notifications',
    'version': '17.0.1.0.0',
    'category': 'Real Estate',
    'summary': 'تنبيهات بريد إلكتروني + WhatsApp + SMS عبر Unifonic',
    'description': """
        Saudi PMS Notifications
        =======================
        7 قوالب بريد عربية + WhatsApp/SMS عبر Unifonic + 3 cron jobs + auto-triggers:
            * تذكير الدفعة قبل الاستحقاق بـ 7 أيام (بريد + WA/SMS)
            * تنبيه دفعة متأخرة (بريد + WA/SMS)
            * تنبيه عقد ينتهي قريباً (بريد + WA/SMS)
            * تأكيد استلام طلب الصيانة (بريد + WA/SMS)
            * إشعار الفني بأمر العمل المُسنَد (بريد + WA/SMS)
            * إشعار المستأجر بإكمال الصيانة (بريد + WA/SMS)
            * إشعار التجديد التلقائي (بريد + WA/SMS)

        WhatsApp أولاً، SMS كـ fallback تلقائي. إعدادات قابلة للتخصيص.
    """,
    'author': 'Abdelrehman Elhaj',
    'website': 'https://proptech.sa',
    'license': 'LGPL-3',
    'depends': [
        'mail',
        'sa_property_base',
        'sa_property',
        'sa_rental_cycle',
        'sa_maintenance',
        'sa_crm',
        'sa_security',
    ],
    'data': [
        'data/mail_templates.xml',
        'data/ir_cron_data.xml',
        'data/notification_config.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
