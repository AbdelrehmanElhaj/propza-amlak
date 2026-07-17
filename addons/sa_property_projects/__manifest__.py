{
    'name': 'المشاريع العقارية',
    'name_en': 'Saudi Real Estate Development Projects',
    'version': '17.0.1.0.0',
    'category': 'Real Estate',
    'summary': 'إدارة المشاريع العقارية التطويرية وربطها بالوحدات ومعرض الصور والمخططات',
    'author': 'Abdelrehman Elhaj',
    'website': 'https://proptech.sa',
    'license': 'LGPL-3',
    'depends': ['sa_property_base', 'l10n_sa_ejar', 'sa_security'],
    'data': [
        'security/ir.model.access.csv',
        'views/sa_project_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
