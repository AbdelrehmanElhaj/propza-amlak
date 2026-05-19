# -*- coding: utf-8 -*-
"""Dashboard controller — يجمع كل الـ KPIs والـ charts data."""
import json
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from odoo import http, _
from odoo.http import request


class PmsDashboardController(http.Controller):

    @http.route('/pms/dashboard', type='http', auth='user', website=False)
    def dashboard(self, **kwargs):
        """يعرض لوحة التحكم التفاعلية. record rules تطبق طبيعياً."""
        env = request.env
        today = date.today()

        # ─── KPI cards ────────────────────────────────────────
        Property = env['property.property']
        Tenancy = env['property.tenancy']
        Payment = env['sa.rent.payment']
        MaintReq = env['sa.maintenance.request']

        all_props = Property.search([])
        active_tenancies = Tenancy.search([('state', '=', 'running')])

        kpis = {
            'total_properties': len(all_props),
            'occupied': len(all_props.filtered(lambda p: p.state == 'on_rent')),
            'vacant': len(all_props.filtered(lambda p: p.state == 'draft')),
            'active_tenancies': len(active_tenancies),
            'monthly_revenue': sum(active_tenancies.mapped('rent_amount')),
            'overdue_count': Payment.search_count([
                ('state', '=', 'overdue'),
            ]),
            'overdue_amount': sum(Payment.search([
                ('state', '=', 'overdue'),
            ]).mapped('balance')),
            'expiring_60d': Tenancy.search_count([
                ('state', '=', 'running'),
                ('end_date', '<=', today + timedelta(days=60)),
                ('end_date', '>=', today),
                ('renewed_to_id', '=', False),
            ]),
        }

        # ─── Revenue trend (last 12 months) ──────────────────
        months_data = []
        for i in range(11, -1, -1):
            month_start = (today.replace(day=1) - relativedelta(months=i))
            next_month = month_start + relativedelta(months=1)
            month_payments = Payment.search([
                ('payment_type', '=', 'rent'),
                ('due_date', '>=', month_start),
                ('due_date', '<', next_month),
            ])
            label = month_start.strftime('%Y-%m')
            months_data.append({
                'month': label,
                'due':   sum(month_payments.mapped('amount')),
                'paid':  sum(month_payments.mapped('amount_paid')),
            })

        # ─── Occupancy donut ─────────────────────────────────
        occupancy = {
            'on_rent': kpis['occupied'],
            'vacant':  kpis['vacant'],
            'other':   kpis['total_properties'] - kpis['occupied'] - kpis['vacant'],
        }

        # ─── Maintenance cost by category ────────────────────
        maint_by_cat = {}
        cat_labels = dict(MaintReq._fields['category'].selection)
        done_requests = MaintReq.search([
            ('state', '=', 'done'),
            ('completion_date', '>=', today - timedelta(days=365)),
        ])
        for req in done_requests:
            label = cat_labels.get(req.category, req.category or 'other')
            maint_by_cat[label] = maint_by_cat.get(label, 0) + (req.cost or 0)

        # ─── Top 5 overdue tenants ───────────────────────────
        overdue_payments = Payment.search([
            ('state', '=', 'overdue'),
        ], order='balance desc', limit=20)
        top_overdue = {}
        for p in overdue_payments:
            tn = p.tenant_id.name or 'غير معروف'
            top_overdue[tn] = top_overdue.get(tn, 0) + (p.balance or 0)
        top_overdue_list = sorted(
            top_overdue.items(), key=lambda x: -x[1]
        )[:5]

        # ─── Top 5 expiring contracts ────────────────────────
        expiring = Tenancy.search([
            ('state', '=', 'running'),
            ('end_date', '<=', today + timedelta(days=60)),
            ('end_date', '>=', today),
            ('renewed_to_id', '=', False),
        ], order='end_date asc', limit=5)
        expiring_list = []
        for t in expiring:
            days_left = (t.end_date - today).days if t.end_date else 0
            expiring_list.append({
                'name': t.name,
                'tenant': t.partner_id.name or '',
                'property': t.property_id.display_name or '',
                'end_date': str(t.end_date) if t.end_date else '',
                'days_left': days_left,
            })

        # Render
        return request.render('sa_dashboard.dashboard_view', {
            'kpis': kpis,
            'months_json': json.dumps(months_data),
            'occupancy_json': json.dumps(occupancy),
            'maint_by_cat_json': json.dumps(maint_by_cat),
            'top_overdue': top_overdue_list,
            'expiring_list': expiring_list,
            'today': today,
        })
