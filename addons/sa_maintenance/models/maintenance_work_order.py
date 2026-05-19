# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaMaintenanceWorkOrder(models.Model):
    """أمر عمل صيانة.

    طلب الصيانة (sa.maintenance.request) قد يحتوي عدة أوامر عمل.
    مثال: طلب "تجديد المطبخ" → 3 أوامر عمل: سباكة + كهرباء + دهان.
    كل أمر عمل له فني، موعد، تكلفة مستقلة.
    """
    _name = 'sa.maintenance.work_order'
    _description = 'أمر عمل صيانة'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'scheduled_date desc, id desc'

    name = fields.Char(
        string='رقم أمر العمل', readonly=True, copy=False,
        default=lambda s: _('جديد'),
    )
    request_id = fields.Many2one(
        'sa.maintenance.request', string='طلب الصيانة',
        required=True, ondelete='cascade', tracking=True,
    )
    property_id = fields.Many2one(
        related='request_id.property_id', store=True, readonly=True,
        string='العقار',
    )

    technician_id = fields.Many2one(
        'res.partner', string='الفني',
        domain="[('is_technician','=',True)]", tracking=True,
    )

    description = fields.Text(string='وصف العمل')

    # ─── الجدولة ───────────────────────────────────────────────
    scheduled_date = fields.Datetime(string='موعد التنفيذ', tracking=True)
    actual_start = fields.Datetime(string='البداية الفعلية', readonly=True)
    actual_end = fields.Datetime(string='الانتهاء الفعلي', readonly=True)
    duration_planned = fields.Float(string='المدة المخططة (ساعات)')
    duration_actual = fields.Float(string='المدة الفعلية (ساعات)', readonly=True)

    # ─── التكلفة ───────────────────────────────────────────────
    materials_cost = fields.Float(string='تكلفة المواد', tracking=True)
    labor_cost = fields.Float(string='تكلفة العمالة', tracking=True)
    transport_cost = fields.Float(string='تكلفة المواصلات', tracking=True)
    total_cost = fields.Float(
        string='الإجمالي', compute='_compute_total', store=True,
    )

    @api.depends('materials_cost', 'labor_cost', 'transport_cost')
    def _compute_total(self):
        for r in self:
            r.total_cost = (r.materials_cost or 0) + (r.labor_cost or 0) + (r.transport_cost or 0)

    # ─── الحالة ────────────────────────────────────────────────
    state = fields.Selection([
        ('draft',       'مسودة'),
        ('scheduled',   'مجدول'),
        ('in_progress', 'قيد التنفيذ'),
        ('done',        'منجز'),
        ('cancelled',   'ملغي'),
    ], string='الحالة', default='draft', required=True, tracking=True, copy=False)

    notes = fields.Text(string='ملاحظات الفني')

    # ─── ربط محاسبي ────────────────────────────────────────────
    bill_id = fields.Many2one(
        'account.move', string='فاتورة المورد', readonly=True, copy=False,
        help='فاتورة المقاول الناتجة عن أمر العمل',
    )

    # ─── Sequence ──────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('جديد')) == _('جديد'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'sa.maintenance.work_order') or _('جديد')
        return super().create(vals_list)

    # ─── State transitions ────────────────────────────────────
    def action_schedule(self):
        for r in self:
            if not r.technician_id:
                raise UserError(_('يجب تعيين فني قبل الجدولة'))
            if not r.scheduled_date:
                raise UserError(_('يجب تحديد موعد التنفيذ'))
            r.state = 'scheduled'

    def action_start(self):
        for r in self:
            r.write({
                'state': 'in_progress',
                'actual_start': fields.Datetime.now(),
            })

    def action_done(self):
        for r in self:
            now = fields.Datetime.now()
            duration = 0.0
            if r.actual_start:
                delta = now - r.actual_start
                duration = round(delta.total_seconds() / 3600, 2)
            r.write({
                'state': 'done',
                'actual_end': now,
                'duration_actual': duration,
            })

    def action_cancel(self):
        for r in self:
            r.state = 'cancelled'

    def action_set_to_draft(self):
        for r in self:
            r.state = 'draft'
