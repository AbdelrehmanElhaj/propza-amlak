# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


class TenantPortal(CustomerPortal):
    """بوابة المستأجر — تعتمد على record rules من sa_security لتقييد الرؤية."""

    # ─── Add counters to portal home ─────────────────────────────
    def _prepare_home_portal_values(self, counters):
        return super()._prepare_home_portal_values(counters)

    # ═══════════════════════════════════════════════════════════
    #  /my/contracts — Tenancies (lease contracts)
    # ═══════════════════════════════════════════════════════════
    @http.route(['/my/contracts', '/my/contracts/<int:tenancy_id>'],
                type='http', auth='user', website=True)
    def portal_my_contracts(self, tenancy_id=None, **kw):
        partner = request.env.user.partner_id
        Tenancy = request.env['property.tenancy']

        if tenancy_id:
            tenancy = Tenancy.browse(tenancy_id).exists()
            if not tenancy or tenancy.partner_id.id != partner.id:
                return request.redirect('/my/contracts')
            return request.render(
                'sa_portal.portal_my_contract_detail',
                {'tenancy': tenancy, 'page_name': 'contract'},
            )

        tenancies = Tenancy.search(
            [('partner_id', '=', partner.id)],
            order='start_date desc',
        )
        return request.render(
            'sa_portal.portal_my_contracts',
            {'tenancies': tenancies, 'page_name': 'contracts'},
        )

    # ═══════════════════════════════════════════════════════════
    #  /my/payments — Rent payments
    # ═══════════════════════════════════════════════════════════
    @http.route(['/my/payments'], type='http', auth='user', website=True)
    def portal_my_payments(self, **kw):
        partner = request.env.user.partner_id
        Payment = request.env['sa.rent.payment']
        payments = Payment.search(
            [('tenancy_id.partner_id', '=', partner.id)],
            order='due_date desc',
        )
        # Stats for header
        total_due = sum(payments.mapped('amount'))
        total_paid = sum(payments.mapped('amount_paid'))
        total_balance = total_due - total_paid
        overdue_count = len(payments.filtered(lambda p: p.state == 'overdue'))

        return request.render(
            'sa_portal.portal_my_payments',
            {
                'payments': payments,
                'total_due': total_due,
                'total_paid': total_paid,
                'total_balance': total_balance,
                'overdue_count': overdue_count,
                'page_name': 'payments',
            },
        )

    # ═══════════════════════════════════════════════════════════
    #  /my/maintenance — Maintenance requests + new request form
    # ═══════════════════════════════════════════════════════════
    @http.route(['/my/maintenance'], type='http', auth='user', website=True)
    def portal_my_maintenance(self, **kw):
        partner = request.env.user.partner_id
        Request_ = request.env['sa.maintenance.request']
        requests_ = Request_.search(
            [('partner_id', '=', partner.id)],
            order='request_date desc',
        )
        # Get tenant's active tenancy (for default property)
        tenancy = request.env['property.tenancy'].search(
            [('partner_id', '=', partner.id), ('state', '=', 'running')],
            limit=1,
        )
        return request.render(
            'sa_portal.portal_my_maintenance',
            {
                'requests': requests_,
                'tenancy': tenancy,
                'page_name': 'maintenance',
                'categories': dict(Request_._fields['category'].selection),
                'priorities': dict(Request_._fields['priority'].selection),
            },
        )

    @http.route(['/my/maintenance/new'], type='http', auth='user',
                website=True, methods=['POST'], csrf=True)
    def portal_my_maintenance_create(self, **post):
        partner = request.env.user.partner_id
        tenancy = request.env['property.tenancy'].search(
            [('partner_id', '=', partner.id), ('state', '=', 'running')],
            limit=1,
        )
        if not tenancy:
            return request.redirect('/my/maintenance?error=no_tenancy')

        category = post.get('category') or 'other'
        priority = post.get('priority') or '1'
        description = post.get('description', '').strip()
        if not description:
            return request.redirect('/my/maintenance?error=no_description')

        from odoo import fields as odoo_fields
        new_req = request.env['sa.maintenance.request'].sudo().create({
            'property_id':  tenancy.property_id.id,
            'tenancy_id':   tenancy.id,
            'partner_id':   partner.id,
            'category':     category,
            'priority':     priority,
            'description':  description,
            'state':        'new',
            'cost_bearer':  'owner',  # default; manager will adjust
            'request_date': odoo_fields.Date.context_today(request.env.user),
        })
        # Notification to managers (via mail_thread)
        try:
            new_req.message_post(
                body=_('طلب صيانة جديد من المستأجر %s عبر البوابة') % partner.name,
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )
        except Exception:
            pass

        return request.redirect('/my/maintenance/%s?success=1' % new_req.id)

    @http.route(['/my/maintenance/<int:request_id>'],
                type='http', auth='user', website=True)
    def portal_my_maintenance_detail(self, request_id, **kw):
        partner = request.env.user.partner_id
        Request_ = request.env['sa.maintenance.request']
        rec = Request_.browse(request_id).exists()
        if not rec or rec.partner_id.id != partner.id:
            return request.redirect('/my/maintenance')
        return request.render(
            'sa_portal.portal_my_maintenance_detail',
            {'request': rec, 'page_name': 'maintenance'},
        )

    # ═══════════════════════════════════════════════════════════
    #  /my/inspections — Inspection reports
    # ═══════════════════════════════════════════════════════════
    @http.route(['/my/inspections'], type='http', auth='user', website=True)
    def portal_my_inspections(self, **kw):
        partner = request.env.user.partner_id
        Inspection = request.env['sa.property.inspection']
        inspections = Inspection.search(
            [('tenant_partner_id', '=', partner.id)],
            order='inspection_date desc',
        )
        return request.render(
            'sa_portal.portal_my_inspections',
            {'inspections': inspections, 'page_name': 'inspections'},
        )

    @http.route(['/my/inspections/<int:inspection_id>'],
                type='http', auth='user', website=True)
    def portal_my_inspection_detail(self, inspection_id, **kw):
        partner = request.env.user.partner_id
        rec = request.env['sa.property.inspection'].browse(inspection_id).exists()
        if not rec or rec.tenant_partner_id.id != partner.id:
            return request.redirect('/my/inspections')
        return request.render(
            'sa_portal.portal_my_inspection_detail',
            {'inspection': rec, 'page_name': 'inspections'},
        )
