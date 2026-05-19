# -*- coding: utf-8 -*-
{
    'name': 'تطبيق الفني الميداني',
    'name_en': 'Saudi PMS Mobile Technician',
    'version': '17.0.1.0.0',
    'category': 'Real Estate',
    'summary': 'واجهة محسَّنة للموبايل للفنيين الميدانيين: kanban + صور قبل/بعد + workflow مبسَّط',
    'description': """
        Saudi PMS Mobile Technician
        ===========================
        تحسينات للفني العامل ميدانياً عبر التليفون:
            * Kanban "أعمالي اليوم" — عرض الـ WOs المُسنَدة بـ swipe friendly
            * Form view مبسَّطة عمود واحد + أزرار كبيرة
            * صور قبل + بعد لكل أمر عمل
            * أزرار state machine بأيقونات واضحة
            * Mobile-first CSS responsive
            * default landing page للفني = kanban أعماله

        يستهدف group_pms_technician (الفني الميداني).
    """,
    'author': 'Abdelrehman Elhaj',
    'website': 'https://proptech.sa',
    'license': 'LGPL-3',
    'depends': [
        'sa_maintenance',
        'sa_security',
    ],
    'data': [
        'views/work_order_mobile_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sa_mobile_tech/static/src/mobile_tech.css',
        ],
    },
    'installable': True,
    'auto_install': False,
}
