{
    'name': 'نظام العقارات السعودي',
    'name_en': 'Saudi Property Management',
    'version': '17.0.1.0.0',
    'category': 'Real Estate',
    'summary': 'نموذج عقار سعودي أصيل — صك، عنوان وطني، هوية، إيجار',
    'description': """
        نظام إدارة العقارات للسوق السعودي
        =====================================
        - نموذج عقار سعودي بحت (فيلا، شقة، دور، ملحق، أرض، محل، مكتب، مستودع)
        - الصك وأنواعه وبيانات المالك
        - العنوان الوطني والمناطق الإدارية السعودية
        - هوية المستأجر (وطنية / إقامة / خليجي)
        - دورة الإيجار الكاملة مع تجميد الرياض
        - جاهز للربط بمنصة إيجار
    """,
    'author': 'Abdelrehman Elhaj',
    'license': 'LGPL-3',
    'depends': [
        'sa_property_base',
        'l10n_sa_ejar',
        'account',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sa_property_types.xml',
        'views/sa_property_views.xml',
        'views/sa_tenancy_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
