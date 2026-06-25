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

    # ─── Unifonic WhatsApp / SMS ──────────────────────────────────────
    sa_unifonic_enabled = fields.Boolean(
        string='تفعيل Unifonic (WhatsApp + SMS)',
        config_parameter='sa_notifications.unifonic_enabled',
        default=False,
    )
    sa_whatsapp_enabled = fields.Boolean(
        string='إرسال عبر WhatsApp',
        config_parameter='sa_notifications.whatsapp_enabled',
        default=True,
    )
    sa_sms_enabled = fields.Boolean(
        string='إرسال عبر SMS (fallback)',
        config_parameter='sa_notifications.sms_enabled',
        default=True,
    )
    sa_unifonic_app_sid = fields.Char(
        string='Unifonic App SID (SMS)',
        config_parameter='sa_notifications.unifonic_app_sid',
    )
    sa_unifonic_sender_id = fields.Char(
        string='SMS Sender ID',
        config_parameter='sa_notifications.unifonic_sender_id',
        help='اسم المُرسِل SMS (مثال: Propza) — يجب أن يكون مسجلاً في Unifonic',
    )
    sa_unifonic_token = fields.Char(
        string='Unifonic Bearer Token (WhatsApp)',
        config_parameter='sa_notifications.unifonic_token',
    )
    sa_unifonic_whatsapp_sender = fields.Char(
        string='WhatsApp Sender Number',
        config_parameter='sa_notifications.unifonic_whatsapp_sender',
        help='رقم WhatsApp Business المُسجَّل في Unifonic (مثال: 9665XXXXXXXX)',
    )

    # ─── Multi-provider gateway selector ─────────────────────────────
    sa_messaging_provider = fields.Selection(
        selection=[
            ('disabled', 'معطّل'),
            ('unifonic', 'Unifonic (WhatsApp + SMS)'),
            ('ultramsg', 'UltraMsg (WhatsApp فقط)'),
        ],
        string='مزوّد الرسائل',
        config_parameter='sa_notifications.messaging_provider',
        default='disabled',
    )

    # ─── UltraMsg credentials ─────────────────────────────────────────
    sa_ultramsg_instance_id = fields.Char(
        string='UltraMsg Instance ID',
        config_parameter='sa_notifications.ultramsg_instance_id',
        help='مثال: instance123456 — تجده في لوحة تحكم UltraMsg',
    )
    sa_ultramsg_token = fields.Char(
        string='UltraMsg Token',
        config_parameter='sa_notifications.ultramsg_token',
    )
