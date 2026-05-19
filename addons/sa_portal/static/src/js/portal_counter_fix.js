/** @odoo-module **/
/**
 * Patch PortalHomeCounters._updateCounters to guard against null elements.
 *
 * Odoo 17's portal JS queries [data-placeholder_count] elements, fetches
 * counts, then calls querySelector again to update each element. If any
 * counter key in the server response has no matching DOM element (e.g.
 * because the card was conditionally rendered by another module), the
 * querySelector returns null and textContent assignment throws TypeError.
 */
import { patch } from "@web/core/utils/patch";
import { PortalHomeCounters } from "@portal/js/portal";

patch(PortalHomeCounters.prototype, {
    async _updateCounters(elem) {
        const numberRpc = 3;
        const needed = Object.values(
            this.el.querySelectorAll("[data-placeholder_count]")
        ).map((el) => el.dataset["placeholder_count"]);

        if (!needed.length) return;

        const counterByRpc = Math.ceil(needed.length / numberRpc);
        const countersAlwaysDisplayed = this._getCountersAlwaysDisplayed();

        const proms = [
            ...Array(Math.min(numberRpc, needed.length)).keys(),
        ].map(async (i) => {
            const data = await this.rpc("/my/counters", {
                counters: needed.slice(i * counterByRpc, (i + 1) * counterByRpc),
            });
            Object.keys(data).forEach((counterName) => {
                const el = this.el.querySelector(
                    `[data-placeholder_count='${counterName}']`
                );
                if (!el) return; // guard against missing DOM elements
                el.textContent = data[counterName];
                if (
                    data[counterName] !== 0 ||
                    countersAlwaysDisplayed.includes(counterName)
                ) {
                    el.closest(".o_portal_index_card").classList.remove("d-none");
                }
            });
            return data;
        });

        return Promise.all(proms).then(() => {
            const spinner = this.el.querySelector(".o_portal_doc_spinner");
            if (spinner) spinner.remove();
        });
    },
});
