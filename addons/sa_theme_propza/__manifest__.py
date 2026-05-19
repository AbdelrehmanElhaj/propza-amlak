# -*- coding: utf-8 -*-
{
    'name': 'Propza Modern Theme',
    'name_en': 'Propza Modern Theme - Modern UI for Property Management',
    'version': '17.0.2.0.0',
    'category': 'Theme',
    'summary': 'Saudi-First identity theme for Propza — Saudi Green & Gold',
    'description': """
        Propza Saudi Theme
        ==================
        A Saudi-first identity theme built around the national color palette.

        Brand Colors:
        * Primary: Saudi Green #1B5E3B
        * Accent:  Gold        #C8A951

        Typography:
        * Tajawal (Arabic + Latin, Google Fonts)
        * Inter (Latin fallback)

        Features:
        * Deep Saudi green sidebar with gold active states
        * Subtle Islamic geometric pattern on sidebar
        * Gold accent highlights throughout
        * Warm off-white backgrounds
        * Full RTL / Arabic support (Tajawal font)
        * Saudi green focus rings on all form elements
        * Gradient KPI cards (green + gold variants)
        * Dark mode with green-tinted palette
        * Responsive for mobile, tablet, desktop
    """,
    'author': 'Abdelrehman Elhaj',
    'website': 'https://propza.sa',
    'license': 'LGPL-3',
    'depends': [
        'web',
        'base',
    ],
    'data': [
        'views/theme_config.xml',
        'views/layout_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # Theme CSS
            'sa_theme_propza/static/src/css/variables.css',
            'sa_theme_propza/static/src/css/base.css',
            'sa_theme_propza/static/src/css/layout.css',
            'sa_theme_propza/static/src/css/buttons.css',
            'sa_theme_propza/static/src/css/forms.css',
            'sa_theme_propza/static/src/css/cards.css',
            'sa_theme_propza/static/src/css/navigation.css',
            'sa_theme_propza/static/src/css/dashboard.css',
            'sa_theme_propza/static/src/css/property.css',
            'sa_theme_propza/static/src/css/tables.css',
            'sa_theme_propza/static/src/css/modals.css',
            'sa_theme_propza/static/src/css/animations.css',
            'sa_theme_propza/static/src/css/responsive.css',
            'sa_theme_propza/static/src/css/dark_mode.css',
            
            # Theme JavaScript
            'sa_theme_propza/static/src/js/theme.js',
            'sa_theme_propza/static/src/js/theme_toggle.js',
            'sa_theme_propza/static/src/js/property.js',
            'sa_theme_propza/static/src/js/animations.js',
        ],
        'web.assets_frontend': [
            # Frontend CSS
            'sa_theme_propza/static/src/css/variables.css',
            'sa_theme_propza/static/src/css/base.css',
            'sa_theme_propza/static/src/css/layout.css',
            'sa_theme_propza/static/src/css/buttons.css',
            'sa_theme_propza/static/src/css/forms.css',
            'sa_theme_propza/static/src/css/cards.css',
            'sa_theme_propza/static/src/css/property.css',
            'sa_theme_propza/static/src/css/responsive.css',
            'sa_theme_propza/static/src/css/animations.css',
            
            # Frontend JavaScript
            'sa_theme_propza/static/src/js/theme.js',
        ],
    },
    'images': [
        'static/description/icon.png',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}
