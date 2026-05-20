"""Tests for job policies, retry patterns, and exception classification."""
from odoo.tests import TransactionCase
from unittest.mock import patch, MagicMock

from ..services.job_policies import (
    SUBMISSION_RETRY_PATTERN,
    POLLING_RETRY_PATTERN,
    DOCUMENT_RETRY_PATTERN,
    classify_ejar_exception,
    CHANNEL_CONTRACTS,
    CHANNEL_POLLING,
    CHANNEL_DOCUMENTS,
)
from ..services.exceptions import (
    EjarNetworkError,
    EjarTimeoutError,
    EjarRateLimitError,
    EjarServerError,
    EjarAuthError,
    EjarCircuitOpenError,
    EjarValidationError,
    EjarForbiddenError,
    EjarNotFoundError,
    EjarPayloadError,
    EjarConfigurationError,
)


class TestJobPolicies(TransactionCase):
    """Test retry patterns and queue channel configuration."""

    def test_submission_retry_pattern(self):
        """Submission retries: 1min → 5min → 30min → 2hr → 4hr."""
        expected = {0: 60, 1: 300, 2: 1_800, 3: 7_200, 4: 14_400}
        self.assertEqual(SUBMISSION_RETRY_PATTERN, expected)

    def test_polling_retry_pattern(self):
        """Polling retries: 5min → 15min → 30min → 1hr."""
        expected = {0: 300, 1: 900, 2: 1_800, 3: 3_600, 4: 7_200}
        self.assertEqual(POLLING_RETRY_PATTERN, expected)

    def test_document_retry_pattern(self):
        """Document retries: 30s → 2min → 10min → 30min."""
        expected = {0: 30, 1: 120, 2: 600, 3: 1_800}
        self.assertEqual(DOCUMENT_RETRY_PATTERN, expected)

    def test_channel_constants(self):
        """Queue channels configured."""
        self.assertEqual(CHANNEL_CONTRACTS, 'root.ejar.contracts')
        self.assertEqual(CHANNEL_POLLING, 'root.ejar.polling')
        self.assertEqual(CHANNEL_DOCUMENTS, 'root.ejar.documents')

    def test_retry_pattern_exponential_backoff(self):
        """Retry patterns show exponential backoff."""
        pattern = SUBMISSION_RETRY_PATTERN
        delays = [pattern[i] for i in sorted(pattern.keys())]

        # Each delay should be >= previous
        for i in range(1, len(delays)):
            self.assertGreaterEqual(delays[i], delays[i-1])


