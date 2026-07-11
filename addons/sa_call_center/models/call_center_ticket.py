# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaCallCenterTicket(models.Model):
    """تذكرة خفيفة — فقط للحالات التي لا تناسب نموذجاً قائماً (شكوى/استفسار عام).

    عند وجود نموذج مناسب (طلب CRM أو طلب صيانة) تُحوَّل التذكرة إليه بدل
    إبقائها كسجل منفصل، لتفادي ازدواجية البيانات.
    """
    _name = 'sa.call.center.ticket'
    _description = 'تذكرة مركز الاتصال'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(
        string='رقم التذكرة', readonly=True, copy=False,
        default=lambda s: _('جديد'),
    )
    partner_id = fields.Many2one('res.partner', string='العميل', tracking=True)
    call_id = fields.Many2one('sa.call.center.call', string='المكالمة الأصلية', copy=False)
    property_id = fields.Many2one('property.property', string='العقار (إن وجد)')
    description = fields.Text(string='الوصف', required=True, tracking=True)
    category = fields.Selection([
        ('complaint', 'شكوى'),
        ('inquiry', 'استفسار'),
        ('other', 'أخرى'),
    ], string='التصنيف', default='inquiry', tracking=True)
    state = fields.Selection([
        ('new', 'جديدة'),
        ('in_progress', 'قيد المعالجة'),
        ('done', 'مغلقة'),
    ], string='الحالة', default='new', required=True, tracking=True, copy=False)
    user_id = fields.Many2one(
        'res.users', string='الموظف المسؤول',
        default=lambda s: s.env.user, tracking=True,
    )

    lead_id = fields.Many2one('sa.crm.lead', string='طلب CRM', copy=False)
    maintenance_request_id = fields.Many2one('sa.maintenance.request', string='طلب صيانة', copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('جديد')) == _('جديد'):
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code(
                    'sa.call.center.ticket') or _('جديد')
        return super().create(vals_list)

    def action_convert_to_lead(self):
        self.ensure_one()
        if self.lead_id:
            raise UserError(_('تم تحويل هذه التذكرة إلى طلب CRM بالفعل.'))
        if not self.partner_id:
            raise UserError(_('يجب تحديد العميل قبل التحويل إلى طلب CRM.'))
        lead = self.env['sa.crm.lead'].create({
            'partner_id': self.partner_id.id,
            'description': self.description,
            'source': 'phone',
        })
        self.write({'lead_id': lead.id, 'state': 'in_progress'})
        return {
            'name': _('طلب CRM'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.crm.lead',
            'view_mode': 'form',
            'res_id': lead.id,
        }

    def action_convert_to_maintenance(self):
        self.ensure_one()
        if self.maintenance_request_id:
            raise UserError(_('تم تحويل هذه التذكرة إلى طلب صيانة بالفعل.'))
        if not self.property_id:
            raise UserError(_('حدد العقار المرتبط قبل التحويل إلى طلب صيانة.'))
        request = self.env['sa.maintenance.request'].create({
            'property_id': self.property_id.id,
            'description': self.description,
            'category': 'other',
        })
        self.write({'maintenance_request_id': request.id, 'state': 'in_progress'})
        return {
            'name': _('طلب صيانة'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.maintenance.request',
            'view_mode': 'form',
            'res_id': request.id,
        }

    def action_close(self):
        for rec in self:
            rec.state = 'done'
