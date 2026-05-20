import hmac
import hashlib
import json
import time
import logging
from datetime import timedelta

from odoo import fields

from .exceptions import (
    EjarWebhookError,
    EjarWebhookSignatureInvalid,
    EjarWebhookTimestampMissing,
    EjarWebhookSignatureMissing,
    EjarWebhookReplayAttack,
    EjarWebhookInvalidJSON,
    EjarWebhookConfigMissing,
)

_logger = logging.getLogger(__name__)

TIMESTAMP_WINDOW_SECONDS = 300  # ±5 minutes


class EjarWebhookValidator:
    """
    Validates webhook requests from Ejar:
    1. Checks timestamp (within ±300 seconds)
    2. Validates HMAC-SHA256 signature
    3. Parses JSON payload
    4. Deduplicates via idempotency key
    """

    def __init__(self, env):
        self._env = env
        self._timestamp_window = TIMESTAMP_WINDOW_SECONDS

    def validate(self, *, signature, timestamp, body_bytes, company_id=None):
        """
        Validate webhook request. Returns validated data dict on success.
        Raises EjarWebhookError subclass on validation failure.

        Args:
            signature: X-Webhook-Signature header value (hex string)
            timestamp: X-Webhook-Timestamp header value (Unix timestamp as string)
            body_bytes: Raw request body (bytes)
            company_id: Optional override for company_id lookup

        Returns:
            dict: Validated webhook payload with _validated_at and _timestamp keys
        """
        # Step 1: Validate timestamp presence and window
        if not timestamp:
            raise EjarWebhookTimestampMissing(
                'Missing X-Webhook-Timestamp header'
            )

        try:
            request_time = int(timestamp)
        except (ValueError, TypeError):
            raise EjarWebhookTimestampMissing(
                f'Invalid X-Webhook-Timestamp format: {timestamp}'
            )

        now = int(time.time())
        delta = abs(now - request_time)

        if delta > self._timestamp_window:
            raise EjarWebhookReplayAttack(
                f'Timestamp outside window: {delta}s delta (max {self._timestamp_window}s)'
            )

        # Step 2: Parse JSON to determine company_id
        if not body_bytes:
            raise EjarWebhookInvalidJSON('Empty request body')

        try:
            webhook_dict = json.loads(body_bytes.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise EjarWebhookInvalidJSON(f'Failed to parse JSON: {e}')

        company_id = company_id or webhook_dict.get('company_id')
        if not company_id:
            raise EjarWebhookConfigMissing('Missing company_id in payload')

        # Step 3: Validate signature presence
        if not signature:
            raise EjarWebhookSignatureMissing(
                'Missing X-Webhook-Signature header'
            )

        # Step 4: Get webhook secret from config
        secret = (
            self._env['ir.config_parameter']
            .sudo()
            .get_param(f'ejar.webhook.secret.company_{company_id}')
        )

        if not secret:
            _logger.warning(
                'Webhook secret not configured for company_id=%s', company_id
            )
            raise EjarWebhookConfigMissing(
                f'Webhook secret not configured for company {company_id}'
            )

        # Step 5: Compute expected signature
        expected_sig = hmac.new(
            secret.encode('utf-8'), body_bytes, hashlib.sha256
        ).hexdigest()

        # Step 6: Constant-time comparison
        if not hmac.compare_digest(signature, expected_sig):
            _logger.warning(
                'Webhook signature mismatch (company_id=%s)', company_id
            )
            raise EjarWebhookSignatureInvalid('Signature mismatch')

        # Step 7: Return validated data with metadata
        webhook_dict['_validated_at'] = now
        webhook_dict['_timestamp'] = request_time
        webhook_dict['_company_id'] = company_id

        _logger.info(
            'Webhook validated (company_id=%s, event_type=%s)',
            company_id,
            webhook_dict.get('event_type'),
        )

        return webhook_dict

    def is_duplicate(self, idempotency_key):
        """
        Check if idempotency_key has been processed in the last 24 hours.
        Returns True if duplicate, False otherwise.
        """
        if not idempotency_key:
            return False

        cutoff_time = fields.Datetime.now() - timedelta(hours=24)

        found = self._env['ejar.sync.log'].search_count(
            [
                ('idempotency_key', '=', idempotency_key),
                ('create_date', '>=', cutoff_time),
            ]
        )

        return found > 0
