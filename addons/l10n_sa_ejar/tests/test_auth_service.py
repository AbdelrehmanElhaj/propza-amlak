"""Unit tests for EjarAuthService and credential management."""
import time
from unittest.mock import patch, MagicMock

from odoo.tests import TransactionCase
from odoo import fields

from ..services.auth_service import EjarAuthService, EjarCredentials, _CredentialCache
from ..services.exceptions import EjarTokenError, EjarTokenExpiredError


class TestEjarCredentials(TransactionCase):
    """Test EjarCredentials immutable dataclass."""

    def test_credentials_frozen(self):
        """Credentials are immutable (dataclass frozen=True)."""
        creds = EjarCredentials(api_key='key123', api_secret_key='secret456')
        with self.assertRaises((AttributeError, TypeError)):
            creds.api_key = 'modified'

    def test_credentials_fingerprint(self):
        """Fingerprint is SHA-256[:12] hash."""
        creds = EjarCredentials(api_key='key123', api_secret_key='secret456')
        self.assertEqual(len(creds.fingerprint), 12)
        self.assertIsInstance(creds.fingerprint, str)
        # Should be consistent
        creds2 = EjarCredentials(api_key='key123', api_secret_key='secret456')
        self.assertEqual(creds.fingerprint, creds2.fingerprint)

    def test_credentials_to_auth_header(self):
        """Generate Basic auth header (Base64)."""
        creds = EjarCredentials(api_key='user', api_secret_key='pass')
        header = creds.to_auth_header()
        self.assertTrue(header.startswith('Basic '))
        # Decode and verify
        import base64
        decoded = base64.b64decode(header.replace('Basic ', '')).decode()
        self.assertEqual(decoded, 'user:pass')

    def test_credentials_repr_safe(self):
        """__repr__ and __str__ don't expose credentials."""
        creds = EjarCredentials(api_key='secret_key_123', api_secret_key='secret_pass_456')
        repr_str = repr(creds)
        str_str = str(creds)
        self.assertNotIn('secret_key_123', repr_str)
        self.assertNotIn('secret_pass_456', repr_str)
        self.assertNotIn('secret_key_123', str_str)
        self.assertNotIn('secret_pass_456', str_str)


class TestCredentialCache(TransactionCase):
    """Test _CredentialCache TTL and thread-safety."""

    def test_cache_hit(self):
        """Cache returns same credentials within TTL."""
        cache = _CredentialCache()
        creds1 = EjarCredentials(api_key='key1', api_secret_key='secret1')

        cache.get_or_set(
            company_id=1,
            value_fn=lambda: creds1,
            ttl=300,
        )

        creds2 = cache.get_or_set(
            company_id=1,
            value_fn=lambda: EjarCredentials(api_key='key2', api_secret_key='secret2'),
            ttl=300,
        )

        # Should be same object (cache hit)
        self.assertEqual(creds1.api_key, creds2.api_key)

    def test_cache_expiry(self):
        """Cache expires after TTL."""
        cache = _CredentialCache()
        call_count = 0

        def value_fn():
            nonlocal call_count
            call_count += 1
            return EjarCredentials(api_key=f'key{call_count}', api_secret_key='secret')

        # First call
        creds1 = cache.get_or_set(company_id=1, value_fn=value_fn, ttl=1)
        self.assertEqual(call_count, 1)

        # Within TTL — cache hit
        creds2 = cache.get_or_set(company_id=1, value_fn=value_fn, ttl=1)
        self.assertEqual(call_count, 1)

        # After TTL — cache miss
        time.sleep(1.1)
        creds3 = cache.get_or_set(company_id=1, value_fn=value_fn, ttl=1)
        self.assertEqual(call_count, 2)

    def test_cache_invalidate(self):
        """Can invalidate cache for specific company."""
        cache = _CredentialCache()
        call_count = 0

        def value_fn():
            nonlocal call_count
            call_count += 1
            return EjarCredentials(api_key=f'key{call_count}', api_secret_key='secret')

        # Set cache
        cache.get_or_set(company_id=1, value_fn=value_fn, ttl=300)
        self.assertEqual(call_count, 1)

        # Invalidate
        cache.invalidate(company_id=1)

        # Next call should fetch again
        cache.get_or_set(company_id=1, value_fn=value_fn, ttl=300)
        self.assertEqual(call_count, 2)


