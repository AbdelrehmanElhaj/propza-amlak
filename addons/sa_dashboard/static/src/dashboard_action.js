/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";

/**
 * Client action that embeds the /pms/dashboard URL in an iframe inside
 * the Odoo webclient. Keeps the navbar + breadcrumbs visible so the
 * dashboard feels like a native Odoo page.
 */
export class PmsDashboardAction extends Component {
    static template = "sa_dashboard.PmsDashboardAction";
}

registry.category("actions").add("pms_dashboard_action", PmsDashboardAction);
