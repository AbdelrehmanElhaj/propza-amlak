# -*- coding: utf-8 -*-
{
    'name': 'نظام التنبيهات لإدارة العقارات',
    'name_en': 'Saudi PMS Notifications',
    'version': '17.0.1.0.0',
    'category': 'Real Estate',
    'summary': 'تنبيهات بالبريد الإلكتروني: تذكير دفعات، انتهاء عقود، صيانة',
    'description': """
        Saudi PMS Notifications
        =======================
        7 قوالب بريد عربية + 4 cron jobs + auto-triggers:
            * تذكير الدفعة قبل الاستحقاق بـ 7 أيام
            * تنبيه دفعة متأخرة
            * تنبيه عقد ينتهي قريباً (60/30/14 يوم)
            * تأكيد استلام طلب الصيانة (للمستأجر)
            * إشعار الفني بأمر العمل المُسنَد
            * إشعار المستأجر بإكمال الصيانة
            * إشعار التجديد التلقائي

        إعدادات قابلة للتخصيص لكل نوع تنبيه.
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