class TestEjarAuthService(TransactionCase):
    """Test credential resolution and fallback chain."""

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.auth_service = EjarAuthService(self.env)

    def test_resolve_from_propza_token_model(self):
        """Prefer propza.ejar.api.token model if exists."""
        # Create token model entry (if exists)
        token_model = self.env.get('propza.ejar.api.token')
        if token_model is not None:
            self.env['propza.ejar.api.token'].create({
                'company_id': self.company.id,
                'api_key_encrypted': 'encrypted_key',
                'api_secret_encrypted': 'encrypted_secret',
                'is_active': True,
            })

    def test_resolve_from_config_parameter_company_scoped(self):
        """Use company-scoped ir.config_parameter."""
        self.env['ir.config_parameter'].sudo().set_param(
            f'ejar.api.key.company_{self.company.id}',
            'company_key_123',
        )
        self.env['ir.config_parameter'].sudo().set_param(
            f'ejar.api.secret.company_{self.company.id}',
            'company_secret_456',
        )

        creds = self.auth_service.resolve_credentials(self.company.id)
        self.assertEqual(creds.api_key, 'company_key_123')
        self.assertEqual(creds.api_secret_key, 'company_secret_456')

    def test_resolve_from_global_fallback(self):
        """Fall back to global config parameters."""
        self.env['ir.config_parameter'].sudo().set_param(
            'ejar.api.key',
            'global_key_789',
        )
        self.env['ir.config_parameter'].sudo().set_param(
            'ejar.api.secret',
            'global_secret_012',
        )

        creds = self.auth_service.resolve_credentials(self.company.id)
        self.assertEqual(creds.api_key, 'global_key_789')
        self.assertEqual(creds.api_secret_key, 'global_secret_012')

    def test_resolve_raises_on_missing_credentials(self):
        """Raise EjarTokenError if no credentials found."""
        with self.assertRaises(EjarTokenError):
            self.auth_service.resolve_credentials(self.company.id)

    def test_cache_invalidation_static_method(self):
        """Static method invalidates cache for company."""
        # Set credentials
        self.env['ir.config_parameter'].sudo().set_param(
            f'ejar.api.key.company_{self.company.id}',
            'key_v1',
        )
        self.env['ir.config_parameter'].sudo().set_param(
            f'ejar.api.secret.company_{self.company.id}',
            'secret_v1',
        )

        creds1 = self.auth_service.resolve_credentials(self.company.id)

        # Update credentials
        self.env['ir.config_parameter'].sudo().set_param(
            f'ejar.api.key.company_{self.company.id}',
            'key_v2',
        )

        # Without invalidation — cache returns old
        creds2 = self.auth_service.resolve_credentials(self.company.id)
        self.assertEqual(creds2.api_key, 'key_v1')

        # After invalidation — cache returns new
        EjarAuthService.invalidate_cache(self.company.id)
        creds3 = self.auth_service.resolve_credentials(self.company.id)
        self.assertEqual(creds3.api_key, 'key_v2')

    def test_multi_company_isolation(self):
        """Credentials don't leak between companies."""
        company2 = self.env['res.company'].create({'name': 'Company 2'})

        self.env['ir.config_parameter'].sudo().set_param(
            f'ejar.api.key.company_{self.company.id}',
            'company1_key',
        )
        self.env['ir.config_parameter'].sudo().set_param(
            f'ejar.api.secret.company_{self.company.id}',
            'company1_secret',
        )

        self.env['ir.config_parameter'].sudo().set_param(
            f'ejar.api.key.company_{company2.id}',
            'company2_key',
        )
        self.env['ir.config_parameter'].sudo().set_param(
            f'ejar.api.secret.company_{company2.id}',
            'company2_secret',
        )

        creds1 = self.auth_service.resolve_credentials(self.company.id)
        creds2 = self.auth_service.resolve_credentials(company2.id)

        self.assertEqual(creds1.api_key, 'company1_key')
        self.assertEqual(creds2.api_key, 'company2_key')
