# -*- coding: utf-8 -*-
import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError

# Fixed, deterministic bigint used as the pg_advisory_xact_lock key to
# serialize load-based lead-rotation assignment across concurrent creates.
LEAD_ROTATION_LOCK_ID = 987654321


class SaCrmLead(models.Model):
    _name = 'sa.crm.lead'
    _description = 'طلب CRM'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'stage_id, priority desc, id desc'

    # ─── Identity ──────────────────────────────────────────────
    name = fields.Char(
        string='المرجع',
        readonly=True, copy=False,
        default=lambda s: _('جديد'),
    )
    active = fields.Boolean(default=True)

    # ─── Customer ──────────────────────────────────────────────
    partner_id = fields.Many2one(
        'res.partner', string='العميل',
        required=True, tracking=True,
    )
    phone = fields.Char(
        string='الهاتف',
        related='partner_id.phone', store=True,
    )
    email = fields.Char(
        string='البريد الإلكتروني',
        related='partner_id.email', store=True,
    )

    # ─── Lead / Opportunity / Deal ─────────────────────────────
    lead_category = fields.Selection([
        ('lead',        'طلب'),
        ('opportunity', 'فرصة'),
        ('deal',        'صفقة'),
    ], string='التصنيف', default='lead', tracking=True)

    # ─── Classification ────────────────────────────────────────
    lead_type = fields.Selection([
        ('rent', 'بحث عن إيجار'),
        ('buy',  'بحث عن شراء'),
    ], string='نوع الطلب', required=True, default='rent', tracking=True)

    property_type = fields.Selection([
        ('residential', 'سكني'),
        ('commercial',  'تجاري'),
        ('industrial',  'صناعي'),
        ('land',        'أرض'),
    ], string='نوع العقار', default='residential', tracking=True)

    # ─── Budget ────────────────────────────────────────────────
    budget_min = fields.Float(string='الميزانية الدنيا')
    budget_max = fields.Float(string='الميزانية القصوى')
    currency_id = fields.Many2one(
        'res.currency', string='العملة',
        default=lambda s: s.env.company.currency_id,
    )

    # ─── Location ──────────────────────────────────────────────
    preferred_region_id = fields.Many2one(
        'sa.region', string='المنطقة المفضلة',
    )

    # ─── Property Requirements ─────────────────────────────────
    rooms_min = fields.Integer(string='الغرف الدنيا')
    rooms_max = fields.Integer(string='الغرف القصوى')
    bathrooms_min = fields.Integer(string='دورات المياه (الحد الأدنى)')
    area_min_sqm = fields.Float(string='المساحة الدنيا م²')
    area_max_sqm = fields.Float(string='المساحة القصوى م²')
    furnished_pref = fields.Selection([
        ('any',        'أي نوع'),
        ('furnished',  'مفروش'),
        ('semi',       'نصف مفروش'),
        ('unfurnished', 'غير مفروش'),
    ], string='التأثيث', default='any')
    parking_required = fields.Boolean(string='يتطلب موقف سيارات')
    pool_required = fields.Boolean(string='يتطلب مسبح')
    garden_required = fields.Boolean(string='يتطلب حديقة')
    elevator_required = fields.Boolean(string='يتطلب مصعد')

    # ─── Pipeline ──────────────────────────────────────────────
    stage_id = fields.Many2one(
        'sa.crm.stage', string='المرحلة',
        required=True, ondelete='restrict', tracking=True,
        default=lambda s: s._default_stage_id(),
    )
    probability = fields.Float(
        string='الاحتمال',
        related='stage_id.probability', store=True,
    )
    kanban_state = fields.Selection([
        ('normal',  'في التقدم'),
        ('done',    'جاهز للمرحلة التالية'),
        ('blocked', 'محجوب'),
    ], string='حالة كانبان', default='normal')

    priority = fields.Selection([
        ('0', 'عادي'),
        ('1', 'مهم'),
        ('2', 'عاجل'),
    ], string='الأولوية', default='0')

    state = fields.Selection([
        ('open', 'مفتوح'),
        ('won',  'فاز'),
        ('lost', 'خسر'),
    ], string='الحالة', default='open', tracking=True, copy=False, index=True)

    lost_reason = fields.Char(string='سبب الخسارة')

    # ─── Assignment ────────────────────────────────────────────
    user_id = fields.Many2one(
        'res.users', string='الموظف المسؤول',
        tracking=True, index=True,
    )
    source = fields.Selection([
        ('walkin',   'زيارة مباشرة'),
        ('phone',    'اتصال هاتفي'),
        ('website',  'الموقع الإلكتروني'),
        ('referral', 'إحالة'),
        ('social',   'وسائل التواصل'),
        ('portal',   'البوابة'),
    ], string='المصدر', default='phone')

    # ─── Property ──────────────────────────────────────────────
    property_id = fields.Many2one(
        'property.property', string='العقار المقترح',
    )
    expected_commission = fields.Float(
        string='العمولة المتوقعة', tracking=True,
    )

    # ─── Dates & Notes ─────────────────────────────────────────
    date_open = fields.Date(
        string='تاريخ الفتح',
        default=fields.Date.today, copy=False, readonly=True,
    )
    date_deadline = fields.Date(string='الموعد النهائي')
    description = fields.Text(string='ملاحظات')

    # ─── Reservations ──────────────────────────────────────────
    reservation_ids = fields.One2many(
        'sa.crm.reservation', 'lead_id', string='الحجوزات',
    )
    reservation_count = fields.Integer(
        string='الحجوزات', compute='_compute_reservation_count',
    )
    active_reservation_id = fields.Many2one(
        'sa.crm.reservation', string='الحجز النشط',
        compute='_compute_active_reservation',
    )
    has_active_reservation = fields.Boolean(
        compute='_compute_active_reservation',
    )
    draft_reservation_id = fields.Many2one(
        'sa.crm.reservation', string='الحجز المعلّق',
        compute='_compute_active_reservation',
    )
    has_draft_reservation = fields.Boolean(
        compute='_compute_active_reservation',
    )

    # ─── Tenancy & Ejar Contract ───────────────────────────────
    tenancy_id = fields.Many2one(
        'property.tenancy', string='عقد الإيجار (تأجير)',
        copy=False, tracking=True,
    )
    contract_id = fields.Many2one(
        'ejar.contract', string='عقد إيجار (منصة)',
        copy=False, tracking=True,
    )

    # ─── Showings ──────────────────────────────────────────────
    showing_ids = fields.One2many(
        'sa.crm.showing', 'lead_id', string='الجولات الميدانية',
    )
    showing_count = fields.Integer(
        string='عدد الجولات', compute='_compute_showing_count',
    )

    # ─── Computed ──────────────────────────────────────────────
    days_open = fields.Integer(
        string='أيام منذ الفتح',
        compute='_compute_days_open',
    )
    matching_count = fields.Integer(
        string='عقارات مطابقة',
        compute='_compute_matching_count',
    )

    # ─── Helpers ───────────────────────────────────────────────
    @api.model
    def _default_stage_id(self):
        return self.env['sa.crm.stage'].search([], order='sequence asc', limit=1)

    @api.depends('reservation_ids')
    def _compute_reservation_count(self):
        for rec in self:
            rec.reservation_count = len(rec.reservation_ids)

    @api.depends('reservation_ids.state')
    def _compute_active_reservation(self):
        for rec in self:
            active = rec.reservation_ids.filtered(lambda r: r.state == 'active')
            draft = rec.reservation_ids.filtered(lambda r: r.state == 'draft')
            rec.active_reservation_id = active[:1]
            rec.has_active_reservation = bool(active)
            rec.draft_reservation_id = draft[:1]
            rec.has_draft_reservation = bool(draft)

    @api.depends('showing_ids')
    def _compute_showing_count(self):
        for rec in self:
            rec.showing_count = len(rec.showing_ids)

    @api.depends('date_open')
    def _compute_days_open(self):
        today = fields.Date.today()
        for rec in self:
            if rec.date_open:
                rec.days_open = (today - rec.date_open).days
            else:
                rec.days_open = 0

    @api.depends(
        'property_type', 'preferred_region_id', 'rooms_min', 'rooms_max',
        'bathrooms_min', 'area_min_sqm', 'area_max_sqm', 'budget_max',
        'lead_type', 'parking_required', 'pool_required',
        'garden_required', 'elevator_required', 'furnished_pref',
    )
    def _compute_matching_count(self):
        for rec in self:
            domain = rec._build_matching_domain()
            rec.matching_count = self.env['property.property'].search_count(domain)

    def _build_matching_domain(self):
        domain = [('state', '=', 'draft'), ('is_reserved', '=', False)]
        if self.property_type:
            domain.append(('property_type', '=', self.property_type))
        if self.preferred_region_id:
            domain.append(('sa_region_id', '=', self.preferred_region_id.id))
        if self.rooms_min:
            domain.append(('sa_rooms', '>=', self.rooms_min))
        if self.rooms_max:
            domain.append(('sa_rooms', '<=', self.rooms_max))
        if self.bathrooms_min:
            domain.append(('sa_bathrooms', '>=', self.bathrooms_min))
        if self.area_min_sqm:
            domain.append(('sa_area_sqm', '>=', self.area_min_sqm))
        if self.area_max_sqm:
            domain.append(('sa_area_sqm', '<=', self.area_max_sqm))
        if self.budget_max:
            if self.lead_type == 'rent':
                domain.append(('rent_amount', '<=', self.budget_max))
            elif self.lead_type == 'buy':
                domain.append(('price_amount', '<=', self.budget_max))
        if self.parking_required:
            domain.append(('sa_parking', '>', 0))
        if self.pool_required:
            domain.append(('sa_pool', '=', True))
        if self.garden_required:
            domain.append(('sa_garden', '=', True))
        if self.elevator_required:
            domain.append(('sa_elevator', '=', True))
        if self.furnished_pref and self.furnished_pref != 'any':
            domain.append(('sa_furnished', '=', self.furnished_pref))
        return domain

    # ─── Load-based rotation ───────────────────────────────────
    def _get_least_loaded_agent(self):
        self.env.cr.execute("SELECT pg_advisory_xact_lock(%s)", (LEAD_ROTATION_LOCK_ID,))
        manager_group = self.env.ref('sa_security.group_pms_manager', raise_if_not_found=False)
        agent_group = self.env.ref('sa_security.group_pms_agent', raise_if_not_found=False)
        if not agent_group:
            return self.env['res.users']
        domain = [
            ('sa_lead_rotation_eligible', '=', True),
            ('groups_id', 'in', [agent_group.id]),
            ('active', '=', True),
        ]
        if manager_group:
            domain.append(('groups_id', 'not in', [manager_group.id]))
        agents = self.env['res.users'].sudo().search(domain)
        if not agents:
            return self.env['res.users']
        self.env.cr.execute("""
            SELECT user_id, COUNT(*) FROM sa_crm_lead
            WHERE user_id = ANY(%s) AND state = 'open'
            GROUP BY user_id
        """, (agents.ids,))
        counts = dict(self.env.cr.fetchall())
        return min(agents, key=lambda a: counts.get(a.id, 0))

    def _cron_auto_assign_unassigned_leads(self):
        unassigned = self.search([('user_id', '=', False), ('state', '=', 'open')])
        for lead in unassigned:
            agent = lead._get_least_loaded_agent()
            if agent:
                lead.user_id = agent.id

    # ─── Sequencing ────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('جديد')) == _('جديد'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'sa.crm.lead'
                ) or _('جديد')
            if not vals.get('user_id'):
                agent = self._get_least_loaded_agent()
                if agent:
                    vals['user_id'] = agent.id
        return super().create(vals_list)

    # ─── Actions ───────────────────────────────────────────────
    def action_qualify_opportunity(self):
        second_stage = self.env['sa.crm.stage'].search([], order='sequence asc', offset=1, limit=1)
        for rec in self:
            rec.lead_category = 'opportunity'
            if rec.stage_id == self.env['sa.crm.stage'].search([], order='sequence asc', limit=1) and second_stage:
                rec.stage_id = second_stage

    def action_create_reservation(self):
        self.ensure_one()
        default_end = fields.Date.today() + datetime.timedelta(days=14)
        return {
            'name': _('حجز وحدة'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.crm.reservation',
            'view_mode': 'form',
            'context': {
                'default_lead_id': self.id,
                'default_property_id': self.property_id.id if self.property_id else False,
                'default_date_end': default_end.strftime('%Y-%m-%d'),
            },
            'target': 'new',
        }

    def action_confirm_reservation(self):
        self.ensure_one()
        draft = self.reservation_ids.filtered(lambda r: r.state == 'draft')[:1]
        if not draft:
            raise UserError(_('لا يوجد حجز معلّق لتأكيده.'))
        draft.action_activate()

    def action_convert_reservation_to_deal(self):
        self.ensure_one()
        active = self.reservation_ids.filtered(lambda r: r.state == 'active')[:1]
        if not active:
            raise UserError(_('يجب تأكيد الحجز أولاً قبل التحويل إلى صفقة.'))
        active.action_convert_to_deal()

    def action_view_reservations(self):
        self.ensure_one()
        return {
            'name': _('الحجوزات — %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'sa.crm.reservation',
            'view_mode': 'tree,form',
            'domain': [('lead_id', '=', self.id)],
            'context': {'default_lead_id': self.id},
        }

    def action_mark_won(self):
        won_stage = self.env['sa.crm.stage'].search(
            [('is_won', '=', True)], order='sequence asc', limit=1
        )
        for rec in self:
            rec.state = 'won'
            rec.lead_category = 'deal'
            if won_stage:
                rec.stage_id = won_stage

    def action_mark_lost(self):
        for rec in self:
            rec.state = 'lost'
            rec.active = False

    def action_reopen(self):
        for rec in self:
            rec.state = 'open'
            rec.active = True
            if rec.lead_category == 'deal':
                rec.lead_category = 'opportunity'

    def action_view_showings(self):
        self.ensure_one()
        return {
            'name': _('الجولات الميدانية'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.crm.showing',
            'view_mode': 'tree,calendar,form',
            'domain': [('lead_id', '=', self.id)],
            'context': {'default_lead_id': self.id},
        }

    def action_find_matching_properties(self):
        self.ensure_one()
        domain = self._build_matching_domain()
        return {
            'name': _('عقارات مطابقة — %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'property.property',
            'view_mode': 'tree,form',
            'domain': domain,
        }

    def action_create_ejar_contract(self):
        self.ensure_one()
        today = fields.Date.today()
        end_date = today + datetime.timedelta(days=365)

        property_rec = self.property_id
        if not property_rec:
            converted = self.reservation_ids.filtered(lambda r: r.state == 'converted')[:1]
            if converted:
                property_rec = converted.property_id

        rent_monthly = 0.0
        rent_annual = 0.0
        if property_rec:
            rent_monthly = property_rec.rent_amount or 0.0
            rent_annual = property_rec.sa_rent_annual or (rent_monthly * 12)
        if not rent_annual:
            rent_annual = self.budget_max or 0.0
        if not rent_monthly:
            rent_monthly = rent_annual / 12

        # 1. Create property.tenancy (draft)
        tenancy_vals = {
            'partner_id': self.partner_id.id,
            'start_date': today,
            'end_date': end_date,
            'rent_amount': rent_monthly,
            'payment_method': 'bank_transfer',
        }
        if self.partner_id.sa_national_id:
            tenancy_vals.update({
                'tenant_id_type': self.partner_id.sa_id_type or 'national_id',
                'tenant_national_id': self.partner_id.sa_national_id,
                'tenant_id_expiry': self.partner_id.sa_id_expiry,
            })
        if property_rec:
            tenancy_vals['property_id'] = property_rec.id
        tenancy = self.env['property.tenancy'].sudo().create(tenancy_vals)
        self.tenancy_id = tenancy

        # 2. Create ejar.contract linked to tenancy
        contract_type = 'residential' if self.property_type in ('residential', 'land') else 'commercial'
        id_type_mapping = {
            'national_id': 'national_id',
            'iqama': 'iqama',
            'passport': 'passport',
            'gcc': 'gcc_id',
        }
        party_vals = {
            'role': 'tenant',
            'entity_type': 'individual',
            'partner_id': self.partner_id.id,
            'full_name_ar': self.partner_id.name or '',
            'mobile': self.partner_id.mobile or self.partner_id.phone or '',
            'email': self.partner_id.email or '',
        }
        if self.partner_id.sa_national_id:
            party_vals.update({
                'id_number': self.partner_id.sa_national_id,
                'id_type': id_type_mapping.get(self.partner_id.sa_id_type, 'national_id'),
                'id_expiry': self.partner_id.sa_id_expiry,
            })
        contract_vals = {
            'tenancy_id': tenancy.id,
            'start_date': today,
            'end_date': end_date,
            'rent_amount': rent_annual,
            'contract_type': contract_type,
            'payment_schedule': 'monthly',
            'party_ids': [(0, 0, party_vals)],
        }
        if property_rec:
            _unit_type_map = {
                'residential': 'apartment',
                'commercial': 'office',
                'industrial': 'warehouse',
                'land': 'land',
            }
            unit_type = _unit_type_map.get(property_rec.ejar_unit_type or '', 'apartment')
            unit_vals = {
                'property_id': property_rec.id,
                'unit_number': property_rec.name,
                'unit_type': unit_type,
                'area': property_rec.sa_area_sqm or 0.0,
                'bedrooms': property_rec.sa_rooms or 0,
                'bathrooms': property_rec.sa_bathrooms or 0,
            }
            contract_vals['unit_ids'] = [(0, 0, unit_vals)]

        contract = self.env['ejar.contract'].create(contract_vals)
        tenancy.ejar_contract_id = contract
        self.contract_id = contract

        return {
            'name': _('عقد الإيجار — %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'ejar.contract',
            'view_mode': 'form',
            'res_id': contract.id,
        }

    def action_view_ejar_contract(self):
        self.ensure_one()
        return {
            'name': _('عقد الإيجار — %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'ejar.contract',
            'view_mode': 'form',
            'res_id': self.contract_id.id,
        }

    def action_view_tenancy(self):
        self.ensure_one()
        return {
            'name': _('عقد الإيجار (تأجير) — %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'property.tenancy',
            'view_mode': 'form',
            'res_id': self.tenancy_id.id,
        }
