/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";

/**
 * Client action that embeds the /callcenter/analytics URL in an iframe inside
 * the Odoo webclient. Keeps the navbar + breadcrumbs visible so the
 * dashboard feels like a native Odoo page.
 */
export class CallCenterAnalyticsDashboardAction extends Component {
    static template = "sa_call_center_analytics.CallCenterAnalyticsDashboardAction";
}

registry.category("actions").add("call_center_analytics_dashboard_action", CallCenterAnalyticsDashboardAction);
