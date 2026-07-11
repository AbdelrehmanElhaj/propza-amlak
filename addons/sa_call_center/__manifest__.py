# -*- coding: utf-8 -*-
{
    'name': 'مركز الاتصال الذكي',
    'name_en': 'Saudi PMS Smart Call Center',
    'version': '17.0.1.0.0',
    'category': 'Real Estate',
    'summary': 'مكالمات مرتبطة بالعملاء والعقود والصيانة + تذاكر خفيفة + تقرير أساسي',
    'description': """
        Saudi PMS Smart Call Center — المرحلة 1
        ========================================
        - سجل موحّد لكل مكالمة واردة/صادرة (`sa.call.center.call`)
        - بحث تلقائي عن العميل بالرقم عبر بوابة اتصالات عامة قابلة للتوسع لأي مزود PBX/VoIP
        - webhook لاستقبال أحداث المكالمات من نظام الاتصالات (Asterisk أو غيره)
        - محول Twilio فعلي: استقبال مكالمات واردة (Voice + Status webhooks بتوقيع HMAC)
          وتحويلها لرقم ثابت، بالإضافة لاتصال صادر (click-to-dial) عبر REST API
        - سمّاعة متصفح (Twilio Voice JS SDK): يرد الموظف على المكالمة من داخل Odoo مباشرة،
          بالتوازي مع رقم التحويل الثابت
        - ربط المكالمة بأي سجل قائم (CRM / صيانة / دفعة / عقد) أو تذكرة خفيفة جديدة
        - زر "مكالمات" على ملف العميل
        - تقرير أساسي (حجم المكالمات، متوسط الانتظار، متوسط المدة، الفائتة)

        Screen Pop اللحظي وتوجيه المكالمات حسب أعضاء القائمة يأتيان في مرحلة لاحقة.
    """,
    'author': 'Abdelrehman Elhaj',
    'website': 'https://proptech.sa',
    'license': 'LGPL-3',
    'depends': [
        'mail',
        'sa_property_base',
        'sa_crm',
        'sa_maintenance',
        'sa_rental_cycle',
        'sa_notifications',
        'sa_security',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/ir_cron_data.xml',
        'views/call_center_call_views.xml',
        'views/call_center_queue_views.xml',
        'views/call_center_ticket_views.xml',
        'views/res_partner_views.xml',
        'views/sa_crm_lead_views.xml',
        'views/res_users_views.xml',
        'views/res_config_settings_views.xml',
        'views/dashboard_template.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sa_call_center/static/src/dashboard_action.js',
            'sa_call_center/static/src/dashboard_action.xml',
            'sa_call_center/static/src/js/softphone_state.js',
            'sa_call_center/static/src/js/softphone.js',
            'sa_call_center/static/src/js/softphone.xml',
            'sa_call_center/static/src/js/call_center_phone_field.js',
            'sa_call_center/static/src/js/call_center_phone_field.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
}
