# -*- coding: utf-8 -*-
"""تقرير أساسي لمركز الاتصال — حجم المكالمات، الانتظار، المدة، الفائتة، لوحة الوكلاء."""
import json
from datetime import date, timedelta

from odoo import http
from odoo.http import request


class CallCenterDashboardController(http.Controller):

    @http.route('/callcenter/dashboard', type='http', auth='user', website=False)
    def dashboard(self, **kwargs):
        env = request.env
        Call = env['sa.call.center.call']
        today = date.today()
        week_ago = today - timedelta(days=7)

        recent = Call.search([('start_datetime', '>=', week_ago)])
        answered = recent.filtered(lambda c: c.state in ('answered', 'ended'))
        missed = recent.filtered(lambda c: c.state == 'missed')

        kpis = {
            'total_calls': len(recent),
            'answered_calls': len(answered),
            'missed_calls': len(missed),
            'missed_rate': round(len(missed) / len(recent) * 100, 1) if recent else 0,
            'avg_wait': round(sum(recent.mapped('wait_duration')) / len(recent), 1) if recent else 0,
            'avg_talk': round(sum(answered.mapped('talk_duration')) / len(answered), 1) if answered else 0,
        }

        # ─── Calls per day (last 7 days) ──────────────────────
        days_data = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            day_calls = recent.filtered(
                lambda c, d=day: c.start_datetime and c.start_datetime.date() == d
            )
            days_data.append({'day': day.strftime('%Y-%m-%d'), 'count': len(day_calls)})

        # ─── Calls by state (donut) ───────────────────────────
        by_state = {}
        state_labels = dict(Call._fields['state'].selection)
        for rec in recent:
            label = state_labels.get(rec.state, rec.state)
            by_state[label] = by_state.get(label, 0) + 1

        # ─── Agent leaderboard (calls handled, last 7 days) ───
        agent_counts = {}
        for rec in answered:
            agent = rec.agent_id.name or 'غير معروف'
            agent_counts[agent] = agent_counts.get(agent, 0) + 1
        top_agents = sorted(agent_counts.items(), key=lambda x: -x[1])[:5]

        return request.render('sa_call_center.dashboard_view', {
            'kpis': kpis,
            'days_json': json.dumps(days_data),
            'by_state_json': json.dumps(by_state),
            'top_agents': top_agents,
            'today': today,
        })
