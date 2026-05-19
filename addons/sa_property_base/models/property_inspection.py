# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PropertyInspection(models.Model):
    """معاينة عقار — تقرير حالة العقار وقت الاستلام/التسليم.

    أنواع المعاينة:
        * move_in:  استلام المستأجر للوحدة في بداية العقد
        * move_out: تسليم المستأجر للوحدة في نهاية العقد
        * interim: معاينة دورية أثناء العقد

    تُستخدم لاحقاً في معالج إنهاء العقد لاحتساب الخصومات من الضمان.
    """
    _name = 'sa.property.inspection'
    _description = 'معاينة عقار'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'inspection_date desc, id desc'

    # ─── Identity ─────────────────────────────────────────────────
    name = fields.Char(
        string='المرجع', required=True, copy=False,
        readonly=True, default=lambda s: _('جديد'), tracking=True,
    )

    # ─── Linkage ──────────────────────────────────────────────────
    tenancy_id = fields.Many2one(
        'property.tenancy', string='عقد الإيجار',
        ondelete='set null', tracking=True,
    )
    property_id = fields.Many2one(
        'property.property', string='العقار',
        required=True, tracking=True, ondelete='restrict',
    )
    tenant_partner_id = fields.Many2one(
        'res.partner', string='المستأجر',
        related='tenancy_id.partner_id', store=True, readonly=True,
    )
    owner_partner_id = fields.Many2one(
        'res.partner', string='المالك',
        related='property_id.owner_partner_id', store=True, readonly=True,
    )

    # ─── Inspection details ───────────────────────────────────────
    inspection_type = fields.Selection([
        ('move_in',  'استلام (بداية العقد)'),
        ('move_out', 'تسليم (نهاية العقد)'),
        ('interim',  'معاينة دورية'),
    ], string='نوع المعاينة', required=True,
       default='move_in', tracking=True)

    inspection_date = fields.Date(
        string='تاريخ المعاينة', required=True,
        default=fields.Date.context_today, tracking=True,
    )
    inspector_id = fields.Many2one(
        'res.users', string='القائم بالمعاينة',
        default=lambda s: s.env.user, tracking=True,
    )

    # ─── Condition ────────────────────────────────────────────────
    general_condition = fields.Selection([
        ('excellent', 'ممتاز'),
        ('good',      'جيد'),
        ('fair',      'مقبول'),
        ('poor',      'سيء'),
        ('damaged',   'متضرر'),
    ], string='الحالة العامة', default='good', tracking=True)
    general_notes = fields.Text(string='ملاحظات عامة')

    # ─── Lines ────────────────────────────────────────────────────
    line_ids = fields.One2many(
        'sa.property.inspection.line', 'inspection_id',
        string='بنود المعاينة', copy=True,
    )
    total_damages_cost = fields.Float(
        string='إجمالي تكلفة الأضرار (ريال)',
        compute='_compute_total_damages', store=True,
    )

    @api.depends('line_ids.damage_cost')
    def _compute_total_damages(self):
        for rec in self:
            rec.total_damages_cost = sum(rec.line_ids.mapped('damage_cost'))

    # ─── State ────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft',     'مسودة'),
        ('completed', 'مكتملة'),
        ('signed',    'موقَّعة'),
        ('cancelled', 'ملغاة'),
    ], string='الحالة', default='draft', required=True, tracking=True, copy=False)

    # ─── Sequencing ───────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('جديد')) == _('جديد'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'sa.property.inspection'
                ) or _('جديد')
        return super().create(vals_list)

    # ─── Onchange ─────────────────────────────────────────────────
    @api.onchange('tenancy_id')
    def _onchange_tenancy(self):
        if self.tenancy_id:
            self.property_id = self.tenancy_id.property_id

    # ─── Actions ──────────────────────────────────────────────────
    def action_complete(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_('يجب إضافة بند واحد على الأقل قبل الإكمال'))
            rec.state = 'completed'
        return True

    def action_sign(self):
        for rec in self:
            if rec.state != 'completed':
                raise UserError(_('يجب إكمال المعاينة قبل التوقيع'))
            rec.state = 'signed'
        return True

    def action_cancel(self):
        for rec in self:
            rec.state = 'cancelled'
        return True

    def action_set_to_draft(self):
        for rec in self:
            rec.state = 'draft'
        return True


class PropertyInspectionLine(models.Model):
    """بند معاينة — صف لكل عنصر/غرفة في تقرير المعاينة."""
    _name = 'sa.property.inspection.line'
    _description = 'بند معاينة'
    _order = 'sequence, id'

    sequence = fields.Integer(string='التسلسل', default=10)
    inspection_id = fields.Many2one(
        'sa.property.inspection', string='تقرير المعاينة',
        required=True, ondelete='cascade',
    )

    room = fields.Selection([
        ('living_room',  'الصالة / المعيشة'),
        ('bedroom',      'غرفة نوم'),
        ('master',       'غرفة نوم رئيسية'),
        ('kitchen',      'المطبخ'),
        ('bathroom',     'دورة مياه'),
        ('balcony',      'الشرفة / البلكونة'),
        ('storage',      'المستودع'),
        ('parking',      'الموقف'),
        ('exterior',     'الواجهة الخارجية'),
        ('common',       'المناطق المشتركة'),
        ('other',        'أخرى'),
    ], string='الموقع', required=True, default='living_room')
    room_other = fields.Char(string='مكان آخر')

    item = fields.Char(
        string='العنصر', required=True,
        help='مثال: حنفية الحوض، الباب الرئيسي، مفتاح الإضاءة...',
    )
    condition = fields.Selection([
        ('good',         'جيد'),
        ('minor_wear',   'تآكل بسيط'),
        ('damaged',      'متضرر'),
        ('missing',      'مفقود'),
        ('needs_repair', 'يحتاج إصلاح'),
        ('replaced',     'مُستبدل'),
    ], string='الحالة', required=True, default='good')

    damage_cost = fields.Float(
        string='تكلفة الإصلاح (ريال)',
        help='تُستخدم في احتساب الخصومات من الضمان',
    )
    notes = fields.Text(string='ملاحظات')
    image = fields.Binary(string='صورة', attachment=True)


class PropertyTenancyInspection(models.Model):
    """ربط عقد الإيجار بسجلات المعاينة (One2many + helpers)."""
    _inherit = 'property.tenancy'

    inspection_ids = fields.One2many(
        'sa.property.inspection', 'tenancy_id',
        string='تقارير المعاينة',
    )
    inspection_count = fields.Integer(
        string='عدد المعاينات',
        compute='_compute_inspection_count',
    )

    @api.depends('inspection_ids')
    def _compute_inspection_count(self):
        for rec in self:
            rec.inspection_count = len(rec.inspection_ids)

    def action_view_inspections(self):
        self.ensure_one()
        return {
            'name': _('معاينات العقد'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.property.inspection',
            'view_mode': 'tree,form',
            'domain': [('tenancy_id', '=', self.id)],
            'context': {
                'default_tenancy_id':  self.id,
                'default_property_id': self.property_id.id,
            },
        }

    def action_create_inspection(self):
        """فتح form معاينة جديدة مرتبطة بهذا العقد."""
        self.ensure_one()
        # Default type: move_in if no inspection yet, move_out if state == closed
        default_type = 'move_in'
        if self.inspection_ids:
            default_type = 'move_out' if self.state == 'closed' else 'interim'
        return {
            'name': _('معاينة جديدة'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.property.inspection',
            'view_mode': 'form',
            'context': {
                'default_tenancy_id':       self.id,
                'default_property_id':      self.property_id.id,
                'default_inspection_type':  default_type,
            },
        }
