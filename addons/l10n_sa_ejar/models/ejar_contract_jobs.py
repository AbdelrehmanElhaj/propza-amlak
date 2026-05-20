"""
Ejar Contract — Async Job Layer
================================
Extends ejar.contract with queue_job-based async processing.

All blocking Ejar API calls are replaced by background jobs that:
  - Run in dedicated queue channels
  - Retry with exponential backoff on transient errors
  - Dead-letter on permanent errors (with chatter + activity)
  - Are idempotent: re-running a job on a partially-complete contract
    resumes from the last successful step

Job flow:
  User confirms wizard
      → action_submit_async() enqueues job_execute_full_submission
          → contract.ejar_status = 'submitting' (immediate, no API call)
  Background worker picks up job
      → EjarContractLifecycleService.execute_full_submission()
          → on success:  ejar_status = 'submitted'
          → on transient: RetryableJobError (queue_job retries)
          → on permanent: FailedJobError → _mark_dead_letter()
  Cron enqueues job_poll_ejar_status for each 'submitted' contract
      → _poll_ejar_status()
          → on approval:  ejar_status = 'approved'
          → on rejection: ejar_status = 'rejected' + reason
"""

from __future__ import annotations

import datetime
import logging
from typing import Optional

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# queue_job imports — graceful if not installed
# ---------------------------------------------------------------------------

try:
    from odoo.addons.queue_job.job import job as _queue_job
    from odoo.addons.queue_job.exception import RetryableJobError, FailedJobError
    _QUEUE_JOB_AVAILABLE = True
except ImportError:
    _QUEUE_JOB_AVAILABLE = False

    def _queue_job(*args, **kwargs):
        """No-op decorator used when queue_job is not installed."""
        if args and callable(args[0]):
            return args[0]
        return lambda fn: fn

    class RetryableJobError(Exception):  # type: ignore[misc]
        pass

    class FailedJobError(Exception):  # type: ignore[misc]
        pass

# ---------------------------------------------------------------------------
# Policy constants (imported here so @job decorator sees them at class-def time)
# ---------------------------------------------------------------------------

from ..services.job_policies import (
    CHANNEL_CONTRACTS,
    CHANNEL_DOCUMENTS,
    CHANNEL_POLLING,
    DOCUMENT_RETRY_PATTERN,
    MAX_DOCUMENT_RETRIES,
    MAX_POLL_RETRIES,
    MAX_SUBMISSION_RETRIES,
    POLLING_RETRY_PATTERN,
    PRIORITY_CLEANUP,
    PRIORITY_POLLING,
    PRIORITY_SUBMISSION,
    SUBMISSION_RETRY_PATTERN,
    classify_ejar_exception,
    document_upload_identity_key,
    polling_identity_key,
    submission_identity_key,
)


# ---------------------------------------------------------------------------
# Model extension
# ---------------------------------------------------------------------------


