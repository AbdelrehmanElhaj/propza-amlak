# -*- coding: utf-8 -*-
"""Dashboard controller — يجمع كل الـ KPIs والـ charts data."""
import json
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from odoo import http
from odoo.http import request


class PmsDashboardController(http.Controller):

    @http.route('/pms/dashboard', type='http', auth='user', website=False)
    def dashboard(self, **kwargs):
        """يعرض لوحة التحكم التفاعلية. record rules تطبق طبيعياً."""
        env = request.env
        today = date.today()
        month_start = today.replace(day=1)

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
            m_start = (today.replace(day=1) - relativedelta(months=i))
            m_end = m_start + relativedelta(months=1)
            month_payments = Payment.search([
                ('payment_type', '=', 'rent'),
                ('due_date', '>=', m_start),
                ('due_date', '<', m_end),
            ])
            months_data.append({
                'month': m_start.strftime('%Y-%m'),
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

        # ═══════════════════════════════════════════════════
        # CRM KPIs
        # ═══════════════════════════════════════════════════
        Lead = env['sa.crm.lead']

        open_leads = Lead.search([('state', '=', 'open')])
        won_this_month = Lead.search([
            ('state', '=', 'won'),
            ('date_open', '>=', month_start),
        ])
        lost_this_month = Lead.search([
            ('state', '=', 'lost'),
            ('date_open', '>=', month_start),
        ])
        total_closed_month = len(won_this_month) + len(lost_this_month)
        conversion_rate = (len(won_this_month) / total_closed_month * 100) if total_closed_month else 0

        # Average days-to-close for won leads in the last 30 days
        won_recent = Lead.search([
            ('state', '=', 'won'),
            ('date_open', '>=', today - timedelta(days=30)),
        ])
        if won_recent:
            avg_days_close = round(
                sum((today - r.date_open).days for r in won_recent if r.date_open)
                / len(won_recent)
            )
        else:
            avg_days_close = 0

        crm_kpis = {
            'open_leads': len(open_leads),
            'pipeline_value': sum(open_leads.mapped('budget_max')),
            'won_this_month': len(won_this_month),
            'conversion_rate': round(conversion_rate, 1),
            'avg_days_close': avg_days_close,
        }

        # ─── CRM Pipeline: leads count by stage ──────────────
        stages = env['sa.crm.stage'].search([], order='sequence asc')
        leads_by_stage = []
        for stage in stages:
            if stage.fold:
                continue
            count = Lead.search_count([
                ('stage_id', '=', stage.id),
                ('state', '=', 'open'),
            ])
            leads_by_stage.append({'stage': stage.name, 'count': count})

        # ─── Top 5 agents by deals won (all time) ────────────
        won_all = Lead.search([('state', '=', 'won')])
        agent_wins = {}
        for lead in won_all:
            agent = lead.user_id.name or 'غير معروف'
            agent_wins[agent] = agent_wins.get(agent, 0) + 1
        top_agents = sorted(agent_wins.items(), key=lambda x: -x[1])[:5]

        # ─── Reservations expiring within 7 days ─────────────
        expiring_res = env['sa.crm.reservation'].search([
            ('state', '=', 'active'),
            ('date_end', '<=', today + timedelta(days=7)),
            ('date_end', '>=', today),
        ], order='date_end asc')
        expiring_res_list = []
        for res in expiring_res:
            expiring_res_list.append({
                'name': res.name,
                'partner': res.partner_id.name or '',
                'property': res.property_id.name or '',
                'date_end': str(res.date_end),
                'days_left': (res.date_end - today).days,
            })

        # ═══════════════════════════════════════════════════
        # Team KPIs (targets / achievement / commission revenue)
        # ═══════════════════════════════════════════════════
        Target = env['sa.sales.target']
        CommissionLine = env['sa.broker.commission.line']

        active_targets = Target.search([
            ('date_from', '<=', today), ('date_to', '>=', today),
        ])
        agent_kpi_rows = [{
            'name': t.user_id.name or '',
            'target': t.target_amount,
            'achieved': t.achieved_amount,
            'pct': t.achievement_pct,
        } for t in active_targets.filtered(lambda t: t.scope == 'user').sorted(
            key=lambda t: -t.achievement_pct
        )]
        team_kpi_rows = [{
            'name': t.team_id.name or '',
            'target': t.target_amount,
            'achieved': t.achieved_amount,
            'pct': t.achievement_pct,
        } for t in active_targets.filtered(lambda t: t.scope == 'team').sorted(
            key=lambda t: -t.achievement_pct
        )]

        total_target = sum(active_targets.mapped('target_amount'))
        total_achieved = sum(active_targets.mapped('achieved_amount'))
        overall_pct = round(total_achieved / total_target * 100, 1) if total_target else 0.0

        month_paid_lines = CommissionLine.search([
            ('state', '=', 'paid'),
            ('due_date', '>=', month_start),
        ])
        team_kpis = {
            'total_target': total_target,
            'total_achieved': total_achieved,
            'overall_pct': overall_pct,
            'month_commission_revenue': sum(month_paid_lines.mapped('amount')),
            'agents_on_target': len([r for r in agent_kpi_rows if r['pct'] >= 100]),
            'agents_total': len(agent_kpi_rows),
        }

        return request.render('sa_dashboard.dashboard_view', {
            'kpis': kpis,
            'months_json': json.dumps(months_data),
            'occupancy_json': json.dumps(occupancy),
            'maint_by_cat_json': json.dumps(maint_by_cat),
            'top_overdue': top_overdue_list,
            'expiring_list': expiring_list,
            'today': today,
            # CRM
            'crm_kpis': crm_kpis,
            'leads_by_stage_json': json.dumps(leads_by_stage),
            'top_agents': top_agents,
            'expiring_res_list': expiring_res_list,
            # Team KPIs
            'team_kpis': team_kpis,
            'agent_kpi_rows': agent_kpi_rows,
            'team_kpi_rows': team_kpi_rows,
            'team_kpis_chart_json': json.dumps(agent_kpi_rows),
        })
