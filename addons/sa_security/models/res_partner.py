# -*- coding: utf-8 -*-
"""ربط جهات الاتصال بمستخدمي النظام.

أزرار "إنشاء مستخدم" تكتشف نوع الجهة:
    * is_property_owner=True  → group_pms_owner (مستخدم داخلي)
    * is_tenant=True          → group_pms_tenant_portal (مستخدم بوابة)
    * is_technician=True      → group_pms_technician (مستخدم داخلي)

ترسل دعوة بريد للمستخدم الجديد ليضع كلمة مروره بنفسه.
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    has_pms_user = fields.Boolean(
        string='له حساب نظام', compute='_compute_has_pms_user',
    )
    pms_user_id = fields.Many2one(
        'res.users', string='حساب النظام',
        compute='_compute_has_pms_user',
    )
    pms_user_role = fields.Char(
        string='الدور', compute='_compute_has_pms_user',
    )

    @api.depends('user_ids', 'user_ids.groups_id')
    def _compute_has_pms_user(self):
        Group = self.env.ref
        try:
            g_owner = Group('sa_security.group_pms_owner').id
            g_tenant = Group('sa_security.group_pms_tenant_portal').id
            g_tech = Group('sa_security.group_pms_technician').id
        except Exception:
            g_owner = g_tenant = g_tech = False

        role_map = {
            g_owner:  _('مالك'),
            g_tenant: _('مستأجر (بوابة)'),
            g_tech:   _('فني صيانة'),
        }
        for rec in self:
            user = rec.user_ids[:1]
            rec.has_pms_user = bool(user)
            rec.pms_user_id = user.id if user else False
            if user:
                # Pick the most-specific PMS group for display
                role_label = ''
                for gid, lbl in role_map.items():
                    if gid and gid in user.groups_id.ids:
                        role_label = lbl
                        break
                rec.pms_user_role = role_label
            else:
                rec.pms_user_role = ''

    # ─── Action: create user ─────────────────────────────────────
    def _get_target_group(self):
        """يختار الـ group المناسب من علامات الجهة."""
        self.ensure_one()
        # Owner has priority over tenant if both flags set (rare)
        if self.is_property_owner:
            return self.env.ref('sa_security.group_pms_owner', raise_if_not_found=False)
        if self.is_technician:
            return self.env.ref('sa_security.group_pms_technician', raise_if_not_found=False)
        if self.is_tenant:
            return self.env.ref('sa_security.group_pms_tenant_portal', raise_if_not_found=False)
        return False

    def action_create_pms_user(self):
        self.ensure_one()
        if self.user_ids:
            raise UserError(_(
                'هذه الجهة لها مستخدم بالفعل: %s'
            ) % ', '.join(self.user_ids.mapped('login')))
        if not self.email:
            raise UserError(_(
                'يجب إدخال البريد الإلكتروني للجهة قبل إنشاء المستخدم.\n'
                'البريد سيُستخدم كاسم الدخول وللتواصل.'
            ))
        if not (self.is_property_owner or self.is_tenant
                or self.is_technician):
            raise UserError(_(
                'الجهة ليست مالكاً ولا مستأجراً ولا فنياً.\n'
                'فعِّل إحدى الخانات قبل إنشاء المستخدم.'
            ))

        group = self._get_target_group()
        if not group:
            raise UserError(_('لم يُعثر على الدور المناسب لهذه الجهة.'))

        # Check email uniqueness
        existing = self.env['res.users'].search([
            ('login', '=', self.email),
        ], limit=1)
        if existing:
            raise UserError(_(
                'يوجد مستخدم آخر بنفس البريد: %s.\n'
                'استخدم بريداً آخر أو اربط الجهة بالمستخدم الموجود.'
            ) % existing.name)

        user_vals = {
            'name':       self.name,
            'login':      self.email,
            'email':      self.email,
            'partner_id': self.id,
            'company_id': self.env.company.id,
            'company_ids': [(6, 0, [self.env.company.id])],
            'groups_id':  [(6, 0, [group.id])],
        }
        # If portal user, ensure we don't add internal-user implicit groups
        # (the group_pms_tenant_portal already implies group_portal).

        user = self.env['res.users'].with_context(
            no_reset_password=True,  # we'll handle invite ourselves
        ).create(user_vals)

        # Send invite email so user can set their own password
        try:
            user.action_reset_password()
            invite_msg = _('تم إرسال دعوة على البريد %s لإكمال التسجيل.') % self.email
        except Exception as e:
            invite_msg = _('تم إنشاء المستخدم. الرجاء إرسال دعوة يدوياً (فشل البريد: %s)') % str(e)[:100]

        self.message_post(
            body=_('<b>تم إنشاء حساب نظام:</b> %s (دور: %s)<br/>%s') % (
                user.login, group.name, invite_msg,
            ),
            message_type='notification', subtype_xmlid='mail.mt_note',
        )

        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('تم إنشاء المستخدم'),
                'message': invite_msg,
                'type':    'success',
                'sticky':  False,
            }
        }

    def action_open_pms_user(self):
        self.ensure_one()
        if not self.user_ids:
            raise UserError(_('لا يوجد مستخدم لهذه الجهة'))
        return {
            'name':      _('مستخدم النظام'),
            'type':      'ir.actions.act_window',
            'res_model': 'res.users',
            'view_mode': 'form',
            'res_id':    self.user_ids[0].id,
        }

    def action_resend_pms_invite(self):
        self.ensure_one()
        if not self.user_ids:
            raise UserError(_('لا يوجد مستخدم لإرسال دعوة'))
        try:
            self.user_ids[0].action_reset_password()
        except Exception as e:
            raise UserError(_('فشل إرسال الدعوة: %s') % str(e)[:200])
        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('تم إرسال الدعوة'),
                'message': _('تم إعادة إرسال دعوة كلمة المرور إلى %s') % self.email,
                'type':    'success',
            }
        }
