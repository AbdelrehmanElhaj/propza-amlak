# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class SaCallCenterCall(models.Model):
    _name = 'sa.call.center.call'
    _description = 'سجل مكالمة مركز الاتصال'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start_datetime desc, id desc'

    name = fields.Char(
        string='رقم المكالمة', readonly=True, copy=False,
        default=lambda s: _('جديد'),
    )
    call_uid = fields.Char(
        string='معرّف المزوّد', copy=False,
        help='معرّف المكالمة الفريد القادم من نظام PBX/الاتصالات',
    )

    direction = fields.Selection([
        ('in', 'واردة'),
        ('out', 'صادرة'),
    ], string='الاتجاه', required=True, default='in', tracking=True)

    from_number = fields.Char(string='رقم المتصل')
    to_number = fields.Char(string='الرقم المطلوب')

    partner_id = fields.Many2one('res.partner', string='العميل', tracking=True)
    agent_id = fields.Many2one(
        'res.users', string='الموظف', tracking=True,
        default=lambda s: s.env.user,
    )
    queue_id = fields.Many2one('sa.call.center.queue', string='قائمة الانتظار')

    state = fields.Selection([
        ('ringing', 'يرن'),
        ('answered', 'تم الرد'),
        ('missed', 'فائتة'),
        ('voicemail', 'بريد صوتي'),
        ('ended', 'منتهية'),
    ], string='الحالة', default='ringing', required=True, tracking=True, copy=False)

    start_datetime = fields.Datetime(string='بداية المكالمة', default=fields.Datetime.now)
    answer_datetime = fields.Datetime(string='وقت الرد')
    end_datetime = fields.Datetime(string='نهاية المكالمة')

    wait_duration = fields.Integer(
        string='مدة الانتظار (ثانية)', compute='_compute_durations', store=True,
    )
    talk_duration = fields.Integer(
        string='مدة المكالمة (ثانية)', compute='_compute_durations', store=True,
    )

    recording_url = fields.Char(string='رابط التسجيل')

    related_record_ref = fields.Reference(
        selection='_selection_related_model', string='مرتبط بـ',
    )
    ticket_id = fields.Many2one('sa.call.center.ticket', string='التذكرة', copy=False)

    notes = fields.Text(string='ملاحظات الموظف')

    @api.model
    def _selection_related_model(self):
        return [
            ('sa.crm.lead', 'طلب CRM'),
            ('sa.maintenance.request', 'طلب صيانة'),
            ('sa.rent.payment', 'دفعة إيجار'),
            ('property.tenancy', 'عقد إيجار'),
        ]

    @api.depends('start_datetime', 'answer_datetime', 'end_datetime')
    def _compute_durations(self):
        for rec in self:
            wait = 0
            talk = 0
            if rec.start_datetime and rec.answer_datetime:
                wait = int((rec.answer_datetime - rec.start_datetime).total_seconds())
            if rec.answer_datetime and rec.end_datetime:
                talk = int((rec.end_datetime - rec.answer_datetime).total_seconds())
            rec.wait_duration = max(wait, 0)
            rec.talk_duration = max(talk, 0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('جديد')) == _('جديد'):
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code(
                    'sa.call.center.call') or _('جديد')
            if vals.get('from_number') and not vals.get('partner_id'):
                partner = self.env['sa.telephony.gateway']._find_partner_by_phone(
                    vals['from_number']
                )
                if partner:
                    vals['partner_id'] = partner.id
        return super().create(vals_list)

    def action_create_ticket(self):
        self.ensure_one()
        if not self.ticket_id:
            ticket = self.env['sa.call.center.ticket'].create({
                'partner_id': self.partner_id.id,
                'call_id': self.id,
                'description': self.notes or '',
            })
            self.ticket_id = ticket
        return {
            'name': _('تذكرة المكالمة'),
            'type': 'ir.actions.act_window',
            'res_model': 'sa.call.center.ticket',
            'view_mode': 'form',
            'res_id': self.ticket_id.id,
        }

    def _cron_close_stale_ringing_calls(self, timeout_minutes=30):
        """يُغلق المكالمات العالقة في حالة 'ringing' بعد مهلة (بيانات فاسدة/webhook مفقود)."""
        threshold = fields.Datetime.subtract(fields.Datetime.now(), minutes=timeout_minutes)
        stale = self.search([
            ('state', '=', 'ringing'),
            ('start_datetime', '<=', threshold),
        ])
        stale.write({'state': 'missed', 'end_datetime': fields.Datetime.now()})
