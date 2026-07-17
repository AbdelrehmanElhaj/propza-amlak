# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class SaProject(models.Model):
    """مشروع عقاري (تطوير) — يجمّع عدداً من الوحدات (property.property)
    تحت مشروع تطويري واحد، مع معرض وسائط (صور / مخططات / بروشورات).
    """
    _name = 'sa.project'
    _description = 'مشروع عقاري (تطوير)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    # ─── Identity ──────────────────────────────────────────────
    name = fields.Char(string='اسم المشروع', required=True, tracking=True, index=True)
    active = fields.Boolean(default=True, tracking=True)
    description = fields.Text(string='الوصف')
    developer_partner_id = fields.Many2one(
        'res.partner', string='المطوّر العقاري', tracking=True,
    )

    # ─── العنوان الوطني / الموقع ────────────────────────────────
    sa_region_id = fields.Many2one('sa.region', string='المنطقة الإدارية')
    sa_city_id = fields.Many2one(
        'sa.city', string='المدينة',
        domain="[('region_id','=',sa_region_id)]",
    )
    sa_district = fields.Char(string='الحي')
    sa_national_address = fields.Char(string='رقم العنوان الوطني')

    # ─── الحالة ───────────────────────────────────────────────
    state = fields.Selection([
        ('planning', 'تخطيط'),
        ('under_construction', 'تحت الإنشاء'),
        ('ready', 'جاهز'),
        ('completed', 'مكتمل'),
    ], string='الحالة', default='planning', tracking=True)

    # ─── الوحدات ─────────────────────────────────────────────────
    unit_ids = fields.One2many('property.property', 'project_id', string='الوحدات')
    unit_count = fields.Integer(string='عدد الوحدات', compute='_compute_unit_count')

    # ─── معرض الوسائط ────────────────────────────────────────────
    image_ids = fields.One2many('sa.project.image', 'project_id', string='الوسائط')
    floor_plan_count = fields.Integer(string='عدد المخططات', compute='_compute_media_counts')
    photo_count = fields.Integer(string='عدد الصور', compute='_compute_media_counts')

    @api.depends('unit_ids')
    def _compute_unit_count(self):
        for rec in self:
            rec.unit_count = len(rec.unit_ids)

    @api.depends('image_ids.media_type')
    def _compute_media_counts(self):
        for rec in self:
            rec.floor_plan_count = len(rec.image_ids.filtered(lambda i: i.media_type == 'floor_plan'))
            rec.photo_count = len(rec.image_ids.filtered(lambda i: i.media_type == 'photo'))

    # ─── Actions ──────────────────────────────────────────────────
    def action_view_units(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('sa_property_base.action_property_property')
        action['domain'] = [('project_id', '=', self.id)]
        action['context'] = {'default_project_id': self.id}
        return action
