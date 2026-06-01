{
    'name': 'AI Property Match for CRM',
    'summary': 'اقتراح عقارات مطابقة لطلبات العملاء باستخدام توصية ذكية',
    'version': '17.0.1.0.0',
    'category': 'Real Estate',
    'author': 'Abdelrehman Elhaj',
    'website': 'https://proptech.sa',
    'license': 'LGPL-3',
    'depends': ['sa_crm', 'sa_property_base'],
    'data': [
        'views/sa_crm_lead_match_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
