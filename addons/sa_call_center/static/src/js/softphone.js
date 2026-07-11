/** @odoo-module **/

import { Component, useState, onWillStart, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";
import { softphoneState } from "./softphone_state";

const TWILIO_SDK_URL = "https://cdn.jsdelivr.net/npm/@twilio/voice-sdk@2.18.3/dist/twilio.min.js";
const TOKEN_REFRESH_MS = 50 * 60 * 1000; // Access Token صالح لساعة واحدة افتراضياً

/**
 * سمّاعة مركز الاتصال — تسجّل متصفح الموظف كـ Twilio Client ليستقبل
 * المكالمات مباشرة داخل واجهة Odoo (بالتوازي مع رقم التحويل الثابت).
 * لا تُفعَّل الواجهة إطلاقاً إن لم يكن المستخدم موظف مركز اتصال، أو لم
 * تُضبط بيانات Twilio API Key بعد (الخادم هو مصدر الحقيقة الوحيد لهذا).
 */
export class CallCenterSoftphone extends Component {
    static template = "sa_call_center.CallCenterSoftphone";
    static props = {};

    setup() {
        this.rpc = useService("rpc");
        this.notification = useService("notification");
        this.state = useState({
            visible: false,
            status: "idle", // idle | incoming | dialing | connected
            fromNumber: "",
        });
        this.device = null;
        this.activeCall = null;
        this.refreshTimer = null;
        this._onDialRequest = (ev) => this.dial(ev.detail.phoneNumber);

        onWillStart(() => this._init());
        this.env.bus.addEventListener("CALL_CENTER:DIAL", this._onDialRequest);
        onWillUnmount(() => {
            this.env.bus.removeEventListener("CALL_CENTER:DIAL", this._onDialRequest);
            if (this.refreshTimer) {
                clearInterval(this.refreshTimer);
            }
            if (this.device) {
                this.device.destroy();
            }
            softphoneState.ready = false;
        });
    }

    /** يستدعيه زر "اتصال" في أي واجهة (مثل ملف العميل) عبر حدث على env.bus. */
    async dial(phoneNumber) {
        if (!phoneNumber) {
            return;
        }
        if (!this.device) {
            this.notification.add(
                "السمّاعة غير جاهزة — تأكد أنك موظف مركز اتصال وأن بيانات Twilio مضبوطة.",
                { type: "warning" }
            );
            return;
        }
        if (this.state.status !== "idle") {
            this.notification.add("يوجد مكالمة جارية بالفعل.", { type: "warning" });
            return;
        }

        this.state.status = "dialing";
        this.state.fromNumber = phoneNumber;
        this.state.visible = true;
        try {
            this.activeCall = await this.device.connect({ params: { To: phoneNumber } });
        } catch (error) {
            console.error("sa_call_center: outbound connect failed", error);
            this._reset();
            return;
        }
        this.activeCall.on("accept", () => {
            this.state.status = "connected";
        });
        this.activeCall.on("disconnect", () => this._reset());
        this.activeCall.on("cancel", () => this._reset());
        this.activeCall.on("reject", () => this._reset());
        this.activeCall.on("error", (error) => console.error("sa_call_center: Twilio Call error", error));
    }

    async _fetchToken() {
        try {
            return await this.rpc("/callcenter/twilio/token", {});
        } catch (e) {
            return null;
        }
    }

    async _init() {
        const result = await this._fetchToken();
        if (!result || result.error || !result.token) {
            return;
        }

        await loadJS(TWILIO_SDK_URL);
        this.device = new window.Twilio.Device(result.token, { logLevel: 1 });
        this.device.on("incoming", (call) => this._onIncoming(call));
        this.device.on("error", (error) => {
            console.error("sa_call_center: Twilio Device error", error);
            softphoneState.ready = false;
        });
        this.device.on("registered", () => {
            console.log("sa_call_center: Twilio Device registered");
            softphoneState.ready = true;
        });
        this.device.on("unregistered", () => {
            softphoneState.ready = false;
        });
        try {
            await this.device.register();
        } catch (error) {
            console.error("sa_call_center: Twilio Device registration failed", error);
        }

        this.refreshTimer = setInterval(async () => {
            const refreshed = await this._fetchToken();
            if (refreshed && refreshed.token && this.device) {
                this.device.updateToken(refreshed.token);
            }
        }, TOKEN_REFRESH_MS);
    }

    _onIncoming(call) {
        this.activeCall = call;
        this.state.status = "incoming";
        this.state.fromNumber = (call.parameters && call.parameters.From) || "";
        this.state.visible = true;

        call.on("cancel", () => this._reset());
        call.on("disconnect", () => this._reset());
        call.on("reject", () => this._reset());
        call.on("error", (error) => console.error("sa_call_center: Twilio Call error", error));
        call.on("accept", () => console.log("sa_call_center: call accepted, media should be live now"));
    }

    onAccept() {
        if (this.activeCall) {
            this.activeCall.accept();
            this.state.status = "connected";
        }
    }

    onReject() {
        if (this.activeCall) {
            this.activeCall.reject();
        }
        this._reset();
    }

    onHangup() {
        if (this.activeCall) {
            this.activeCall.disconnect();
        }
        this._reset();
    }

    _reset() {
        this.activeCall = null;
        this.state.status = "idle";
        this.state.visible = false;
        this.state.fromNumber = "";
    }
}

registry.category("main_components").add("CallCenterSoftphone", {
    Component: CallCenterSoftphone,
});
