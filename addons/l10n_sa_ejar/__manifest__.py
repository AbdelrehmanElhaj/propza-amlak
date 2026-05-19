{
    'name': 'Saudi Arabia - Ejar Integration',
    'name_ar': 'تكامل منصة إيجار - المملكة العربية السعودية',
    'version': '17.0.1.0.0',
    'category': 'Real Estate',
    'summary': 'Ejar platform integration for Saudi real estate rental management',
    'description': """
        Saudi Arabia - Ejar Platform Integration
        =========================================
        - Saudi administrative regions (14 regions)
        - National address fields (رقم العنوان الوطني)
        - Property deed number (رقم الصك)
        - Tenant national ID / Iqama
        - Ejar contract fields and status tracking
        - Ejar API connector (ready for credentials)
        - Rent freeze rules (Riyadh 5-year freeze 2025)
        - SADAD payment reference
    """,
    'author': 'Abdelrehman Elhaj',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'sa_property_base',
        'account',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sa_regions_data.xml',
        'data/ejar_sequence.xml',
        'views/sa_region_views.xml',
        'views/property_property_views.xml',
        'views/property_tenancy_views.xml',
        'views/res_partner_views.xml',
        'views/ejar_contract_views.xml',
        'views/menu.xml',
        'wizard/ejar_sync_wizard_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
