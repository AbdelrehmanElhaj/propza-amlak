"""
l10n_sa_ejar.services — Ejar ECRS API service layer
=====================================================
Public surface:

    EjarApiClient                — HTTP gateway (one instance per company per request)
    EjarAuthService              — Per-company credential resolver
    EjarCredentials              — Immutable credential value object
    EjarWebhookValidator         — Webhook request validation (signature, replay, idempotency)
    EjarWebhookProcessor         — Webhook event processing and routing

All exceptions are importable from .exceptions directly:

    from odoo.addons.l10n_sa_ejar.services.exceptions import (
        EjarAPIError,
        EjarValidationError,
        EjarConflictError,
        EjarWebhookSignatureInvalid,
        ...
    )
"""

from .auth_service import EjarAuthService, EjarCredentials
from .ejar_client import EjarApiClient
from .payload_builder import EjarPayloadBuilder
from .lifecycle_service import EjarContractLifecycleService
from .webhook_validator import EjarWebhookValidator
from .webhook_processor import EjarWebhookProcessor
from .job_policies import (
    CHANNEL_CONTRACTS,
    CHANNEL_DOCUMENTS,
    CHANNEL_POLLING,
    SUBMISSION_RETRY_PATTERN,
    POLLING_RETRY_PATTERN,
    DOCUMENT_RETRY_PATTERN,
    classify_ejar_exception,
)
from . import constants
from . import exceptions

__all__ = [
    "EjarApiClient",
    "EjarAuthService",
    "EjarCredentials",
    "EjarPayloadBuilder",
    "EjarContractLifecycleService",
    "EjarWebhookValidator",
    "EjarWebhookProcessor",
    # Job policies
    "CHANNEL_CONTRACTS",
    "CHANNEL_DOCUMENTS",
    "CHANNEL_POLLING",
    "SUBMISSION_RETRY_PATTERN",
    "POLLING_RETRY_PATTERN",
    "DOCUMENT_RETRY_PATTERN",
    "classify_ejar_exception",
    # Sub-modules
    "constants",
    "exceptions",
]
