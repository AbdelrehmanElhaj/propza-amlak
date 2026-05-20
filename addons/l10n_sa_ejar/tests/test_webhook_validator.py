import hmac
import hashlib
import json
import time

from odoo.tests import TransactionCase
from odoo.exceptions import ValidationError

from ..services.webhook_validator import EjarWebhookValidator
from ..services.exceptions import (
    EjarWebhookSignatureInvalid,
    EjarWebhookTimestampMissing,
    EjarWebhookSignatureMissing,
    EjarWebhookReplayAttack,
    EjarWebhookInvalidJSON,
    EjarWebhookConfigMissing,
)


class TestEjarWebhookValidator(TransactionCase):
    """Test webhook validation: signatures, timestamps, idempotency."""

    def setUp(self):
        super().setUp()
        self.validator = EjarWebhookValidator(self.env)
        self.company = self.env.company
        self.secret = 'test-webhook-secret-12345'

        # Configure webhook secret for company
        self.env['ir.config_parameter'].sudo().set_param(
            f'ejar.webhook.secret.company_{self.company.id}',
            self.secret,
        )

    def test_valid_signature(self):
        """Test webhook with valid HMAC-SHA256 signature."""
        payload = {
            'company_id': self.company.id,
            'contract_id': 1,
            'event_type': 'contract.approved',
            'idempotency_key': 'test-idem-001',
        }
        body_bytes = json.dumps(payload).encode('utf-8')
        timestamp = str(int(time.time()))
        signature = hmac.new(
            self.secret.encode('utf-8'),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()

        result = self.validator.validate(
            signature=signature,
            timestamp=timestamp,
            body_bytes=body_bytes,
        )

        self.assertEqual(result['company_id'], self.company.id)
        self.assertEqual(result['event_type'], 'contract.approved')

    def test_invalid_signature(self):
        """Test webhook with mismatched signature."""
        payload = {'company_id': self.company.id, 'event_type': 'contract.approved'}
        body_bytes = json.dumps(payload).encode('utf-8')
        timestamp = str(int(time.time()))
        invalid_sig = 'abc123invalid'

        with self.assertRaises(EjarWebhookSignatureInvalid):
            self.validator.validate(
                signature=invalid_sig,
                timestamp=timestamp,
                body_bytes=body_bytes,
            )

    def test_missing_signature(self):
        """Test webhook with missing signature header."""
        payload = {'company_id': self.company.id}
        body_bytes = json.dumps(payload).encode('utf-8')
        timestamp = str(int(time.time()))

        with self.assertRaises(EjarWebhookSignatureMissing):
            self.validator.validate(
                signature=None,
                timestamp=timestamp,
                body_bytes=body_bytes,
            )

    def test_missing_timestamp(self):
        """Test webhook with missing timestamp header."""
        payload = {'company_id': self.company.id}
        body_bytes = json.dumps(payload).encode('utf-8')
        signature = 'abc123'

        with self.assertRaises(EjarWebhookTimestampMissing):
            self.validator.validate(
                signature=signature,
                timestamp=None,
                body_bytes=body_bytes,
            )

    def test_old_timestamp(self):
        """Test webhook with timestamp outside acceptable window."""
        payload = {'company_id': self.company.id}
        body_bytes = json.dumps(payload).encode('utf-8')
        old_timestamp = str(int(time.time()) - 400)  # 400s in the past
        signature = hmac.new(
            self.secret.encode('utf-8'),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()

        with self.assertRaises(EjarWebhookReplayAttack):
            self.validator.validate(
                signature=signature,
                timestamp=old_timestamp,
                body_bytes=body_bytes,
            )

    def test_future_timestamp(self):
        """Test webhook with timestamp in the future (clock skew)."""
        payload = {'company_id': self.company.id}
        body_bytes = json.dumps(payload).encode('utf-8')
        future_timestamp = str(int(time.time()) + 400)  # 400s in the future
        signature = hmac.new(
            self.secret.encode('utf-8'),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()

        with self.assertRaises(EjarWebhookReplayAttack):
            self.validator.validate(
                signature=signature,
                timestamp=future_timestamp,
                body_bytes=body_bytes,
            )

    def test_invalid_json(self):
        """Test webhook with malformed JSON."""
        body_bytes = b'not valid json {'
        timestamp = str(int(time.time()))
        signature = hmac.new(
            self.secret.encode('utf-8'),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()

        with self.assertRaises(EjarWebhookInvalidJSON):
            self.validator.validate(
                signature=signature,
                timestamp=timestamp,
                body_bytes=body_bytes,
            )

    def test_missing_company_id(self):
        """Test webhook without company_id in payload."""
        payload = {'event_type': 'contract.approved'}
        body_bytes = json.dumps(payload).encode('utf-8')
        timestamp = str(int(time.time()))
        signature = hmac.new(
            self.secret.encode('utf-8'),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()

        with self.assertRaises(EjarWebhookConfigMissing):
            self.validator.validate(
                signature=signature,
                timestamp=timestamp,
                body_bytes=body_bytes,
            )

    def test_missing_secret_config(self):
        """Test webhook when secret is not configured."""
        other_company = self.env['res.company'].create({'name': 'Other Co'})
        payload = {
            'company_id': other_company.id,
            'event_type': 'contract.approved',
        }
        body_bytes = json.dumps(payload).encode('utf-8')
        timestamp = str(int(time.time()))
        signature = 'abc123'

        with self.assertRaises(EjarWebhookConfigMissing):
            self.validator.validate(
                signature=signature,
                timestamp=timestamp,
                body_bytes=body_bytes,
            )

    def test_is_duplicate(self):
        """Test idempotency key deduplication."""
        # Create a sync log entry
        self.env['ejar.sync.log'].log_call(
            action='webhook_test',
            contract_id=1,
            company_id=self.company.id,
            correlation_id='corr-123',
            idempotency_key='test-idem-dup',
            direction='inbound',
            http_method='POST',
            endpoint='/ejar/webhook',
            http_status=202,
            status='success',
        )

        # Check is_duplicate detects it
        is_dup = self.validator.is_duplicate('test-idem-dup')
        self.assertTrue(is_dup)

        # Non-existent key should not be duplicate
        is_dup = self.validator.is_duplicate('test-idem-not-exists')
        self.assertFalse(is_dup)
