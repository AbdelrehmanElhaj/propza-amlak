# -*- coding: utf-8 -*-
{
    'name': 'SA Theme - Login Landing Page',
    'version': '17.0.1.0.0',
    'category': 'Real Estate',
    'summary': 'صفحة هبوط احترافية مع دعم RTL وتصميم مخصص لمنصة أملاك',
    'author': 'Abdelrehman Elhaj',
    'website': 'https://proptech.sa',
    'license': 'LGPL-3',
    'depends': ['web'],
    'data': [
        'views/login_template.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'sa_theme/static/src/css/login.css',
        ],
    },
    'installable': True,
    'auto_install': False,
}
