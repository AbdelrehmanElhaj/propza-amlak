import json
import logging

from odoo import fields, _
from odoo.exceptions import UserError

from .exceptions import (
    EjarWebhookError,
    EjarWebhookContractNotFound,
    EjarWebhookUnknownEventType,
)
from .job_policies import CHANNEL_POLLING, POLLING_RETRY_PATTERN

try:
    from odoo.addons.queue_job.job import job
except ImportError:
    def job(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

_logger = logging.getLogger(__name__)


class EjarWebhookProcessor:
    """
    Processes webhook events from Ejar.
    Handles: contract.approved, contract.rejected, acknowledgement.completed,
             document.verification, status.update
    """

    def __init__(self, env):
        self._env = env

    @job(channel=CHANNEL_POLLING, retry_pattern=POLLING_RETRY_PATTERN)
    def process_webhook(self, *, webhook_data, correlation_id):
        """
        Main webhook entry point. Routes to handler based on event_type.

        Args:
            webhook_data (dict): Validated webhook payload
            correlation_id (str): Correlation ID for tracing
        """
        event_type = webhook_data.get('event_type')
        company_id = webhook_data.get('_company_id')
        contract_id = webhook_data.get('contract_id')
        idempotency_key = webhook_data.get('idempotency_key')

        try:
            # 1. Log webhook receipt
            self._env['ejar.sync.log'].log_call(
                action=f'webhook_{event_type}',
                contract_id=contract_id,
                company_id=company_id,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                direction='inbound',
                http_method='POST',
                endpoint='/ejar/webhook',
                http_status=202,
                status='pending',
                request_body=self._sanitize_json(webhook_data),
            )

            # 2. Get contract
            contract = self._env['ejar.contract'].browse(contract_id)
            if not contract.exists():
                raise EjarWebhookContractNotFound(
                    f'Contract {contract_id} not found'
                )

            # 3. Route to handler
            handler_map = {
                'contract.approved': self._handle_contract_approved,
                'contract.rejected': self._handle_contract_rejected,
                'acknowledgement.completed': (
                    self._handle_acknowledgement_completed
                ),
                'document.verification': self._handle_document_verification,
                'status.update': self._handle_status_update,
            }

            handler = handler_map.get(event_type)
            if not handler:
                raise EjarWebhookUnknownEventType(f'Unknown event: {event_type}')

            # 4. Process event
            handler(contract, webhook_data, correlation_id)

            # 5. Update webhook tracking
            contract.sudo().write(
                {
                    'webhook_uuid': webhook_data.get('webhook_id'),
                    'webhook_delivered_at': fields.Datetime.now(),
                    'webhook_event_type': event_type,
                    'webhook_correlation_id': correlation_id,
                }
            )

            # 6. Log success
            sync_log = self._env['ejar.sync.log'].search(
                [
                    ('correlation_id', '=', correlation_id),
                    ('action', '=', f'webhook_{event_type}'),
                ],
                limit=1,
            )
            if sync_log:
                sync_log.sudo().write({'status': 'success'})

            _logger.info(
                'Webhook processed (correlation_id=%s, event_type=%s, '
                'contract_id=%s)',
                correlation_id,
                event_type,
                contract_id,
            )

        except EjarWebhookError as e:
            _logger.warning('Webhook processing error: %s', e)
            sync_log = self._env['ejar.sync.log'].search(
                [('correlation_id', '=', correlation_id)], limit=1
            )
            if sync_log:
                sync_log.sudo().write(
                    {
                        'status': 'error',
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'is_permanent_error': getattr(e, 'is_permanent', False),
                    }
                )
            raise

    def _handle_contract_approved(self, contract, webhook_data, correlation_id):
        """Event: contract.approved → update status to 'approved'"""
        contract_number = webhook_data.get('ejar_contract_number')

        # Update status (bypasses constraint for webhook updates)
        contract.sudo().write(
            {
                'ejar_status': 'approved',
                'ejar_contract_number': contract_number,
            }
        )

        # Post chatter
        msg_body = _('تم الموافقة على العقد من قِبل منصة إيجار')
        if contract_number:
            msg_body += f'\n{_("رقم العقد")}: {contract_number}'

        contract.message_post(body=msg_body)

        _logger.info(
            'Contract approved via webhook (contract_id=%s, '
            'ejar_contract_number=%s)',
            contract.id,
            contract_number,
        )

    def _handle_contract_rejected(self, contract, webhook_data, correlation_id):
        """Event: contract.rejected → update status to 'rejected'"""
        reason = webhook_data.get('reason', '')

        contract.sudo().write(
            {
                'ejar_status': 'rejected',
                'rejection_reason': reason,
            }
        )

        msg_body = _('تم رفض العقد من قِبل منصة إيجار')
        if reason:
            msg_body += f'\n{_("السبب")}: {reason}'

        contract.message_post(body=msg_body)

        _logger.info(
            'Contract rejected via webhook (contract_id=%s, reason=%s)',
            contract.id,
            reason,
        )

    def _handle_acknowledgement_completed(
        self, contract, webhook_data, correlation_id
    ):
        """Event: acknowledgement.completed → mark parties as synced"""
        parties_data = webhook_data.get('parties', [])

        for party_data in parties_data:
            ejar_party_id = party_data.get('ejar_party_id')
            party = contract.party_ids.filtered(
                lambda p: p.ejar_party_id == ejar_party_id
            )
            if party:
                party.sudo().write({'sync_state': 'synced'})

        msg_body = _('تم التحقق من أطراف العقد')
        if parties_data:
            msg_body += f' ({len(parties_data)} أطراف)'

        contract.message_post(body=msg_body)

        _logger.info(
            'Acknowledgement completed for contract_id=%s, parties=%d',
            contract.id,
            len(parties_data),
        )

    def _handle_document_verification(self, contract, webhook_data, correlation_id):
        """Event: document.verification → update doc verification state"""
        doc_type = webhook_data.get('document_type', 'unknown')
        verified = webhook_data.get('verified', False)

        status_text = _('تم التحقق من') if verified else _('تم رفض')
        msg_body = f'{status_text} {_("المستند")}: {doc_type}'

        contract.message_post(body=msg_body)

        _logger.info(
            'Document verification webhook (contract_id=%s, doc_type=%s, '
            'verified=%s)',
            contract.id,
            doc_type,
            verified,
        )

    def _handle_status_update(self, contract, webhook_data, correlation_id):
        """Event: status.update → general status synchronization"""
        new_status = webhook_data.get('ejar_status')

        msg_body = _('تحديث حالة العقد من إيجار')
        if new_status:
            msg_body += f': {new_status}'

        contract.message_post(body=msg_body)

        _logger.info(
            'Status update webhook (contract_id=%s, new_status=%s)',
            contract.id,
            new_status,
        )

    @staticmethod
    def _sanitize_json(data):
        """
        Sanitize sensitive fields before logging.
        Returns JSON string with sensitive data removed.
        """
        from .constants import SENSITIVE_FIELDS

        sanitized = {}
        for key, value in data.items():
            if key in SENSITIVE_FIELDS or key.endswith('_key'):
                sanitized[key] = '***REDACTED***'
            elif isinstance(value, dict):
                sanitized[key] = EjarWebhookProcessor._sanitize_json(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    (
                        EjarWebhookProcessor._sanitize_json(item)
                        if isinstance(item, dict)
                        else item
                    )
                    for item in value
                ]
            else:
                sanitized[key] = value

        return json.dumps(sanitized)[:65536]
