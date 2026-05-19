from odoo import models, fields, api, _
from datetime import date


class SaMaintenance(models.Model):
    """طلبات الصيانة للعقار السعودي"""
    _name = 'sa.maintenance.request'
    _description = 'طلب صيانة'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='رقم الطلب', readonly=True,
                       default=lambda self: _('جديد'))
    tenancy_id = fields.Many2one(
        'property.tenancy', string='عقد الإيجار', required=True
    )
    property_id = fields.Many2one(
        related='tenancy_id.property_id', string='العقار', store=True
    )
    tenant_id = fields.Many2one(
        related='tenancy_id.partner_id', string='المستأجر', store=True
    )

    category = fields.Selection([
        ('plumbing',    'سباكة'),
        ('electrical',  'كهرباء'),
        ('ac',          'تكييف'),
        ('painting',    'دهانات'),
        ('carpentry',   'نجارة'),
        ('cleaning',    'تنظيف'),
        ('pest',        'مكافحة حشرات'),
        ('other',       'أخرى'),
    ], string='نوع الصيانة', required=True)

    priority = fields.Selection([
        ('low',     'منخفضة'),
        ('normal',  'عادية'),
        ('high',    'عالية'),
        ('urgent',  'عاجلة'),
    ], string='الأولوية', default='normal')

    description = fields.Text(string='وصف المشكلة', required=True)
    request_date = fields.Date(string='تاريخ الطلب', default=fields.Date.today)
    scheduled_date = fields.Date(string='تاريخ الصيانة المقرر')
    completion_date = fields.Date(string='تاريخ الإنجاز')

    cost = fields.Float(string='تكلفة الصيانة (ريال)')
    cost_bearer = fields.Selection([
        ('owner',   'المالك'),
        ('tenant',  'المستأجر'),
    ], string='من يتحمل التكلفة', default='owner')

    state = fields.Selection([
        ('new',         'جديد'),
        ('scheduled',   'مجدول'),
        ('in_progress', 'جاري التنفيذ'),
        ('done',        'منجز'),
        ('cancelled',   'ملغي'),
    ], string='الحالة', default='new', tracking=True)

    notes = fields.Text(string='ملاحظات')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('جديد')) == _('جديد'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'sa.maintenance.request') or _('جديد')
        return super().create(vals_list)

    def action_schedule(self):
        self.state = 'scheduled'

    def action_start(self):
        self.state = 'in_progress'

    def action_done(self):
        self.write({'state': 'done', 'completion_date': date.today()})

    def action_cancel(self):
        self.state = 'cancelled'


class PropertyTenancyMaintenance(models.Model):
    _inherit = 'property.tenancy'

    sa_maintenance_ids = fields.One2many(
        'sa.maintenance.request', 'tenancy_id',
        string='طلبات الصيانة'
    )
    sa_maintenance_count = fields.Integer(
        compute='_compute_maintenance_count'
    )

    @api.depends('sa_maintenance_ids')
    def _compute_maintenance_count(self):
        for rec in self:
            rec.sa_maintenance_count = len(
                rec.sa_maintenance_ids.filtered(
                    lambda m: m.state != 'cancelled'
                )
            )

    def action_new_maintenance(self):
        return {
            'name': _('طلب صيانة جديد'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.maintenance.request',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_tenancy_id': self.id,
                'default_property_id': self.property_id.id,
            },
        }