class EjarContractJobs(models.Model):
    _inherit = "ejar.contract"

    # ── Job monitoring fields ─────────────────────────────────────────

    active_job_uuid = fields.Char(
        string="معرّف المهمة النشطة",
        readonly=True,
        copy=False,
        index=True,
        help="UUID of the currently active queue.job record",
    )
    job_channel = fields.Char(
        string="قناة المهمة",
        readonly=True,
        copy=False,
    )
    job_enqueued_at = fields.Datetime(
        string="وقت الإدراج",
        readonly=True,
        copy=False,
    )
    job_retry_count = fields.Integer(
        string="عدد إعادات المحاولة",
        readonly=True,
        copy=False,
        default=0,
    )
    job_last_error = fields.Text(
        string="آخر خطأ في المهمة",
        readonly=True,
        copy=False,
    )

    # Computed from queue.job record (never stored — always live)
    job_state = fields.Char(
        string="حالة المهمة",
        compute="_compute_job_state",
        store=False,
    )
    job_progress = fields.Char(
        string="تقدم المهمة",
        compute="_compute_job_state",
        store=False,
    )
    has_active_job = fields.Boolean(
        string="توجد مهمة نشطة",
        compute="_compute_job_state",
        store=False,
    )

    # ── Compute: live job state from queue.job ────────────────────────

    @api.depends("active_job_uuid", "ejar_status")
    def _compute_job_state(self):
        _LABELS = {
            "pending":   "في قائمة الانتظار",
            "enqueued":  "في قائمة الانتظار",
            "started":   "قيد التنفيذ",
            "done":      "مكتمل",
            "failed":    "فشل",
            "cancelled": "ملغي",
        }
        QueueJob = self.env.get("queue.job")

        for rec in self:
            if not rec.active_job_uuid or not QueueJob:
                rec.job_state = ""
                rec.job_progress = ""
                rec.has_active_job = False
                continue

            qjob = QueueJob.sudo().search(
                [("uuid", "=", rec.active_job_uuid)], limit=1
            )

            if not qjob:
                rec.job_state = ""
                rec.job_progress = ""
                rec.has_active_job = False
                continue

            state = qjob.state
            retry = getattr(qjob, "retry", 0)
            max_r = getattr(qjob, "max_retries", 1)
            eta = getattr(qjob, "eta", None)

            rec.job_state = state
            rec.has_active_job = state in ("pending", "enqueued", "started")

            if state == "failed":
                exc_snippet = (getattr(qjob, "exc_info", "") or "")[:120]
                rec.job_progress = f"فشل (محاولة {retry}/{max_r}): {exc_snippet}"

            elif state == "started":
                rec.job_progress = f"قيد التنفيذ — محاولة {retry + 1}/{max_r}"

            elif state in ("pending", "enqueued"):
                if eta and retry > 0:
                    eta_str = eta.strftime("%H:%M")
                    rec.job_progress = (
                        f"إعادة محاولة {retry}/{max_r} — التالية في {eta_str}"
                    )
                else:
                    rec.job_progress = "في قائمة الانتظار"

            elif state == "done":
                rec.job_progress = "مكتملة"

            else:
                rec.job_progress = _LABELS.get(state, state)

    # ==================================================================
    # Public: enqueue submission
    # ==================================================================

    def action_submit_async(self) -> None:
        """
        Immediately move contract to 'submitting' and enqueue the
        background submission job.  Called from ejar.submit.wizard.

        Returns None — the wizard shows a notification after calling this.
        """
        self.ensure_one()
        self._validate_ready_state()

        if not _QUEUE_JOB_AVAILABLE:
            raise UserError(
                _(
                    "وحدة queue_job غير مثبتة. "
                    "يرجى تثبيتها أو استخدام الإرسال المتزامن."
                )
            )

        # Block duplicate enqueue
        if self.has_active_job:
            raise UserError(
                _("توجد مهمة إرسال قيد التنفيذ بالفعل (%(uuid)s)")
                % {"uuid": self.active_job_uuid}
            )

        # Advance state synchronously — user sees 'submitting' immediately
        self.write(
            {
                "ejar_status": "submitting",
                "submit_error": False,
                "job_last_error": False,
                "submit_attempt": self.submit_attempt + 1,
                "job_enqueued_at": fields.Datetime.now(),
                "job_channel": CHANNEL_CONTRACTS,
            }
        )
        self.env.cr.commit()

        delayable = self.with_delay(
            channel=CHANNEL_CONTRACTS,
            description=_("إرسال عقد إيجار: %s") % self.name,
            max_retries=MAX_SUBMISSION_RETRIES,
            identity_key=submission_identity_key(self.id),
            priority=PRIORITY_SUBMISSION,
        )
        result = delayable.job_execute_full_submission()

        job_uuid = getattr(result, "uuid", None)
        if job_uuid:
            self.sudo().write({"active_job_uuid": job_uuid})

        self.message_post(
            body=_("تم إدراج مهمة الإرسال في قائمة الانتظار (%(uuid)s).")
            % {"uuid": job_uuid or "—"},
        )

    # ==================================================================
    # Public: cancel pending job
    # ==================================================================

    def action_cancel_pending_job(self):
        """Cancel a job that is still pending (not yet started)."""
        self.ensure_one()
        if not self.active_job_uuid:
            raise UserError(_("لا توجد مهمة نشطة لهذا العقد"))

        QueueJob = self.env.get("queue.job")
        if not QueueJob:
            raise UserError(_("queue_job غير مثبت"))

        qjob = QueueJob.sudo().search(
            [
                ("uuid", "=", self.active_job_uuid),
                ("state", "in", ("pending", "enqueued")),
            ],
            limit=1,
        )
        if not qjob:
            raise UserError(
                _("المهمة ليست في حالة الانتظار ولا يمكن إلغاؤها")
            )

        qjob.button_cancelled()
        self.write(
            {
                "ejar_status": "ready",
                "active_job_uuid": False,
                "job_channel": False,
            }
        )
        self.message_post(body=_("تم إلغاء مهمة الإرسال من قائمة الانتظار"))

    # ==================================================================
    # Job: full submission pipeline
    # ==================================================================

    @_queue_job(retry_pattern=SUBMISSION_RETRY_PATTERN)
    def job_execute_full_submission(self) -> None:
        """
        Background job: run the complete 14-step Ejar ECRS pipeline.

        Idempotent — each step checks its Ejar UUID before calling the API,
        so re-running after a partial failure resumes from where it left off.

        Retry policy: SUBMISSION_RETRY_PATTERN (up to MAX_SUBMISSION_RETRIES).
        On permanent failure: _mark_dead_letter() + FailedJobError.
        """
        self.ensure_one()
        _logger.info(
            "Ejar job_execute_full_submission START | contract=%s company=%s",
            self.name,
            self.company_id.id,
        )

        # Idempotency guard
        if self.ejar_status in ("submitted", "approved"):
            _logger.info(
                "Contract %s already in state %s — job is a no-op",
                self.name,
                self.ejar_status,
            )
            return

        from ..services.lifecycle_service import EjarContractLifecycleService
        from ..services.exceptions import EjarAPIError

        try:
            svc = EjarContractLifecycleService(self.env)
            svc.execute_full_submission(self.id)
            # Lifecycle service sets ejar_status = 'submitted' on success
            self.sudo().write({"job_last_error": False})

        except EjarAPIError as exc:
            self._handle_submission_exc(exc)

        except Exception as exc:
            _logger.exception(
                "Unexpected error in job_execute_full_submission for %s: %s",
                self.name,
                exc,
            )
            # Unknown — retry conservatively
            raise RetryableJobError(str(exc)) from exc

    # ==================================================================
    # Job: poll Ejar status
    # ==================================================================

    @_queue_job(retry_pattern=POLLING_RETRY_PATTERN)
    def job_poll_ejar_status(self) -> None:
        """
        Background job: poll Ejar GET /contracts/{id} and update Odoo state.

        Safe to call repeatedly (idempotent).
        Uses identity_key so only one poll job runs per contract at a time.
        """
        self.ensure_one()
        _logger.debug(
            "Ejar job_poll_ejar_status | contract=%s ejar_id=%s",
            self.name,
            self.ejar_contract_id,
        )

        if self.ejar_status not in self._POLLABLE_STATES:
            return
        if not self.ejar_contract_id:
            return

        from ..services.exceptions import EjarAPIError

        try:
            self._poll_ejar_status()
            self.sudo().write(
                {"next_poll_at": fields.Datetime.now() + datetime.timedelta(minutes=30)}
            )
        except EjarAPIError as exc:
            classify_ejar_exception(exc)  # raises RetryableJobError or FailedJobError
        except Exception as exc:
            _logger.exception(
                "Unexpected error polling contract %s: %s", self.name, exc
            )
            raise RetryableJobError(str(exc)) from exc

    # ==================================================================
    # Job: upload signed document
    # ==================================================================

    @_queue_job(retry_pattern=DOCUMENT_RETRY_PATTERN)
    def job_upload_signed_document(
        self, doc_b64: str, filename: str, *, trigger_submission: bool = False
    ) -> None:
        """
        Background job: upload a signed PDF to Ejar.

        Args:
            doc_b64:            Base64-encoded PDF content.
            filename:           Original filename.
            trigger_submission: If True, enqueue full submission after upload.
        """
        self.ensure_one()
        _logger.info(
            "Ejar job_upload_signed_document | contract=%s file=%s",
            self.name,
            filename,
        )

        import base64
        from ..services.ejar_client import EjarApiClient
        from ..services.exceptions import EjarAPIError

        if not self.ejar_contract_id:
            raise FailedJobError(
                f"Contract {self.name} has no ejar_contract_id — "
                "cannot upload document before contract is created on Ejar"
            )

        content = base64.b64decode(doc_b64)

        try:
            client = EjarApiClient(self.env, company_id=self.company_id.id)
            client.upload_signed_document(
                self.ejar_contract_id, content, filename
            )
        except EjarAPIError as exc:
            classify_ejar_exception(exc)
        except Exception as exc:
            raise RetryableJobError(str(exc)) from exc

        # Persist uploaded doc on the contract record
        self.sudo().write(
            {
                "signed_doc": doc_b64,
                "signed_doc_filename": filename,
            }
        )
        self.message_post(
            body=_("تم رفع المستند الموقّع إلى إيجار في الخلفية: %s") % filename,
        )

        if trigger_submission and self.is_ready_to_submit:
            self.action_submit_async()

    # ==================================================================
    # Override: action_submit_to_ejar → open wizard (unchanged)
    # Override: action_check_ejar_status → enqueue poll job
    # ==================================================================

    def action_check_ejar_status(self):
        """Override: enqueue a poll job instead of blocking the request."""
        self.ensure_one()
        if not self.ejar_contract_id:
            raise UserError(_("لا يوجد معرّف عقد إيجار للاستعلام عنه"))

        if not _QUEUE_JOB_AVAILABLE:
            # Fallback to synchronous polling if queue_job not installed
            return super().action_check_ejar_status()

        delayable = self.with_delay(
            channel=CHANNEL_POLLING,
            description=_("استطلاع حالة عقد: %s") % self.name,
            max_retries=MAX_POLL_RETRIES,
            identity_key=polling_identity_key(self.id),
            priority=PRIORITY_POLLING,
        )
        result = delayable.job_poll_ejar_status()
        job_uuid = getattr(result, "uuid", None)
        if job_uuid:
            self.sudo().write({"active_job_uuid": job_uuid})

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("مهمة في قائمة الانتظار"),
                "message": _("تم إدراج مهمة استطلاع الحالة. سيتم التحديث قريباً."),
                "type": "info",
                "sticky": False,
            },
        }

    # ==================================================================
    # Override: cron → enqueue one poll job per submitted contract
    # ==================================================================

    @api.model
    def _cron_poll_submitted_contracts(self) -> None:
        """
        Override cron: instead of polling inline, enqueue one
        job_poll_ejar_status job per submitted contract.

        This allows parallel polling across N workers, with per-contract
        retry if any single poll fails.
        """
        if not _QUEUE_JOB_AVAILABLE:
            return super()._cron_poll_submitted_contracts()

        now = fields.Datetime.now()
        contracts = self.search(
            [
                ("ejar_status", "in", list(self._POLLABLE_STATES)),
                "|",
                ("next_poll_at", "=", False),
                ("next_poll_at", "<=", now),
            ]
        )

        _logger.info(
            "Ejar poll cron: enqueuing %d polling jobs", len(contracts)
        )

        for contract in contracts:
            try:
                delayable = contract.with_delay(
                    channel=CHANNEL_POLLING,
                    description=_("استطلاع: %s") % contract.name,
                    max_retries=MAX_POLL_RETRIES,
                    identity_key=polling_identity_key(contract.id),
                    priority=PRIORITY_POLLING,
                )
                result = delayable.job_poll_ejar_status()
                job_uuid = getattr(result, "uuid", None)

                contract.sudo().write(
                    {
                        "active_job_uuid": job_uuid or contract.active_job_uuid,
                        "next_poll_at": now + datetime.timedelta(minutes=30),
                    }
                )
            except Exception as exc:
                _logger.exception(
                    "Failed to enqueue poll job for contract %s: %s",
                    contract.name,
                    exc,
                )

    # ==================================================================
    # Cleanup crons
    # ==================================================================

    @api.model
    def _cron_cleanup_dead_letter_jobs(self) -> None:
        """
        Find contracts stuck in 'submitting' whose queue.job has failed
        (exhausted all retries) and move them to dead-letter state.

        Runs every 15 minutes.
        """
        QueueJob = self.env.get("queue.job")
        if not QueueJob:
            return

        stuck = self.search(
            [
                ("ejar_status", "=", "submitting"),
                ("active_job_uuid", "!=", False),
            ]
        )
        if not stuck:
            return

        uuids = stuck.mapped("active_job_uuid")
        failed_jobs = QueueJob.sudo().search(
            [("uuid", "in", uuids), ("state", "in", ("failed", "cancelled"))]
        )
        failed_uuid_map = {j.uuid: j for j in failed_jobs}

        for contract in stuck:
            job_rec = failed_uuid_map.get(contract.active_job_uuid)
            if not job_rec:
                continue

            exc_info = (getattr(job_rec, "exc_info", "") or "")[:500]
            reason = exc_info or _("استنفدت جميع محاولات إعادة الإرسال")

            _logger.warning(
                "Dead-lettering contract %s (job %s failed after max retries)",
                contract.name,
                contract.active_job_uuid,
            )
            contract._mark_dead_letter(reason)

    @api.model
    def _cron_purge_old_sync_logs(self) -> None:
        """
        Delete ejar.sync.log records older than 90 days.
        Prevents unbounded table growth in production.
        """
        cutoff = fields.Datetime.now() - datetime.timedelta(days=90)
        old_logs = self.env["ejar.sync.log"].sudo().search(
            [("create_date", "<", cutoff)]
        )
        count = len(old_logs)
        if count:
            old_logs.unlink()
            _logger.info("Purged %d old ejar.sync.log records (older than 90d)", count)

    @api.model
    def _cron_purge_completed_jobs(self) -> None:
        """
        Delete queue.job records in 'done' state older than 30 days
        that belong to Ejar channels, keeping the queue table lean.
        """
        QueueJob = self.env.get("queue.job")
        if not QueueJob:
            return

        cutoff = fields.Datetime.now() - datetime.timedelta(days=30)
        old_jobs = QueueJob.sudo().search(
            [
                ("state", "=", "done"),
                ("date_done", "<", cutoff),
                ("channel", "like", "root.ejar"),
            ]
        )
        count = len(old_jobs)
        if count:
            old_jobs.unlink()
            _logger.info(
                "Purged %d completed Ejar queue.job records (>30d)", count
            )

    # ==================================================================
    # Dead-letter handler
    # ==================================================================

    def _mark_dead_letter(self, reason: str) -> None:
        """
        Move contract back to 'ready', post chatter message,
        open an Odoo activity for human review.

        Called when:
          a) A permanent API error (is_permanent=True) is caught in a job.
          b) The cleanup cron finds a 'submitting' contract with a failed job.
        """
        self.ensure_one()
        _logger.error(
            "Ejar dead-letter | contract=%s reason=%s", self.name, reason[:200]
        )

        self.sudo().write(
            {
                "ejar_status": "ready",
                "submit_error": reason[:2048],
                "job_last_error": reason[:2048],
                "active_job_uuid": False,
                "job_channel": False,
            }
        )

        self.message_post(
            body=_(
                "<strong>❌ فشل الإرسال إلى إيجار بشكل دائم.</strong><br/>"
                "<strong>السبب:</strong> %(reason)s<br/>"
                "يرجى تصحيح البيانات وإعادة الإرسال."
            )
            % {"reason": reason[:500]},
        )

        activity_type = self.env.ref(
            "mail.mail_activity_data_todo", raise_if_not_found=False
        )
        if activity_type:
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("مراجعة خطأ إيجار"),
                note=_("فشل إرسال العقد %(name)s: %(reason)s")
                % {"name": self.name, "reason": reason[:200]},
            )

    # ==================================================================
    # Internal: exception router for submission job
    # ==================================================================

    def _handle_submission_exc(self, exc: Exception) -> None:
        """
        Called inside job_execute_full_submission's except block.
        Routes to RetryableJobError, FailedJobError, or dead-letter.
        """
        # Persist the error for the UI regardless of whether we retry or not
        self.sudo().write({"job_last_error": str(exc)[:2048]})

        is_permanent = getattr(exc, "is_permanent", False)
        if is_permanent:
            self._mark_dead_letter(str(exc))
            raise FailedJobError(str(exc)) from exc

        # Delegate to policy classifier for everything else
        classify_ejar_exception(exc)
