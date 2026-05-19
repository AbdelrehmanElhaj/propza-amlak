# -*- coding: utf-8 -*-
"""صفحة إعدادات للمسؤول: تشغيل/إيقاف كل نوع تنبيه."""
from odoo import models, fields


class ResConfigSettingsNotifications(models.TransientModel):
    _inherit = 'res.config.settings'

    sa_payment_reminder_enabled = fields.Boolean(
        string='تذكير الدفعات قبل الاستحقاق',
        config_parameter='sa_notifications.payment_reminder_enabled',
        default=True,
    )
    sa_payment_reminder_days = fields.Integer(
        string='عدد الأيام قبل الاستحقاق',
        config_parameter='sa_notifications.payment_reminder_days',
        default=7,
    )
    sa_payment_overdue_enabled = fields.Boolean(
        string='تنبيه الدفعات المتأخرة',
        config_parameter='sa_notifications.payment_overdue_enabled',
        default=True,
    )
    sa_contract_expiring_enabled = fields.Boolean(
        string='تنبيه عقود تنتهي قريباً',
        config_parameter='sa_notifications.contract_expiring_enabled',
        default=True,
    )
    sa_contract_expiring_days = fields.Integer(
        string='عدد الأيام قبل انتهاء العقد',
        config_parameter='sa_notifications.contract_expiring_days',
        default=30,
    )
    sa_maintenance_received_enabled = fields.Boolean(
        string='تأكيد استلام طلب الصيانة',
        config_parameter='sa_notifications.maintenance_received_enabled',
        default=True,
    )
    sa_maintenance_assigned_enabled = fields.Boolean(
        string='إشعار الفني بأمر العمل',
        config_parameter='sa_notifications.maintenance_assigned_enabled',
        default=True,
    )
    sa_maintenance_completed_enabled = fields.Boolean(
        string='إشعار إكمال الصيانة',
        config_parameter='sa_notifications.maintenance_completed_enabled',
        default=True,
    )
    sa_renewal_proposed_enabled = fields.Boolean(
        string='إشعار اقتراح التجديد',
        config_parameter='sa_notifications.renewal_proposed_enabled',
        default=True,
    )
