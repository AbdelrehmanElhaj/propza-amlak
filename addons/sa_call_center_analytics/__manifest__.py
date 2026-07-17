# -*- coding: utf-8 -*-
{
    'name': 'تحليلات مركز الاتصال والتواصل مع العملاء',
    'name_en': 'Saudi PMS Call Center Communication Analytics',
    'version': '17.0.1.0.0',
    'category': 'Real Estate',
    'summary': 'تحليلات تواصل العملاء: عملاء فريدون، تكرار الاتصال، إجمالي وقت التحدث، لوحة تحكم وتقارير محورية',
    'description': """
        Saudi PMS Call Center Communication Analytics
        ===============================================
        - إحصاءات تواصل مجمّعة (عملاء فريدون، مكالمات مكررة، إجمالي وقت التحدث)
          عبر sa.call.center.call.get_communication_stats()
        - حقول محسوبة (غير مخزّنة) على ملف العميل: إجمالي وقت التحدث،
          عدد الاتصالات المكررة، تاريخ أول/آخر تواصل
        - حقول مرتبطة على طلب CRM تعكس نفس إحصاءات العميل
        - لوحة تحكم تحليلية (/callcenter/analytics) بفلاتر تاريخ وموظف
        - إجراء عرض محوري (Pivot/Graph) جديد لمكالمات مركز الاتصال

        هذه الوحدة للقراءة/التحليل فقط ولا تُعدّل مسار استقبال المكالمات (webhook) في sa_call_center.
    """,
    'author': 'Abdelrehman Elhaj',
    'website': 'https://proptech.sa',
    'license': 'LGPL-3',
    'depends': [
        'sa_call_center',
    ],
    'data': [
        'views/call_center_call_views.xml',
        'views/res_partner_views.xml',
        'views/sa_crm_lead_views.xml',
        'views/analytics_dashboard_template.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sa_call_center_analytics/static/src/analytics_dashboard_action.js',
            'sa_call_center_analytics/static/src/analytics_dashboard_action.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
}
