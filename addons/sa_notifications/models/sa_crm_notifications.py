# -*- coding: utf-8 -*-
"""CRM auto-triggers: WhatsApp/SMS on showing scheduled, reservation confirmed, deal closed."""
from odoo import models, api, _


class SaCrmShowingNotifications(models.Model):
    _inherit = 'sa.crm.showing'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        unifonic = self.env['sa.unifonic.service']
        for showing in records:
            partner = showing.lead_id.partner_id
            phone = unifonic._partner_phone(partner)
            if phone:
                prop_name = showing.property_id.name or ''
                scheduled = showing.scheduled_date.strftime('%Y-%m-%d %H:%M') if showing.scheduled_date else ''
                msg = (
                    f"عزيزنا {partner.name}،\n"
                    f"تم جدولة جولة ميدانية للعقار: {prop_name}\n"
                    f"الموعد: {scheduled}\n"
                    f"يرجى الحضور في الوقت المحدد."
                )
                unifonic._send_whatsapp_sms(phone, msg)
        return records


class SaCrmReservationNotifications(models.Model):
    _inherit = 'sa.crm.reservation'

    def action_activate(self):
        res = super().action_activate()
        unifonic = self.env['sa.unifonic.service']
        for rec in self:
            partner = rec.partner_id
            phone = unifonic._partner_phone(partner)
            if phone:
                prop_name = rec.property_id.name or ''
                date_end = rec.date_end or ''
                msg = (
                    f"عزيزنا {partner.name}،\n"
                    f"تم تأكيد حجزك للعقار: {prop_name}\n"
                    f"الحجز ساري حتى: {date_end}\n"
                    f"رقم الحجز: {rec.name}"
                )
                unifonic._send_whatsapp_sms(phone, msg)
        return res

    def action_convert_to_deal(self):
        res = super().action_convert_to_deal()
        unifonic = self.env['sa.unifonic.service']
        for rec in self:
            partner = rec.partner_id
            phone = unifonic._partner_phone(partner)
            if phone:
                prop_name = rec.property_id.name or ''
                msg = (
                    f"تهانينا {partner.name}!\n"
                    f"اكتملت صفقتك للعقار: {prop_name}\n"
                    f"سيتواصل معك فريقنا لإتمام إجراءات التعاقد."
                )
                unifonic._send_whatsapp_sms(phone, msg)
        return res
