# -*- coding: utf-8 -*-
"""لوحة تحليلات التواصل مع العملاء — عملاء فريدون، تكرار، إجمالي وقت التحدث."""
from datetime import date, timedelta

from odoo import http
from odoo.http import request


class CallCenterAnalyticsDashboardController(http.Controller):

    @http.route('/callcenter/analytics', type='http', auth='user', website=False)
    def analytics_dashboard(self, **kwargs):
        env = request.env
        Call = env['sa.call.center.call']

        today = date.today()
        default_from = today - timedelta(days=30)

        date_from = kwargs.get('date_from') or default_from.strftime('%Y-%m-%d')
        date_to = kwargs.get('date_to') or today.strftime('%Y-%m-%d')
        agent_id = kwargs.get('agent_id')
        agent_id = int(agent_id) if agent_id else False

        domain = [
            ('start_datetime', '>=', date_from + ' 00:00:00'),
            ('start_datetime', '<=', date_to + ' 23:59:59'),
        ]
        if agent_id:
            domain.append(('agent_id', '=', agent_id))

        stats = Call.get_communication_stats(domain)

        # ─── Per-agent breakdown (single read_group call) ─────
        contact_domain = domain + [('state', 'in', ('answered', 'ended'))]
        raw_groups = Call.read_group(
            contact_domain, ['talk_duration:sum'], ['agent_id', 'partner_id'], lazy=False,
        )
        per_agent = {}
        for g in raw_groups:
            agent = g['agent_id']
            if not agent:
                continue
            agent_key, agent_name = agent
            entry = per_agent.setdefault(agent_key, {
                'agent_name': agent_name,
                'unique_customers': 0,
                'total_calls': 0,
                'total_talk_duration': 0,
            })
            entry['total_calls'] += g['__count']
            entry['total_talk_duration'] += g['talk_duration']
            if g['partner_id']:
                entry['unique_customers'] += 1
        agent_breakdown = sorted(
            per_agent.values(), key=lambda a: -a['total_calls']
        )

        # قائمة الموظفين للفلتر: الموظفون الذين لديهم مكالمات مسجّلة (تجميع واحد)
        agent_options = Call.sudo().read_group([], [], ['agent_id'])
        agent_choices = [
            (g['agent_id'][0], g['agent_id'][1])
            for g in agent_options if g['agent_id']
        ]

        def format_hms(total_seconds):
            total_seconds = int(total_seconds or 0)
            h, rem = divmod(total_seconds, 3600)
            m, s = divmod(rem, 60)
            return '%02d:%02d:%02d' % (h, m, s)

        return request.render('sa_call_center_analytics.analytics_dashboard_view', {
            'stats': stats,
            'total_talk_duration_hms': format_hms(stats['total_talk_duration']),
            'agent_breakdown': agent_breakdown,
            'agent_choices': agent_choices,
            'date_from': date_from,
            'date_to': date_to,
            'agent_id': agent_id,
        })
