# -*- coding: utf-8 -*-
import base64
from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


class UserProfilePortal(CustomerPortal):

    # ─── /my home: add profile card ──────────────────────────────

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id
        values['profile_completion'] = partner.profile_completion
        values['verification_state'] = partner.verification_state
        return values

    # ─── /my/profile GET ─────────────────────────────────────────

    @http.route('/my/profile', type='http', auth='user', website=True)
    def my_profile(self, **kw):
        partner = request.env.user.partner_id
        user = request.env.user

        regions = request.env['sa.region'].sudo().search([])
        doc_types = request.env['sa.user.document']._fields['doc_type'].selection
        id_types = request.env['sa.user.verification']._fields['id_type'].selection

        verifications = partner.verification_ids.sorted('id', reverse=True)
        documents = partner.document_ids.filtered(lambda d: d.state != 'archived')

        # Groups / roles for display
        pms_groups = [
            ('sa_security.group_pms_admin',         'مدير النظام'),
            ('sa_security.group_pms_manager',       'مدير العقارات'),
            ('sa_security.group_pms_accountant',    'محاسب العقارات'),
            ('sa_security.group_pms_agent',         'موظف خدمة العملاء'),
            ('sa_security.group_pms_owner',         'مالك عقار'),
            ('sa_security.group_pms_technician',    'فني صيانة'),
            ('sa_security.group_pms_tenant_portal', 'مستأجر (بوابة)'),
        ]
        user_roles = []
        for xml_id, label in pms_groups:
            grp = request.env.ref(xml_id, raise_if_not_found=False)
            if grp and grp.id in user.groups_id.ids:
                user_roles.append(label)

        # Recent login + messages
        audit_entries = request.env['mail.message'].sudo().search([
            ('author_id', '=', partner.id),
            ('message_type', 'in', ['comment', 'email']),
        ], limit=20, order='date desc')

        values = {
            'partner':           partner,
            'user':              user,
            'regions':           regions,
            'doc_types':         doc_types,
            'id_types':          id_types,
            'verifications':     verifications,
            'documents':         documents,
            'user_roles':        user_roles,
            'audit_entries':     audit_entries,
            'success':           kw.get('success'),
            'error':             kw.get('error'),
            'active_tab':        kw.get('tab', 'personal'),
            'page_name':         'profile',
        }
        return request.render('sa_user_profile.portal_my_profile', values)

    # ─── POST: personal info ──────────────────────────────────────

    @http.route('/my/profile/personal', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def update_personal(self, **post):
        partner = request.env.user.partner_id
        vals = {}
        for field in ('name', 'phone', 'email', 'gender', 'bio'):
            if field in post:
                vals[field] = post[field].strip() or False
        if 'date_of_birth' in post and post['date_of_birth']:
            vals['date_of_birth'] = post['date_of_birth']
        if vals:
            partner.sudo().write(vals)
        return request.redirect('/my/profile?tab=personal&success=1')

    # ─── POST: national address ───────────────────────────────────

    @http.route('/my/profile/address', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def update_address(self, **post):
        partner = request.env.user.partner_id
        vals = {}
        for field in ('city', 'sa_district', 'sa_building_no', 'sa_unit_no',
                      'sa_additional_no', 'sa_postal_code', 'sa_national_address'):
            if field in post:
                vals[field] = post[field].strip() or False
        if 'sa_region_id' in post and post['sa_region_id']:
            vals['sa_region_id'] = int(post['sa_region_id'])
        if vals:
            partner.sudo().write(vals)
        return request.redirect('/my/profile?tab=address&success=1')

    # ─── POST: submit verification ────────────────────────────────

    @http.route('/my/profile/verification', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def submit_verification(self, **post):
        partner = request.env.user.partner_id
        id_type = post.get('id_type')
        id_number = (post.get('id_number') or '').strip()
        id_expiry = post.get('id_expiry') or False
        scan_file = post.get('id_scan')

        if not id_type or not id_number:
            return request.redirect('/my/profile?tab=verification&error=missing_fields')

        scan_data = False
        scan_name = False
        if scan_file and hasattr(scan_file, 'read'):
            raw = scan_file.read()
            if raw:
                scan_data = base64.b64encode(raw)
                scan_name = scan_file.filename

        verif = request.env['sa.user.verification'].sudo().create({
            'partner_id':   partner.id,
            'id_type':      id_type,
            'id_number':    id_number,
            'id_expiry':    id_expiry or False,
            'id_scan':      scan_data,
            'id_scan_name': scan_name,
        })
        verif.action_submit()
        return request.redirect('/my/profile?tab=verification&success=1')

    # ─── POST: upload document ────────────────────────────────────

    @http.route('/my/profile/document/upload', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def upload_document(self, **post):
        partner = request.env.user.partner_id
        doc_file = post.get('doc_file')
        doc_name = (post.get('doc_name') or '').strip()
        doc_type = post.get('doc_type', 'other')
        expiry = post.get('expiry_date') or False

        if not doc_file or not hasattr(doc_file, 'read'):
            return request.redirect('/my/profile?tab=documents&error=no_file')

        raw = doc_file.read()
        if not raw:
            return request.redirect('/my/profile?tab=documents&error=empty_file')

        request.env['sa.user.document'].sudo().create({
            'partner_id':  partner.id,
            'doc_type':    doc_type,
            'name':        doc_name or doc_file.filename,
            'datas':       base64.b64encode(raw),
            'filename':    doc_file.filename,
            'expiry_date': expiry or False,
        })
        return request.redirect('/my/profile?tab=documents&success=1')

    # ─── POST: archive document ───────────────────────────────────

    @http.route('/my/profile/document/<int:doc_id>/archive', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def archive_document(self, doc_id, **post):
        partner = request.env.user.partner_id
        doc = request.env['sa.user.document'].sudo().search([
            ('id', '=', doc_id),
            ('partner_id', '=', partner.id),
        ], limit=1)
        if doc:
            doc.action_archive()
        return request.redirect('/my/profile?tab=documents&success=1')