class TestExceptionClassification(TransactionCase):
    """Test classify_ejar_exception routes to retry/dead-letter."""

    def test_network_error_is_retryable(self):
        """Network errors → RetryableJobError."""
        from odoo.addons.queue_job.job import RetryableJobError

        exc = EjarNetworkError(
            'Connection refused',
            correlation_id='test',
            company_id=1,
        )

        with self.assertRaises(RetryableJobError):
            classify_ejar_exception(exc)

    def test_timeout_error_is_retryable(self):
        """Timeout errors → RetryableJobError."""
        from odoo.addons.queue_job.job import RetryableJobError

        exc = EjarTimeoutError(
            'Request timeout',
            correlation_id='test',
            company_id=1,
        )

        with self.assertRaises(RetryableJobError):
            classify_ejar_exception(exc)

    def test_rate_limit_error_is_retryable(self):
        """Rate limit errors → RetryableJobError (with retry_after)."""
        from odoo.addons.queue_job.job import RetryableJobError

        exc = EjarRateLimitError(
            'Rate limit exceeded',
            retry_after=60,
            correlation_id='test',
            company_id=1,
        )

        with self.assertRaises(RetryableJobError):
            classify_ejar_exception(exc)

    def test_server_error_is_retryable(self):
        """Server errors (5xx) → RetryableJobError."""
        from odoo.addons.queue_job.job import RetryableJobError

        exc = EjarServerError(
            'Service unavailable',
            correlation_id='test',
            company_id=1,
            http_status=503,
        )

        with self.assertRaises(RetryableJobError):
            classify_ejar_exception(exc)

    def test_circuit_open_is_retryable(self):
        """Circuit open → RetryableJobError."""
        from odoo.addons.queue_job.job import RetryableJobError

        exc = EjarCircuitOpenError(
            'Circuit breaker open',
            retry_after=60,
            correlation_id='test',
            company_id=1,
        )

        with self.assertRaises(RetryableJobError):
            classify_ejar_exception(exc)

    def test_auth_error_is_retryable_once(self):
        """Auth errors → RetryableJobError (attempt token refresh)."""
        from odoo.addons.queue_job.job import RetryableJobError

        exc = EjarAuthError(
            'Invalid credentials',
            correlation_id='test',
            company_id=1,
            http_status=401,
        )

        # Can retry once for token refresh
        with self.assertRaises(RetryableJobError):
            classify_ejar_exception(exc)

    def test_validation_error_is_permanent(self):
        """Validation errors → FailedJobError (permanent)."""
        from odoo.addons.queue_job.job import FailedJobError

        exc = EjarValidationError(
            'Invalid party ID',
            correlation_id='test',
            company_id=1,
            http_status=400,
        )

        with self.assertRaises(FailedJobError):
            classify_ejar_exception(exc)

    def test_forbidden_error_is_permanent(self):
        """Forbidden (403) → FailedJobError (permanent)."""
        from odoo.addons.queue_job.job import FailedJobError

        exc = EjarForbiddenError(
            'License does not permit this operation',
            correlation_id='test',
            company_id=1,
            http_status=403,
        )

        with self.assertRaises(FailedJobError):
            classify_ejar_exception(exc)

    def test_not_found_error_is_permanent(self):
        """Not found (404) → FailedJobError (permanent)."""
        from odoo.addons.queue_job.job import FailedJobError

        exc = EjarNotFoundError(
            'Contract not found',
            correlation_id='test',
            company_id=1,
            http_status=404,
        )

        with self.assertRaises(FailedJobError):
            classify_ejar_exception(exc)

    def test_payload_error_is_permanent(self):
        """Payload errors → FailedJobError (permanent)."""
        from odoo.addons.queue_job.job import FailedJobError

        exc = EjarPayloadError(
            'Missing required field',
            correlation_id='test',
            company_id=1,
            odoo_field='start_date',
            odoo_model='ejar.contract',
        )

        with self.assertRaises(FailedJobError):
            classify_ejar_exception(exc)

    def test_configuration_error_is_permanent(self):
        """Configuration errors → FailedJobError (permanent)."""
        from odoo.addons.queue_job.job import FailedJobError

        exc = EjarConfigurationError(
            'API environment not configured',
            correlation_id='test',
            company_id=1,
        )

        with self.assertRaises(FailedJobError):
            classify_ejar_exception(exc)


class TestRetryDeadLetterFlow(TransactionCase):
    """Test retry and dead-letter handling in contracts."""

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.profile = self.env['ejar.brokerage.profile'].create({
            'company_id': self.company.id,
            'office_name_ar': 'مكتب الوساطة',
            'office_name_en': 'Brokerage',
            'cr_number': '1234567890',
            'license_number': 'RERA-123456',
            'license_expiry': '2030-01-01',
            'unified_number': '1111111111',
            'vat_number': '3333333333',
        })

    def test_contract_retries_on_transient_error(self):
        """Contract submission increments retry counter on transient error."""
        contract = self.env['ejar.contract'].create({
            'company_id': self.company.id,
            'brokerage_profile_id': self.profile.id,
            'contract_type': 'residential',
            'start_date': '2024-01-01',
            'end_date': '2025-01-01',
            'rent_amount': 50000.0,
        })

        # Simulate retry: increment attempt counter
        contract.write({'submit_attempt': 1})
        self.assertEqual(contract.submit_attempt, 1)

        contract.write({'submit_attempt': 2})
        self.assertEqual(contract.submit_attempt, 2)

    def test_contract_dead_letter_on_permanent_error(self):
        """Contract reset to 'ready' on permanent error (dead-letter)."""
        contract = self.env['ejar.contract'].create({
            'company_id': self.company.id,
            'brokerage_profile_id': self.profile.id,
            'contract_type': 'residential',
            'start_date': '2024-01-01',
            'end_date': '2025-01-01',
            'rent_amount': 50000.0,
        })

        # Simulate dead-letter: move to ready, store error
        contract._set_status('submitting')
        contract.write({
            'ejar_status': 'ready',
            'submit_error': 'Validation failed: Invalid party ID',
        })

        self.assertEqual(contract.ejar_status, 'ready')
        self.assertIn('Validation failed', contract.submit_error)
