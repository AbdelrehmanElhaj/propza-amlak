"""
Ejar queue_job — Retry Policies & Exception Classifier
========================================================
Single source of truth for every queue_job configuration constant.

Import these into model files that use @job / with_delay() so that
retry timings and channel names are never scattered across the codebase.

Channel topology (configure in odoo.cfg or ODOO_QUEUE_JOB_CHANNELS):
  [queue_job]
  channels = root:4,root.ejar:8,root.ejar.contracts:2,root.ejar.polling:10,root.ejar.documents:3

  root.ejar.contracts  — full submission pipelines (heavy, 2 workers)
  root.ejar.polling    — lightweight status polls (10 workers, high throughput)
  root.ejar.documents  — PDF uploads (3 workers, large payloads)
"""

from __future__ import annotations

import logging
from typing import NoReturn

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Channel names
# ---------------------------------------------------------------------------

CHANNEL_ROOT      = "root.ejar"
CHANNEL_CONTRACTS = "root.ejar.contracts"
CHANNEL_POLLING   = "root.ejar.polling"
CHANNEL_DOCUMENTS = "root.ejar.documents"

# ---------------------------------------------------------------------------
# Job priorities  (lower number = higher priority)
# ---------------------------------------------------------------------------

PRIORITY_SUBMISSION = 10   # contract creation is high-value
PRIORITY_POLLING    = 20   # status checks can wait
PRIORITY_CLEANUP    = 30   # maintenance is lowest priority

# ---------------------------------------------------------------------------
# Max retries per job type
# ---------------------------------------------------------------------------

MAX_SUBMISSION_RETRIES = 5
MAX_POLL_RETRIES       = 20   # polls run for the life of the contract
MAX_DOCUMENT_RETRIES   = 4

# ---------------------------------------------------------------------------
# Retry patterns  {attempt_number: seconds_before_next_retry}
#
# Formula: backoff = pattern[min(retry, max_key)]
# queue_job picks the value for the CURRENT retry count.
# ---------------------------------------------------------------------------

SUBMISSION_RETRY_PATTERN: dict[int, int] = {
    0:  60,        #  1 min  — fast first retry for transient blips
    1:  300,       #  5 min
    2:  1_800,     # 30 min
    3:  7_200,     #  2 hrs
    4:  14_400,    #  4 hrs  — final attempt before dead-letter
}

POLLING_RETRY_PATTERN: dict[int, int] = {
    0:  300,       #  5 min
    1:  900,       # 15 min
    2:  1_800,     # 30 min
    3:  3_600,     #  1 hr
    4:  7_200,     #  2 hrs
}

DOCUMENT_RETRY_PATTERN: dict[int, int] = {
    0:  30,        # 30 s
    1:  120,       #  2 min
    2:  600,       # 10 min
    3:  1_800,     # 30 min
}

# ---------------------------------------------------------------------------
# Exception classifier
# ---------------------------------------------------------------------------

def classify_ejar_exception(exc: Exception) -> NoReturn:
    """
    Convert an EjarAPIError subclass into the appropriate queue_job exception.

    Call this inside a @job method's except block::

        try:
            ...
        except EjarAPIError as exc:
            classify_ejar_exception(exc)

    Raises:
        RetryableJobError — for transient failures (network, rate limit, 5xx)
        FailedJobError    — for permanent failures (validation, forbidden, payload)

    The caller must NOT catch these; queue_job intercepts them.
    """
    try:
        from odoo.addons.queue_job.exception import RetryableJobError, FailedJobError
    except ImportError:
        raise exc  # queue_job not installed; let the exception bubble naturally

    from .exceptions import (
        EjarNetworkError,
        EjarTimeoutError,
        EjarRateLimitError,
        EjarServerError,
        EjarCircuitOpenError,
        EjarAuthError,
        EjarValidationError,
        EjarForbiddenError,
        EjarNotFoundError,
        EjarPayloadError,
        EjarConfigurationError,
        EjarTokenError,
        EjarTokenExpiredError,
    )

    # --- Transient: always retry ---

    if isinstance(exc, (EjarNetworkError, EjarTimeoutError)):
        _logger.warning("Ejar transient network error — retrying: %s", exc)
        raise RetryableJobError(str(exc), ignore_retry=False) from exc

    if isinstance(exc, EjarRateLimitError):
        retry_after = max(getattr(exc, "retry_after", 60), 5)
        _logger.warning("Ejar rate limit — retry after %ds: %s", retry_after, exc)
        raise RetryableJobError(str(exc), seconds=retry_after, ignore_retry=False) from exc

    if isinstance(exc, EjarServerError):
        _logger.warning("Ejar server error — retrying: %s", exc)
        raise RetryableJobError(str(exc)) from exc

    if isinstance(exc, EjarCircuitOpenError):
        retry_after = max(getattr(exc, "retry_after", 60), 5)
        _logger.warning(
            "Ejar circuit open — retry after %ds (failures=%s): %s",
            retry_after, getattr(exc, "failure_count", "?"), exc,
        )
        raise RetryableJobError(str(exc), seconds=retry_after) from exc

    if isinstance(exc, EjarAuthError):
        # Token expired / rejected — retry once after cache invalidation
        _logger.warning("Ejar auth error — one retry: %s", exc)
        raise RetryableJobError(str(exc), seconds=30) from exc

    if isinstance(exc, (EjarTokenExpiredError,)):
        _logger.warning("Ejar token expired — retrying: %s", exc)
        raise RetryableJobError(str(exc), seconds=60) from exc

    # --- Permanent: dead-letter immediately ---

    if isinstance(exc, (
        EjarValidationError,
        EjarForbiddenError,
        EjarNotFoundError,
        EjarPayloadError,
        EjarConfigurationError,
        EjarTokenError,
    )):
        _logger.error("Ejar permanent error — dead-lettering: %s", exc)
        raise FailedJobError(str(exc)) from exc

    # --- Unknown: retry conservatively ---
    _logger.error("Unknown Ejar exception type %s — retrying: %s", type(exc).__name__, exc)
    raise RetryableJobError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Identity key helpers (prevent duplicate jobs)
# ---------------------------------------------------------------------------

def submission_identity_key(contract_id: int) -> str:
    return f"ejar-submit-{contract_id}"


def polling_identity_key(contract_id: int) -> str:
    return f"ejar-poll-{contract_id}"


def document_upload_identity_key(contract_id: int) -> str:
    return f"ejar-docupload-{contract_id}"
