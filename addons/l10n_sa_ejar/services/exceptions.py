"""
Ejar ECRS API — Exception Hierarchy
=====================================
Every exception carries structured metadata so callers can make
precise retry/dead-letter decisions without parsing string messages.

Retry decision guide:
  EjarNetworkError        → retry (transient)
  EjarRateLimitError      → retry after retry_after seconds
  EjarServerError         → retry (transient, max 3)
  EjarAuthError           → attempt token refresh once, then dead-letter
  EjarForbiddenError      → dead-letter, alert operations
  EjarValidationError     → dead-letter, requires human correction
  EjarConflictError       → treat as success (idempotency — already processed)
  EjarNotFoundError       → dead-letter, check submitted IDs
  EjarIdentityError       → dead-letter, pre-flight gate — never reached HTTP layer
  EjarCircuitOpenError    → dead-letter until circuit recovers
  EjarConfigurationError  → dead-letter, alert operations immediately
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class EjarAPIError(Exception):
    """
    Root of all Ejar API exceptions.

    All subclasses must populate `should_retry` so queue processors
    can branch without isinstance() chains.
    """

    should_retry: bool = False
    is_permanent: bool = False
    http_status: Optional[int] = None

    def __init__(
        self,
        message: str,
        *,
        correlation_id: Optional[str] = None,
        company_id: Optional[int] = None,
        endpoint: Optional[str] = None,
        http_status: Optional[int] = None,
        raw_response: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.correlation_id = correlation_id
        self.company_id = company_id
        self.endpoint = endpoint
        self.raw_response = raw_response or {}
        if http_status is not None:
            self.http_status = http_status

    def to_dict(self) -> Dict[str, Any]:
        """Structured representation for audit logging."""
        return {
            "exception_type": type(self).__name__,
            "message": self.message,
            "should_retry": self.should_retry,
            "is_permanent": self.is_permanent,
            "http_status": self.http_status,
            "correlation_id": self.correlation_id,
            "company_id": self.company_id,
            "endpoint": self.endpoint,
        }

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}("
            f"message={self.message!r}, "
            f"http_status={self.http_status}, "
            f"correlation_id={self.correlation_id!r}, "
            f"company_id={self.company_id})"
        )


# ---------------------------------------------------------------------------
# Network / Transport Errors  →  retry
# ---------------------------------------------------------------------------


class EjarNetworkError(EjarAPIError):
    """
    TCP/TLS-level failure: connection refused, DNS resolution failure,
    read timeout, SSL error.

    Always transient — retry with backoff.
    """

    should_retry = True
    is_permanent = False

    def __init__(
        self,
        message: str,
        *,
        original_error: Optional[Exception] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.original_error = original_error


class EjarTimeoutError(EjarNetworkError):
    """
    Request timed out waiting for Ejar to respond.
    Subclass of EjarNetworkError — retry policy is identical.
    """


# ---------------------------------------------------------------------------
# Authentication / Authorization Errors
# ---------------------------------------------------------------------------


class EjarAuthError(EjarAPIError):
    """
    HTTP 401 — credentials rejected or token expired.

    Strategy: attempt one token refresh, then retry. If refresh fails,
    dead-letter and alert the operations team.
    """

    should_retry = False   # caller must refresh token first
    is_permanent = False
    http_status = 401

    def __init__(self, message: str, *, token_fingerprint: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.token_fingerprint = token_fingerprint


class EjarForbiddenError(EjarAPIError):
    """
    HTTP 403 — valid credentials, but this brokerage office does not have
    permission to perform the requested operation (e.g., submitting
    a commercial contract with a residential-only license).

    Permanent — do not retry. Alert operations team.
    """

    should_retry = False
    is_permanent = True
    http_status = 403


# ---------------------------------------------------------------------------
# Rate Limiting  →  retry after delay
# ---------------------------------------------------------------------------


class EjarRateLimitError(EjarAPIError):
    """
    HTTP 429 — Ejar rate limit exceeded.

    Always retry, but only after `retry_after` seconds have elapsed.
    Ejar may return a `Retry-After` header; fall back to 60 seconds.
    """

    should_retry = True
    is_permanent = False
    http_status = 429

    def __init__(
        self,
        message: str,
        *,
        retry_after: int = 60,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


# ---------------------------------------------------------------------------
# Client / Validation Errors  →  permanent, dead-letter
# ---------------------------------------------------------------------------


class EjarValidationError(EjarAPIError):
    """
    HTTP 400 or 422 — Ejar rejected our payload.

    The request was structurally or semantically invalid:
    - Missing required field
    - Date in the past
    - Invalid enum value
    - Business rule violation (e.g., end_date before start_date)

    PERMANENT — retrying the same payload will always fail.
    Requires human correction before resubmission.
    """

    should_retry = False
    is_permanent = True

    def __init__(
        self,
        message: str,
        *,
        field_errors: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.field_errors: List[Dict[str, Any]] = field_errors or []

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["field_errors"] = self.field_errors
        return base

    def user_facing_message(self) -> str:
        """Arabic-friendly summary for Odoo UI display."""
        if not self.field_errors:
            return self.message
        details = "; ".join(
            f"{e.get('field', '?')}: {e.get('detail', '')}"
            for e in self.field_errors
        )
        return f"{self.message} — {details}"


class EjarNotFoundError(EjarAPIError):
    """
    HTTP 404 — the requested resource (contract, party, unit) does not exist
    in Ejar's system.

    PERMANENT — indicates a data synchronisation issue (we referenced an ID
    that Ejar doesn't know about).
    """

    should_retry = False
    is_permanent = True
    http_status = 404

    def __init__(
        self,
        message: str,
        *,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.resource_type = resource_type
        self.resource_id = resource_id


# ---------------------------------------------------------------------------
# Conflict / Idempotency  →  treat as success
# ---------------------------------------------------------------------------


class EjarConflictError(EjarAPIError):
    """
    HTTP 409 — the resource already exists or the operation was already
    performed (idempotency collision).

    This is NOT an error in the queue processor — callers should extract
    the existing resource reference from `existing_resource` and continue.

    Do NOT retry and do NOT dead-letter.
    """

    should_retry = False
    is_permanent = False
    http_status = 409

    def __init__(
        self,
        message: str,
        *,
        existing_resource: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.existing_resource = existing_resource or {}


# ---------------------------------------------------------------------------
# Server / Infrastructure Errors  →  retry (transient)
# ---------------------------------------------------------------------------


class EjarServerError(EjarAPIError):
    """
    HTTP 500, 502, 503, 504 — Ejar platform error.

    Transient. Retry with exponential backoff, max 3 additional attempts
    beyond normal retry budget (these errors are more likely to clear
    than 429s which are quota-based).
    """

    should_retry = True
    is_permanent = False

    def __init__(
        self,
        message: str,
        *,
        ejar_error_code: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.ejar_error_code = ejar_error_code


# ---------------------------------------------------------------------------
# Pre-flight / Identity Errors  →  never reach HTTP
# ---------------------------------------------------------------------------


class EjarIdentityValidationError(EjarAPIError):
    """
    Raised by the pre-flight identity gate BEFORE any HTTP call.

    This means a required field in the brokerage profile or party data is
    missing, expired, or inconsistent. The job must be dead-lettered and
    the brokerage notified to update their profile.

    Never reaches Ejar's API — no HTTP status code.
    """

    should_retry = False
    is_permanent = True

    def __init__(
        self,
        message: str,
        *,
        failed_checks: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.failed_checks: List[str] = failed_checks or []

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["failed_checks"] = self.failed_checks
        return base


# ---------------------------------------------------------------------------
# Token / Credential Errors
# ---------------------------------------------------------------------------


class EjarTokenError(EjarAPIError):
    """
    Raised when credentials cannot be resolved or decrypted for a company.

    Causes:
    - No API key configured for company
    - Token model decryption failure
    - Token marked inactive

    PERMANENT until credentials are configured.
    """

    should_retry = False
    is_permanent = True


class EjarTokenExpiredError(EjarTokenError):
    """
    Raised when a token's `expires_at` has passed.
    Separate from EjarAuthError (which is an HTTP 401 from Ejar).
    """


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------


class EjarCircuitOpenError(EjarAPIError):
    """
    Raised by the circuit breaker when it is in OPEN state.

    Ejar API has had too many consecutive failures. All requests to this
    company's Ejar endpoint are blocked until the circuit resets.

    retry_after: seconds until the circuit attempts HALF-OPEN probe.
    """

    should_retry = True   # retry AFTER retry_after seconds
    is_permanent = False

    def __init__(
        self,
        message: str,
        *,
        retry_after: int = 60,
        failure_count: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after
        self.failure_count = failure_count


# ---------------------------------------------------------------------------
# Configuration Errors
# ---------------------------------------------------------------------------


class EjarConfigurationError(EjarAPIError):
    """
    Raised when the integration cannot proceed due to missing or invalid
    Odoo configuration (not a runtime API error).

    Examples:
    - ejar.api.environment set to an unknown value
    - Required ir.config_parameter not set
    - services/ package imported without requests installed

    PERMANENT — requires administrator action.
    Alert immediately; do not enqueue for retry.
    """

    should_retry = False
    is_permanent = True


# ---------------------------------------------------------------------------
# Payload Construction Errors
# ---------------------------------------------------------------------------


class EjarPayloadError(EjarAPIError):
    """
    Raised when the Odoo-to-Ejar payload builder cannot construct a valid
    request body — e.g., a required Odoo field is null, or an enum mapping
    is missing.

    Distinct from EjarValidationError (which is a rejection from Ejar's API).
    This is caught before any HTTP call is made.

    PERMANENT — requires data correction in Odoo.
    """

    should_retry = False
    is_permanent = True

    def __init__(
        self,
        message: str,
        *,
        odoo_field: Optional[str] = None,
        odoo_model: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.odoo_field = odoo_field
        self.odoo_model = odoo_model


# ---------------------------------------------------------------------------
# Webhook / Inbound Callback Errors
# ---------------------------------------------------------------------------


class EjarWebhookError(EjarAPIError):
    """
    Base exception for webhook validation and processing errors.
    Raised by webhook validator and processor.
    """

    should_retry = False
    is_permanent = False


class EjarWebhookSignatureInvalid(EjarWebhookError):
    """
    HMAC-SHA256 signature does not match expected signature.
    Could indicate tampering or replay attack.

    PERMANENT — reject immediately, alert security team.
    """

    is_permanent = True


class EjarWebhookSignatureMissing(EjarWebhookError):
    """
    Required X-Webhook-Signature header is missing.

    PERMANENT — malformed webhook request.
    """

    is_permanent = True


class EjarWebhookTimestampMissing(EjarWebhookError):
    """
    Required X-Webhook-Timestamp header is missing.

    PERMANENT — malformed webhook request.
    """

    is_permanent = True


class EjarWebhookReplayAttack(EjarWebhookError):
    """
    Webhook timestamp is outside the acceptable window (±300 seconds).
    Could indicate a replay attack or clock skew.

    Transient — may retry if clock skew is detected and corrected.
    """

    should_retry = False
    is_permanent = False


class EjarWebhookInvalidJSON(EjarWebhookError):
    """
    Webhook payload cannot be parsed as JSON.

    PERMANENT — malformed request body.
    """

    is_permanent = True


class EjarWebhookConfigMissing(EjarWebhookError):
    """
    Webhook secret not configured for the company.

    PERMANENT until configuration is provided by administrator.
    """

    is_permanent = True


class EjarWebhookContractNotFound(EjarWebhookError):
    """
    Webhook references a contract_id that does not exist in Odoo.

    PERMANENT — indicates data sync issue or webhook sent for deleted contract.
    """

    is_permanent = True


class EjarWebhookUnknownEventType(EjarWebhookError):
    """
    Webhook event_type is not recognized or not yet implemented.

    Could indicate: new event type from Ejar, or malformed event_type field.
    Transient for now (might be implemented in future); implementation can retry
    or dead-letter based on operational policy.
    """

    should_retry = False
    is_permanent = False


class EjarWebhookIdempotencyKeyMissing(EjarWebhookError):
    """
    Webhook idempotency_key is missing (required for deduplication).

    PERMANENT — webhook validation failed.
    """

    is_permanent = True


# ---------------------------------------------------------------------------
# Helper: classify HTTP status → exception
# ---------------------------------------------------------------------------


def raise_for_ejar_status(
    http_status: int,
    response_body: Dict[str, Any],
    *,
    correlation_id: Optional[str] = None,
    company_id: Optional[int] = None,
    endpoint: Optional[str] = None,
) -> None:
    """
    Inspect an HTTP status code and raise the appropriate EjarAPIError.

    Returns None for 2xx responses (no error).
    Always raises for non-2xx.

    Usage::

        raise_for_ejar_status(
            response.status_code,
            response.json(),
            correlation_id=cid,
            company_id=company_id,
            endpoint=endpoint,
        )
    """
    if 200 <= http_status < 300:
        return

    common = dict(
        correlation_id=correlation_id,
        company_id=company_id,
        endpoint=endpoint,
        http_status=http_status,
        raw_response=response_body,
    )

    errors = response_body.get("errors", [])
    first_msg = errors[0].get("detail", "") if errors else ""
    message = first_msg or response_body.get("message", f"HTTP {http_status}")

    if http_status == 400:
        field_errors = [
            {"field": e.get("source", {}).get("pointer", ""), "detail": e.get("detail", "")}
            for e in errors
        ]
        raise EjarValidationError(message, field_errors=field_errors, **common)

    if http_status == 401:
        raise EjarAuthError(message, **common)

    if http_status == 403:
        raise EjarForbiddenError(message, **common)

    if http_status == 404:
        raise EjarNotFoundError(message, **common)

    if http_status == 409:
        existing = response_body.get("data")
        raise EjarConflictError(message, existing_resource=existing, **common)

    if http_status == 422:
        field_errors = [
            {"field": e.get("source", {}).get("pointer", ""), "detail": e.get("detail", "")}
            for e in errors
        ]
        raise EjarValidationError(message, field_errors=field_errors, **common)

    if http_status == 429:
        raise EjarRateLimitError(message, retry_after=60, **common)

    if http_status in (500, 502, 503, 504):
        ejar_code = response_body.get("error_code")
        raise EjarServerError(message, ejar_error_code=ejar_code, **common)

    # Unexpected status
    raise EjarAPIError(f"Unexpected HTTP {http_status}: {message}", **common)
