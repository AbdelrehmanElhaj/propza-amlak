import logging
import json
from uuid import uuid4

from odoo import http
from odoo.http import request

from ..services.exceptions import EjarWebhookError

_logger = logging.getLogger(__name__)


class EjarWebhookController(http.Controller):
    @http.route('/ejar/webhook', type='json', auth='none', methods=['POST'], csrf=False)
    def webhook_handler(self):
        """
        Webhook endpoint for Ejar callbacks.
        - Returns 202 Accepted immediately (async processing)
        - Validates signature + timestamp
        - Routes to processor (async via queue_job if available)

        Headers expected:
          X-Webhook-Signature: HMAC-SHA256(secret, body).hexdigest()
          X-Webhook-Timestamp: Unix timestamp (seconds)
          X-Correlation-ID: Optional correlation ID
        """
        try:
            # 1. Extract headers
            signature = request.httprequest.headers.get('X-Webhook-Signature')
            timestamp = request.httprequest.headers.get('X-Webhook-Timestamp')
            correlation_id = (
                request.httprequest.headers.get('X-Correlation-ID')
                or str(uuid4())
            )

            # 2. Get raw body for signature validation
            body_bytes = request.httprequest.get_data()

            # 3. Validate webhook (raises EjarWebhookError on invalid)
            from ..services.webhook_validator import EjarWebhookValidator

            validator = EjarWebhookValidator(request.env)
            webhook_data = validator.validate(
                signature=signature,
                timestamp=timestamp,
                body_bytes=body_bytes,
            )

            # 4. Deduplicate via idempotency key
            idempotency_key = webhook_data.get('idempotency_key')
            if idempotency_key and validator.is_duplicate(idempotency_key):
                _logger.info(
                    "Webhook duplicate (idem_key=%s), skipping", idempotency_key
                )
                return {'status': 'received'}, 202

            # 5. Queue for processing (async) or process synchronously (dev)
            from ..services.webhook_processor import EjarWebhookProcessor

            processor = EjarWebhookProcessor(request.env)

            try:
                # Try async via queue_job
                processor.with_delay(priority=15).process_webhook(
                    webhook_data=webhook_data,
                    correlation_id=correlation_id,
                )
            except (ImportError, AttributeError):
                # Fallback: sync processing if queue_job not available
                processor.process_webhook(
                    webhook_data=webhook_data,
                    correlation_id=correlation_id,
                )

            _logger.info(
                "Webhook received and queued (correlation_id=%s, event_type=%s)",
                correlation_id,
                webhook_data.get('event_type'),
            )

            # 6. Return 202 (accepted for async processing)
            return {'status': 'received', 'correlation_id': correlation_id}, 202

        except EjarWebhookError as e:
            _logger.warning("Webhook validation error: %s", e)
            return {'status': 'error', 'message': str(e)}, 400
        except Exception as e:
            _logger.exception("Webhook handler error: %s", e)
            return {'status': 'error', 'message': 'internal server error'}, 500
