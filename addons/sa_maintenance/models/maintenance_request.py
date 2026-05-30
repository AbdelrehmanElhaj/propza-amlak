# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaMaintenanceRequest(models.Model):
    """طلب صيانة عقار.

    تطوير من `sa_rental_cycle` — تم نقل النموذج لموديول `sa_maintenance`
    لتنظيمه كنظام مستقل.
    """
    _name = 'sa.maintenance.request'
    _description = 'طلب صيانة'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority desc, request_date desc, id desc'

    # ─── الهوية ────────────────────────────────────────────────
    name = fields.Char(
        string='رقم الطلب', readonly=True, copy=False,
        default=lambda s: _('جديد'),
    )
    description = fields.Text(string='وصف المشكلة', required=True, tracking=True)
    request_date = fields.Date(
        string='تاريخ الطلب', required=True,
        default=fields.Date.context_today, tracking=True,
    )

    # ─── الربط ─────────────────────────────────────────────────
    property_id = fields.Many2one(
        'property.property', string='العقار',
        required=True, tracking=True,
    )
    tenancy_id = fields.Many2one(
        'property.tenancy', string='عقد الإيجار',
        domain="[('property_id','=',property_id)]",
        tracking=True,
    )
    partner_id = fields.Many2one(
        'res.partner', string='المستأجر',
        related='tenancy_id.partner_id', store=True, readonly=True,
    )
    owner_partner_id = fields.Many2one(
        'res.partner', string='المالك',
        related='property_id.owner_partner_id', store=True, readonly=True,
    )

    # ─── التصنيف ────────────────────────────────────────────────
    category = fields.Selection([
        ('plumbing',   'سباكة'),
        ('electrical', 'كهرباء'),
        ('ac',         'تكييف'),
        ('painting',   'دهان'),
        ('carpentry',  'نجارة'),
        ('cleaning',   'تنظيف'),
        ('pest',       'مكافحة حشرات'),
        ('appliance',  'أجهزة منزلية'),
        ('other',      'أخرى'),
    ], string='الفئة', required=True, tracking=True)

    skill_ids = fields.Many2many(
        'sa.maintenance.skill',
        'request_skill_rel', 'request_id', 'skill_id',
        string='التخصصات المطلوبة'
    )

    priority = fields.Selection([
        ('0', 'منخفضة'),
        ('1', 'عادية'),
        ('2', 'مرتفعة'),
        ('3', 'عاجلة'),
    ], string='الأولوية', default='1', tracking=True)

    # ─── الحالة ────────────────────────────────────────────────
    state = fields.Selection([
        ('new',         'جديد'),
        ('approved',    'معتمد'),
        ('scheduled',   'مجدول'),
        ('in_progress', 'قيد التنفيذ'),
        ('done',        'منجز'),
        ('cancelled',   'ملغي'),
    ], string='الحالة', default='new', required=True, tracking=True, copy=False)

    # ─── المقاول/الفني ─────────────────────────────────────────
    supplier_partner_id = fields.Many2one(
        'res.partner', string='المقاول/الفني',
        domain="[('is_technician','=',True)]",
        tracking=True,
    )

    # ─── الجدولة ───────────────────────────────────────────────
    scheduled_date = fields.Datetime(string='موعد الزيارة المجدول', tracking=True)
    completion_date = fields.Date(string='تاريخ الإنجاز', tracking=True)
    estimated_duration = fields.Float(string='المدة التقديرية (ساعات)')
    actual_duration = fields.Float(string='المدة الفعلية (ساعات)')

    # ─── التكاليف التفصيلية ─────────────────────────────────────
    materials_cost = fields.Float(string='تكلفة المواد (ريال)', tracking=True)
    labor_cost = fields.Float(string='تكلفة العمالة (ريال)', tracking=True)
    transport_cost = fields.Float(string='تكلفة المواصلات (ريال)', tracking=True)
    cost = fields.Float(
        string='إجمالي التكلفة (ريال)',
        compute='_compute_cost', store=True, tracking=True,
    )
    cost_bearer = fields.Selection([
        ('owner',  'المالك'),
        ('tenant', 'المستأجر'),
        ('split',  'مشترك'),
    ], string='المتحمل للتكلفة', default='owner', tracking=True)

    @api.depends('materials_cost', 'labor_cost', 'transport_cost')
    def _compute_cost(self):
        for r in self:
            r.cost = (r.materials_cost or 0) + (r.labor_cost or 0) + (r.transport_cost or 0)

    # ─── الاعتماد ──────────────────────────────────────────────
    approved_by = fields.Many2one(
        'res.users', string='اعتمد بواسطة', readonly=True, copy=False,
    )
    approval_date = fields.Datetime(
        string='تاريخ الاعتماد', readonly=True, copy=False,
    )

    # ─── ربط مع عقد الصيانة الدورية ─────────────────────────────
    contract_id = fields.Many2one(
        'sa.maintenance.contract',
        string='عقد الصيانة الدورية',
        help='يُملأ تلقائياً عند توليد الطلب من عقد دوري',
    )

    # ─── أوامر العمل ───────────────────────────────────────────
    work_order_ids = fields.One2many(
        'sa.maintenance.work_order', 'request_id',
        string='أوامر العمل',
    )
    work_order_count = fields.Integer(
        string='عدد أوامر العمل',
        compute='_compute_work_order_count',
    )

    @api.depends('work_order_ids')
    def _compute_work_order_count(self):
        for r in self:
            r.work_order_count = len(r.work_order_ids)

    def action_create_work_order(self):
        self.ensure_one()
        return {
            'name': _('أمر عمل جديد'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.maintenance.work_order',
            'view_mode': 'form',
            'context': {
                'default_request_id': self.id,
                'default_technician_id': self.supplier_partner_id.id or False,
            },
        }

    def action_view_work_orders(self):
        self.ensure_one()
        return {
            'name': _('أوامر العمل'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.maintenance.work_order',
            'view_mode': 'tree,form',
            'domain': [('request_id', '=', self.id)],
            'context': {'default_request_id': self.id},
        }

    # ─── الملاحظات ─────────────────────────────────────────────
    notes = fields.Text(string='ملاحظات إضافية')

    # ─── Sequencing ────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('جديد')) == _('جديد'):
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code(
                    'sa.maintenance.request') or _('جديد')
        return super().create(vals_list)

    # ─── State transitions ────────────────────────────────────
    def action_approve(self):
        for r in self:
            r.write({
                'state': 'approved',
                'approved_by': self.env.user.id,
                'approval_date': fields.Datetime.now(),
            })

    def action_schedule(self):
        for r in self:
            if not r.scheduled_date:
                raise UserError(_('يجب تحديد موعد الزيارة قبل الجدولة.'))
            if not r.supplier_partner_id:
                raise UserError(_('يجب تعيين مقاول/فني قبل الجدولة.'))
            r.state = 'scheduled'

    def action_start(self):
        for r in self:
            r.state = 'in_progress'

    def action_done(self):
        for r in self:
            r.write({
                'state': 'done',
                'completion_date': fields.Date.context_today(self),
            })

    def action_cancel(self):
        for r in self:
            r.state = 'cancelled'

    def action_set_to_new(self):
        for r in self:
            r.state = 'new'
