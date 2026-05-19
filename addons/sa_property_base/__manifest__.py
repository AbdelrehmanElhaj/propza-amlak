# -*- coding: utf-8 -*-
{
    'name': 'Saudi Property Base',
    'name_ar': 'الأساس السعودي لإدارة العقارات',
    'version': '17.0.1.0.0',
    'category': 'Real Estate',
    'summary': 'Lean Saudi-first base for property and tenancy models',
    'description': """
        Saudi Property Base
        ===================
        Minimal, Saudi-market-shaped base providing:
        - property.property model (10 essential fields)
        - property.tenancy model (13 fields + state machine)
        - Mail / activity tracking via mixins
        - No vendor lock-in, no booking/CRM/portal bloat

        Designed to replace third-party general-purpose property modules.
        Built to be extended by l10n_sa_ejar, sa_property, sa_rental_cycle.
    """,
    'author': 'Abdelrehman Elhaj',
    'website': 'https://proptech.sa',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'account',  # for currency_id, journal references in extending modules
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/menu_root.xml',
        'views/property_property_views.xml',
        'views/property_tenancy_views.xml',
        'views/property_inspection_views.xml',
        'views/partner_views.xml',
        'views/menu.xml',
        'data/hide_unused_menus.xml',
        'report/inspection_report.xml',
        'report/lease_contract_report.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}
