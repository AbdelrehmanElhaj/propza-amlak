# -*- coding: utf-8 -*-
{
    'name': 'ملف المستخدم — User Profile',
    'version': '17.0.1.0.0',
    'category': 'Real Estate',
    'summary': 'إدارة الملف الشخصي: معلومات، عنوان وطني، توثيق، وثائق، صلاحيات، سجل النشاط',
    'author': 'Abdelrehman Elhaj',
    'license': 'LGPL-3',
    'depends': [
        'portal',
        'mail',
        'sa_security',
        'sa_property_base',
        'l10n_sa_ejar',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/sa_user_verification_views.xml',
        'views/sa_user_document_views.xml',
        'views/res_partner_profile_views.xml',
        'views/portal_profile_templates.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
