# -*- coding: utf-8 -*-
{
    'name': 'أهداف المبيعات وقياس الأداء',
    'name_en': 'Sales Targets & Performance',
    'version': '17.0.1.0.0',
    'category': 'Real Estate',
    'summary': 'تحديد أهداف مبيعات (عمولات) شهرية/ربع سنوية/سنوية للموظفين والفرق، وقياس نسبة الإنجاز آلياً',
    'description': """
        Sales Targets & Performance
        ===========================
        * ربط عمولات الوسطاء بمندوب مبيعات (مستخدم) لأغراض قياس الأداء
        * فرق مبيعات (مدير + أعضاء)
        * أهداف مبيعات فردية أو على مستوى الفريق، لفترات شهرية/ربع سنوية/سنوية
        * احتساب المبلغ المحقَّق ونسبة الإنجاز آلياً من دفعات العمولات المُسدَّدة
    """,
    'author': 'Abdelrehman Elhaj',
    'website': 'https://proptech.sa',
    'license': 'LGPL-3',
    'depends': [
        'sa_broker_commission',
        'sa_crm',
        'sa_security',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/sa_sales_target_security.xml',
        'views/sa_sales_team_views.xml',
        'views/sa_sales_target_views.xml',
        'views/menu.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'auto_install': False,
    'application': False,
}
