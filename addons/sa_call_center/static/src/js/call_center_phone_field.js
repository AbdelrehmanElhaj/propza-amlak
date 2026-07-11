/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { PhoneField } from "@web/views/fields/phone/phone_field";
import { softphoneState } from "./softphone_state";

/**
 * حقل هاتف يُفعّل الاتصال المباشر عبر سمّاعة مركز الاتصال (يُطلق حدث
 * `CALL_CENTER:DIAL` على env.bus بدل فتح رابط tel:) — لكن فقط حين تكون
 * السمّاعة فعلاً جاهزة (`softphoneState.ready`)، وإلا يُترك سلوك tel:
 * الطبيعي كما هو لأي مستخدم ليس موظف مركز اتصال. حقل مستقل بـ widget
 * صريح (`sa_call_center_phone`) لا يُستبدل به حقل الهاتف الافتراضي في كل
 * الواجهات، بل يُفعَّل فقط أينما أُضيف صراحة (ملف العميل، طلب CRM...).
 */
export class CallCenterPhoneField extends PhoneField {
    static template = "sa_call_center.CallCenterPhoneField";

    onClickCall(ev) {
        const phoneNumber = this.props.record.data[this.props.name];
        if (!phoneNumber || !softphoneState.ready) {
            return;
        }
        ev.preventDefault();
        this.env.bus.dispatchEvent(
            new CustomEvent("CALL_CENTER:DIAL", { detail: { phoneNumber } })
        );
    }
}

export const callCenterPhoneField = {
    component: CallCenterPhoneField,
    displayName: _t("Phone (Call Center)"),
    supportedTypes: ["char"],
    extractProps: ({ attrs }) => ({
        placeholder: attrs.placeholder,
    }),
};

registry.category("fields").add("sa_call_center_phone", callCenterPhoneField);
