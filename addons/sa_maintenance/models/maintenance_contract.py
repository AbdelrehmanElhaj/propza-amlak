# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta


class SaMaintenanceContract(models.Model):
    """عقد صيانة دورية (preventive maintenance).

    مثال: عقد سنوي لصيانة التكييف لكل عقارات المحفظة، أو عقد ربع سنوي
    لمكافحة الحشرات. يولّد cron طلب صيانة جديد عند حلول next_service_date.
    """
    _name = 'sa.maintenance.contract'
    _description = 'عقد صيانة دورية'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'next_service_date asc, id desc'

    name = fields.Char(
        string='اسم العقد', required=True, tracking=True,
        default=lambda s: _('جديد'),
    )
    supplier_partner_id = fields.Many2one(
        'res.partner', string='المقاول',
        domain="[('is_technician','=',True)]",
        required=True, tracking=True,
    )
    property_ids = fields.Many2many(
        'property.property',
        'maintenance_contract_property_rel',
        'contract_id', 'property_id',
        string='العقارات المُغطّاة', required=True,
    )
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

    # ─── الجدولة ───────────────────────────────────────────────
    frequency = fields.Selection([
        ('monthly',     'شهري'),
        ('quarterly',   'ربع سنوي'),
        ('semi_annual', 'نصف سنوي'),
        ('annual',      'سنوي'),
    ], string='التكرار', required=True, default='annual', tracking=True)

    start_date = fields.Date(
        string='تاريخ البداية', required=True,
        default=fields.Date.context_today, tracking=True,
    )
    end_date = fields.Date(string='تاريخ النهاية', tracking=True)
    last_service_date = fields.Date(string='آخر صيانة', readonly=True, tracking=True)
    next_service_date = fields.Date(
        string='الصيانة القادمة',
        compute='_compute_next_service_date', store=True, tracking=True,
    )

    # ─── المحتوى ───────────────────────────────────────────────
    service_description = fields.Text(
        string='وصف الخدمة',
        help='يُستخدم كقالب لأوامر العمل المُولَّدة',
    )
    estimated_cost_per_visit = fields.Float(
        string='التكلفة المتوقعة لكل زيارة (ريال)', tracking=True,
    )

    # ─── الحالة ────────────────────────────────────────────────
    active = fields.Boolean(default=True)
    state = fields.Selection([
        ('draft',     'مسودة'),
        ('active',    'نشط'),
        ('suspended', 'موقوف'),
        ('expired',   'منتهي'),
    ], string='الحالة', default='draft', required=True, tracking=True, copy=False)

    # ─── الطلبات المولّدة ──────────────────────────────────────
    request_ids = fields.One2many(
        'sa.maintenance.request', 'contract_id',
        string='طلبات الصيانة المولّدة',
    )
    request_count = fields.Integer(
        string='عدد الطلبات', compute='_compute_request_count',
    )

    @api.depends('request_ids')
    def _compute_request_count(self):
        for r in self:
            r.request_count = len(r.request_ids)

    @api.depends('start_date', 'last_service_date', 'frequency')
    def _compute_next_service_date(self):
        offset = {
            'monthly':     relativedelta(months=1),
            'quarterly':   relativedelta(months=3),
            'semi_annual': relativedelta(months=6),
            'annual':      relativedelta(years=1),
        }
        for r in self:
            base = r.last_service_date or r.start_date
            if base and r.frequency:
                r.next_service_date = base + offset[r.frequency]
            else:
                r.next_service_date = False

    # ─── State transitions ────────────────────────────────────
    def action_activate(self):
        for r in self:
            if not r.property_ids:
                raise UserError(_('يجب تحديد عقار واحد على الأقل'))
            r.state = 'active'

    def action_suspend(self):
        for r in self:
            r.state = 'suspended'

    def action_expire(self):
        for r in self:
            r.state = 'expired'

    # ─── Auto-generation ──────────────────────────────────────
    def _generate_request(self):
        """ينشئ طلب صيانة جديد لكل عقار في العقد."""
        self.ensure_one()
        Request = self.env['sa.maintenance.request']
        created = Request
        desc = self.service_description or _('صيانة دورية وفق العقد %s') % self.name
        for prop in self.property_ids:
            req = Request.create({
                'description': desc,
                'property_id': prop.id,
                'category': self.category,
                'priority': '1',
                'state': 'approved',  # auto-approved since contracted
                'supplier_partner_id': self.supplier_partner_id.id,
                'request_date': fields.Date.context_today(self),
                'contract_id': self.id,
                'cost_bearer': 'owner',
                'notes': _('مولَّد تلقائياً من عقد الصيانة الدورية'),
            })
            created |= req
        self.last_service_date = fields.Date.context_today(self)
        self.message_post(
            body=_('تم توليد %d طلب صيانة من العقد') % len(created),
            message_type='notification',
        )
        return created

    def action_generate_request_now(self):
        """Public wrapper — يُستدعى من زرّ الواجهة لتوليد طلب فوراً."""
        created_total = self.env['sa.maintenance.request']
        for r in self:
            if r.state != 'active':
                raise UserError(_('لا يمكن توليد طلب من عقد غير نشط'))
            created_total |= r._generate_request()
        if not created_total:
            return False
        return {
            'name': _('طلبات الصيانة المُولّدة'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.maintenance.request',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', created_total.ids)],
        }

    @api.model
    def cron_generate_due_services(self):
        """يُستدعى يومياً — يولّد طلبات للعقود التي حلّ موعد صيانتها."""
        today = fields.Date.context_today(self)
        due = self.search([
            ('state', '=', 'active'),
            ('next_service_date', '<=', today),
            '|',
            ('end_date', '=', False),
            ('end_date', '>=', today),
        ])
        for c in due:
            try:
                c._generate_request()
            except Exception:
                pass
        return len(due)

    def action_view_requests(self):
        self.ensure_one()
        return {
            'name': _('طلبات الصيانة المُولّدة'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.maintenance.request',
            'view_mode': 'tree,form',
            'domain': [('contract_id', '=', self.id)],
            'context': {'default_contract_id': self.id},
        }
