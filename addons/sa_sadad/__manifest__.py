# -*- coding: utf-8 -*-
{
    'name': 'محاكاة SADAD للدفع',
    'name_en': 'Saudi SADAD Payment Simulator',
    'version': '17.0.1.0.0',
    'category': 'Real Estate',
    'summary': 'إصدار فواتير SADAD + QR + webhook محاكي للدفع',
    'description': """
        Saudi SADAD Simulator
        =====================
        محاكاة كاملة لمنظومة SADAD لأغراض الاختبار والتطوير:
            * إصدار رقم فاتورة 15 رقم بصيغة SADAD
            * توليد QR code للدفع
            * webhook endpoint يحاكي callback من SADAD
            * عند الدفع: يحدّث sa.rent.payment تلقائياً
            * إيصال PDF للدفع
            * إعدادات: biller_code، مدة صلاحية الفاتورة

        ملاحظة: هذا للمحاكاة. لـ SADAD حقيقي يحتاج اتفاقية مع SAMA + بنك.
    """,
    'author': 'Abdelrehman Elhaj',
    'website': 'https://proptech.sa',
    'license': 'LGPL-3',
    'depends': [
        'mail',
        'sa_property_base',
        'sa_rental_cycle',
        'sa_security',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/ir_config.xml',
        'views/sa_sadad_invoice_views.xml',
        'views/sa_rent_payment_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu.xml',
        'report/sadad_receipt.xml',
    ],
    'installable': True,
    'auto_install': False,
}
