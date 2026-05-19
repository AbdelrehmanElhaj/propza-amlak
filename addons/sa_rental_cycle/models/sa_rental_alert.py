from odoo import models, fields, api, _
from datetime import date


class SaRentalAlert(models.Model):
    """تنبيهات دورة الإيجار — انتهاء العقد، تأخر الدفع"""
    _name = 'sa.rental.alert'
    _description = 'تنبيه إيجاري'
    _inherit = ['mail.thread']
    _order = 'create_date desc'

    name = fields.Char(string='التنبيه', required=True)
    tenancy_id = fields.Many2one('property.tenancy', string='عقد الإيجار')
    alert_type = fields.Selection([
        ('expiry_30',   'انتهاء العقد خلال 30 يوم'),
        ('expiry_14',   'انتهاء العقد خلال 14 يوم'),
        ('overdue',     'دفعة متأخرة'),
        ('ejar_expire', 'انتهاء توثيق إيجار'),
    ], string='نوع التنبيه')
    state = fields.Selection([
        ('active',   'نشط'),
        ('resolved', 'تم التعامل معه'),
    ], default='active')
    resolved_date = fields.Date(string='تاريخ الحل')

    def action_resolve(self):
        self.write({'state': 'resolved', 'resolved_date': date.today()})


class SaRentalAlertCron(models.Model):
    """وظائف الـ cron لتوليد التنبيهات"""
    _inherit = 'property.tenancy'

    def cron_check_expiry_alerts(self):
        """يتحقق من العقود المنتهية قريباً — يُشغَّل يومياً"""
        today = date.today()
        Alert = self.env['sa.rental.alert']

        # عقود تنتهي خلال 30 يوم
        tenancies_30 = self.search([
            ('state', '=', 'running'),
            ('end_date', '!=', False),
        ])
        for t in tenancies_30:
            if not t.end_date:
                continue
            days = (t.end_date - today).days
            if days == 30:
                existing = Alert.search([
                    ('tenancy_id', '=', t.id),
                    ('alert_type', '=', 'expiry_30'),
                    ('state', '=', 'active'),
                ])
                if not existing:
                    Alert.create({
                        'name': f'عقد {t.name} ينتهي خلال 30 يوم',
                        'tenancy_id': t.id,
                        'alert_type': 'expiry_30',
                    })
                    t.message_post(
                        body=_('تنبيه: عقد الإيجار ينتهي خلال 30 يوماً في %s') % t.end_date,
                        message_type='notification',
                        subtype_xmlid='mail.mt_note',
                    )
            elif days == 14:
                existing = Alert.search([
                    ('tenancy_id', '=', t.id),
                    ('alert_type', '=', 'expiry_14'),
                    ('state', '=', 'active'),
                ])
                if not existing:
                    Alert.create({
                        'name': f'عقد {t.name} ينتهي خلال 14 يوم',
                        'tenancy_id': t.id,
                        'alert_type': 'expiry_14',
                    })

        # تحديث حالة الدفعات المتأخرة
        self.env['sa.rent.payment'].action_mark_overdue()
