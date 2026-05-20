from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class EjarSubmitWizard(models.TransientModel):
    """
    Pre-submission validation wizard.

    Shows a readiness checklist and an environment warning before
    enqueueing the background submission job.

    The actual Ejar API calls happen in job_execute_full_submission()
    running in a queue_job worker — the wizard just validates and enqueues.
    """

    _name = "ejar.submit.wizard"
    _description = "معالج إرسال العقد إلى إيجار"

    # ── Target contract ───────────────────────────────────────────────
    contract_id = fields.Many2one(
        "ejar.contract",
        string="العقد",
        required=True,
        readonly=True,
        ondelete="cascade",
    )

    # ── Readiness checks (computed, readonly) ─────────────────────────
    check_brokerage = fields.Boolean(string="ملف مكتب الوساطة", compute="_compute_checks")
    check_lessor    = fields.Boolean(string="المؤجر",            compute="_compute_checks")
    check_tenant    = fields.Boolean(string="المستأجر",          compute="_compute_checks")
    check_unit      = fields.Boolean(string="الوحدة",            compute="_compute_checks")
    check_signed_doc= fields.Boolean(string="العقد الموقّع",     compute="_compute_checks")
    check_dates     = fields.Boolean(string="التواريخ والإيجار", compute="_compute_checks")

    all_checks_pass  = fields.Boolean(compute="_compute_checks")
    missing_summary  = fields.Text(string="العناصر الناقصة", compute="_compute_checks")

    # ── Environment ───────────────────────────────────────────────────
    environment   = fields.Char(string="البيئة", compute="_compute_environment")
    is_production = fields.Boolean(compute="_compute_environment")

    # ── Async mode ────────────────────────────────────────────────────
    queue_job_available = fields.Boolean(compute="_compute_queue_job_available")
    processing_mode = fields.Char(
        string="وضع المعالجة",
        compute="_compute_queue_job_available",
    )

    # ── Confirmation ──────────────────────────────────────────────────
    confirmed = fields.Boolean(
        string="أؤكد إرسال هذا العقد إلى إيجار",
        default=False,
    )

    # ── Compute ───────────────────────────────────────────────────────

    @api.depends(
        "contract_id",
        "contract_id.brokerage_profile_id",
        "contract_id.has_lessor",
        "contract_id.has_tenant",
        "contract_id.has_unit",
        "contract_id.signed_doc",
        "contract_id.start_date",
        "contract_id.end_date",
        "contract_id.rent_amount",
    )
    def _compute_checks(self):
        for rec in self:
            c = rec.contract_id
            if not c:
                rec.check_brokerage = rec.check_lessor = rec.check_tenant = False
                rec.check_unit = rec.check_signed_doc = rec.check_dates = False
                rec.all_checks_pass = False
                rec.missing_summary = ""
                continue

            rec.check_brokerage  = bool(c.brokerage_profile_id)
            rec.check_lessor     = c.has_lessor
            rec.check_tenant     = c.has_tenant
            rec.check_unit       = c.has_unit
            rec.check_signed_doc = bool(c.signed_doc)
            rec.check_dates      = bool(c.start_date and c.end_date and c.rent_amount > 0)

            missing = []
            if not rec.check_brokerage:  missing.append(_("ملف مكتب الوساطة"))
            if not rec.check_lessor:     missing.append(_("المؤجر"))
            if not rec.check_tenant:     missing.append(_("المستأجر"))
            if not rec.check_unit:       missing.append(_("وحدة عقارية"))
            if not rec.check_signed_doc: missing.append(_("العقد الموقّع (PDF)"))
            if not rec.check_dates:      missing.append(_("التواريخ وقيمة الإيجار"))

            rec.all_checks_pass = not missing
            rec.missing_summary = "\n• ".join(missing) if missing else ""

    @api.depends("contract_id.company_id")
    def _compute_environment(self):
        from ..services.auth_service import EjarAuthService
        for rec in self:
            if not rec.contract_id:
                rec.environment = "uat"
                rec.is_production = False
                continue
            auth = EjarAuthService(self.env)
            env_name = auth.get_environment(rec.contract_id.company_id.id)
            rec.environment   = env_name
            rec.is_production = env_name == "production"

    def _compute_queue_job_available(self):
        try:
            import odoo.addons.queue_job  # noqa: F401
            available = True
        except ImportError:
            available = False

        for rec in self:
            rec.queue_job_available = available
            rec.processing_mode = (
                "خلفي (queue_job)" if available else "متزامن (بدون queue_job)"
            )

    # ── Actions ───────────────────────────────────────────────────────

    def action_confirm_submit(self):
        """Validate, then enqueue (or synchronously run) the submission."""
        self.ensure_one()

        if not self.all_checks_pass:
            raise UserError(
                _("لا يمكن الإرسال. العناصر الناقصة:\n• %s") % self.missing_summary
            )
        if not self.confirmed:
            raise UserError(_("يرجى تأكيد الإرسال أولاً بتحديد مربع التأكيد"))

        contract = self.contract_id

        if self.queue_job_available:
            # Async path — enqueue job and return immediately
            contract.action_submit_async()
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("تم الإدراج في قائمة الانتظار"),
                    "message": _(
                        "تم إدراج مهمة الإرسال في الخلفية. "
                        "سيتحدث حقل 'حالة المهمة' تلقائياً."
                    ),
                    "type": "success",
                    "sticky": False,
                },
            }
        else:
            # Sync fallback (dev / testing with no workers)
            from ..services.lifecycle_service import EjarContractLifecycleService
            try:
                svc = EjarContractLifecycleService(self.env)
                result = svc.execute_full_submission(contract.id)
            except Exception as exc:
                raise UserError(_("فشل الإرسال إلى إيجار:\n%s") % str(exc)) from exc

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("تم الإرسال"),
                    "message": _(
                        "تم إرسال العقد بنجاح. رقم العقد: %s"
                    ) % result.get("ejar_contract_number", "—"),
                    "type": "success",
                    "sticky": False,
                },
            }
