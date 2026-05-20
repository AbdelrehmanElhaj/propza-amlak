"""Mocked API tests for EjarApiClient HTTP layer."""
from unittest.mock import patch, MagicMock, Mock
import json

from odoo.tests import TransactionCase
from odoo import fields

from ..services.ejar_client import EjarApiClient
from ..services.exceptions import (
    EjarNetworkError,
    EjarTimeoutError,
    EjarAuthError,
    EjarValidationError,
    EjarServerError,
    EjarRateLimitError,
    EjarConflictError,
    EjarNotFoundError,
    EjarCircuitOpenError,
)


class TestEjarApiClientMocked(TransactionCase):
    """Test EjarApiClient with mocked HTTP responses."""

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.client = EjarApiClient(self.env, company_id=self.company.id)

        # Configure credentials
        self.env['ir.config_parameter'].sudo().set_param(
            f'ejar.api.key.company_{self.company.id}',
            'test_key',
        )
        self.env['ir.config_parameter'].sudo().set_param(
            f'ejar.api.secret.company_{self.company.id}',
            'test_secret',
        )

    @patch('odoo.addons.l10n_sa_ejar.services.ejar_client.requests.Session')
    def test_create_contract_success(self, mock_session_class):
        """Successful contract creation."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'data': {
                'contract_id': 'contract-uuid-123',
                'contract_number': 'EJAR-2024-001',
            }
        }
        mock_session.post.return_value = mock_response

        client = EjarApiClient(self.env, company_id=self.company.id)
        result = client.create_contract({
            'contract_attributes': {},
            'parties': [],
            'units': [],
        })

        self.assertEqual(result['contract_id'], 'contract-uuid-123')
        self.assertTrue(mock_session.post.called)

    @patch('odoo.addons.l10n_sa_ejar.services.ejar_client.requests.Session')
    def test_http_400_validation_error(self, mock_session_class):
        """HTTP 400 raises EjarValidationError."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            'errors': [
                {
                    'detail': 'Invalid party ID format',
                    'source': {'pointer': '/data/parties/0/id_number'},
                }
            ],
            'message': 'Validation failed',
        }
        mock_session.post.return_value = mock_response

        client = EjarApiClient(self.env, company_id=self.company.id)

        with self.assertRaises(EjarValidationError) as cm:
            client.create_contract({})

        exc = cm.exception
        self.assertEqual(exc.http_status, 400)
        self.assertTrue(len(exc.field_errors) > 0)

    @patch('odoo.addons.l10n_sa_ejar.services.ejar_client.requests.Session')
    def test_http_401_auth_error(self, mock_session_class):
        """HTTP 401 raises EjarAuthError."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {
            'message': 'Invalid credentials',
        }
        mock_session.post.return_value = mock_response

        client = EjarApiClient(self.env, company_id=self.company.id)

        with self.assertRaises(EjarAuthError):
            client.create_contract({})

    @patch('odoo.addons.l10n_sa_ejar.services.ejar_client.requests.Session')
    def test_http_404_not_found(self, mock_session_class):
        """HTTP 404 raises EjarNotFoundError."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {
            'message': 'Contract not found',
        }
        mock_session.post.return_value = mock_response

        client = EjarApiClient(self.env, company_id=self.company.id)

        with self.assertRaises(EjarNotFoundError):
            client.get_contract('non-existent-uuid')

    @patch('odoo.addons.l10n_sa_ejar.services.ejar_client.requests.Session')
    def test_http_409_conflict_idempotency(self, mock_session_class):
        """HTTP 409 raises EjarConflictError (not error, idempotency)."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_response.json.return_value = {
            'message': 'Contract already exists',
            'data': {'contract_id': 'existing-uuid-123'},
        }
        mock_session.post.return_value = mock_response

        client = EjarApiClient(self.env, company_id=self.company.id)

        with self.assertRaises(EjarConflictError) as cm:
            client.create_contract({})

        exc = cm.exception
        self.assertEqual(exc.http_status, 409)
        self.assertEqual(exc.existing_resource['contract_id'], 'existing-uuid-123')

    @patch('odoo.addons.l10n_sa_ejar.services.ejar_client.requests.Session')
    def test_http_429_rate_limit(self, mock_session_class):
        """HTTP 429 raises EjarRateLimitError with retry_after."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.json.return_value = {
            'message': 'Rate limit exceeded',
        }
        mock_session.post.return_value = mock_response

        client = EjarApiClient(self.env, company_id=self.company.id)

        with self.assertRaises(EjarRateLimitError) as cm:
            client.create_contract({})

        exc = cm.exception
        self.assertEqual(exc.http_status, 429)
        self.assertGreater(exc.retry_after, 0)

    @patch('odoo.addons.l10n_sa_ejar.services.ejar_client.requests.Session')
    def test_http_500_server_error(self, mock_session_class):
        """HTTP 500+ raises EjarServerError (transient)."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.json.return_value = {
            'message': 'Service unavailable',
        }
        mock_session.post.return_value = mock_response

        client = EjarApiClient(self.env, company_id=self.company.id)

        with self.assertRaises(EjarServerError) as cm:
            client.create_contract({})

        exc = cm.exception
        self.assertEqual(exc.http_status, 503)
        self.assertTrue(exc.should_retry)

    @patch('odoo.addons.l10n_sa_ejar.services.ejar_client.requests.Session')
    def test_network_error_timeout(self, mock_session_class):
        """Network timeout raises EjarTimeoutError."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        import requests
        mock_session.post.side_effect = requests.Timeout('Connection timed out')

        client = EjarApiClient(self.env, company_id=self.company.id)

        with self.assertRaises(EjarTimeoutError):
            client.create_contract({})

    @patch('odoo.addons.l10n_sa_ejar.services.ejar_client.requests.Session')
    def test_network_error_connection_refused(self, mock_session_class):
        """Connection refused raises EjarNetworkError."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        import requests
        mock_session.post.side_effect = requests.ConnectionError('Connection refused')

        client = EjarApiClient(self.env, company_id=self.company.id)

        with self.assertRaises(EjarNetworkError):
            client.create_contract({})

    @patch('odoo.addons.l10n_sa_ejar.services.ejar_client.requests.Session')
    def test_idempotency_key_header(self, mock_session_class):
        """Idempotency-Key header sent on POST."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {'data': {'contract_id': 'uuid'}}
        mock_session.post.return_value = mock_response

        client = EjarApiClient(self.env, company_id=self.company.id)
        client.create_contract({}, idempotency_key='idem-key-123')

        # Verify header sent
        call_args = mock_session.post.call_args
        self.assertIn('headers', call_args.kwargs)
        self.assertIn('X-Idempotency-Key', call_args.kwargs['headers'])
        self.assertEqual(
            call_args.kwargs['headers']['X-Idempotency-Key'],
            'idem-key-123',
        )

    @patch('odoo.addons.l10n_sa_ejar.services.ejar_client.requests.Session')
    def test_correlation_id_propagation(self, mock_session_class):
        """Correlation-ID header sent and logged."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {'data': {'contract_id': 'uuid'}}
        mock_session.post.return_value = mock_response

        client = EjarApiClient(self.env, company_id=self.company.id)
        client.create_contract({})

        # Verify Correlation-ID header sent
        call_args = mock_session.post.call_args
        self.assertIn('X-Correlation-ID', call_args.kwargs['headers'])


class TestEjarApiClientCircuitBreaker(TransactionCase):
    """Test circuit breaker: CLOSED → OPEN → HALF_OPEN → CLOSED."""

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.env['ir.config_parameter'].sudo().set_param(
            f'ejar.api.key.company_{self.company.id}',
            'test_key',
        )
        self.env['ir.config_parameter'].sudo().set_param(
            f'ejar.api.secret.company_{self.company.id}',
            'test_secret',
        )

    @patch('odoo.addons.l10n_sa_ejar.services.ejar_client.requests.Session')
    def test_circuit_breaker_opens_after_failures(self, mock_session_class):
        """Circuit breaker opens after 5 consecutive failures."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.json.return_value = {'message': 'Service unavailable'}
        mock_session.post.return_value = mock_response

        client = EjarApiClient(self.env, company_id=self.company.id)

        # Trigger 5 failures
        for _ in range(5):
            with self.assertRaises(EjarServerError):
                client.create_contract({})

        # 6th call should be blocked by circuit breaker (OPEN state)
        with self.assertRaises(EjarCircuitOpenError):
            client.create_contract({})

    @patch('odoo.addons.l10n_sa_ejar.services.ejar_client.requests.Session')
    def test_circuit_breaker_success_resets(self, mock_session_class):
        """Successful request resets circuit breaker to CLOSED."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        # First 5 responses: fail
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 503
        mock_response_fail.json.return_value = {'message': 'Service unavailable'}

        # 6th response: success
        mock_response_ok = MagicMock()
        mock_response_ok.status_code = 201
        mock_response_ok.json.return_value = {'data': {'contract_id': 'uuid'}}

        mock_session.post.side_effect = (
            [mock_response_fail] * 5 +
            [mock_response_ok]
        )

        client = EjarApiClient(self.env, company_id=self.company.id)

        # Trigger 5 failures
        for _ in range(5):
            with self.assertRaises(EjarServerError):
                client.create_contract({})

        # Reset sequence
        mock_session.post.side_effect = None
        mock_session.post.return_value = mock_response_ok

        # Next call succeeds (transitions to HALF_OPEN → CLOSED)
        result = client.create_contract({})
        self.assertEqual(result['contract_id'], 'uuid')
