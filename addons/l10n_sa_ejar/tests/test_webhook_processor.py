import json
from odoo.tests import TransactionCase
from odoo import fields, _


class TestEjarWebhookProcessor(TransactionCase):
    """Test webhook event processing and contract state transitions."""

    def setUp(self):
        super().setUp()

        # Create company and brokerage profile
        self.company = self.env.company
        self.profile = self.env['ejar.brokerage.profile'].create({
            'company_id': self.company.id,
            'office_name_ar': 'مكتب الوساطة',
            'office_name_en': 'Brokerage Office',
            'cr_number': '1234567890',
            'license_number': 'RERA-123456',
            'license_expiry': fields.Date.today().replace(year=fields.Date.today().year + 1),
            'unified_number': '1111111111',
            'vat_number': '3333333333',
        })

        # Create contract in 'submitted' state
        self.contract = self.env['ejar.contract'].create({
            'company_id': self.company.id,
            'brokerage_profile_id': self.profile.id,
            'ejar_status': 'submitted',
            'contract_type': 'residential',
            'start_date': fields.Date.today(),
            'end_date': fields.Date.today().replace(year=fields.Date.today().year + 1),
            'rent_amount': 50000.0,
            'ejar_contract_id': 'ejar-uuid-123',
        })

    def test_webhook_contract_approved(self):
        """Test webhook event: contract.approved."""
        webhook_data = {
            '_company_id': self.company.id,
            'contract_id': self.contract.id,
            'event_type': 'contract.approved',
            'webhook_id': 'webhook-uuid-1',
            'ejar_contract_number': 'EJAR-2024-001',
            'idempotency_key': 'test-idem-approved-001',
        }

        from ..services.webhook_processor import EjarWebhookProcessor

        processor = EjarWebhookProcessor(self.env)
        processor.process_webhook(
            webhook_data=webhook_data,
            correlation_id='corr-123',
        )

        # Refresh contract
        self.contract.invalidate_cache()

        # Verify state transition
        self.assertEqual(self.contract.ejar_status, 'approved')
        self.assertEqual(self.contract.ejar_contract_number, 'EJAR-2024-001')
        self.assertEqual(self.contract.webhook_uuid, 'webhook-uuid-1')
        self.assertEqual(self.contract.webhook_event_type, 'contract.approved')

        # Verify chatter message
        messages = self.contract.message_ids
        self.assertTrue(any('موافق عليه' in m.body for m in messages))

    def test_webhook_contract_rejected(self):
        """Test webhook event: contract.rejected."""
        webhook_data = {
            '_company_id': self.company.id,
            'contract_id': self.contract.id,
            'event_type': 'contract.rejected',
            'webhook_id': 'webhook-uuid-2',
            'reason': 'Invalid party ID format',
            'idempotency_key': 'test-idem-rejected-001',
        }

        from ..services.webhook_processor import EjarWebhookProcessor

        processor = EjarWebhookProcessor(self.env)
        processor.process_webhook(
            webhook_data=webhook_data,
            correlation_id='corr-456',
        )

        # Refresh contract
        self.contract.invalidate_cache()

        # Verify state transition
        self.assertEqual(self.contract.ejar_status, 'rejected')
        self.assertEqual(self.contract.rejection_reason, 'Invalid party ID format')

        # Verify chatter message
        messages = self.contract.message_ids
        self.assertTrue(any('رفض' in m.body for m in messages))

    def test_webhook_acknowledgement_completed(self):
        """Test webhook event: acknowledgement.completed."""
        # Create parties
        lessor = self.env['ejar.contract.party'].create({
            'contract_id': self.contract.id,
            'role': 'lessor',
            'entity_type': 'individual',
            'id_type': 'national_id',
            'id_number': '1234567890',
            'ejar_party_id': 'ejar-party-lessor-1',
        })
        tenant = self.env['ejar.contract.party'].create({
            'contract_id': self.contract.id,
            'role': 'tenant',
            'entity_type': 'individual',
            'id_type': 'national_id',
            'id_number': '9876543210',
            'ejar_party_id': 'ejar-party-tenant-1',
        })

        webhook_data = {
            '_company_id': self.company.id,
            'contract_id': self.contract.id,
            'event_type': 'acknowledgement.completed',
            'webhook_id': 'webhook-uuid-3',
            'parties': [
                {'ejar_party_id': 'ejar-party-lessor-1'},
                {'ejar_party_id': 'ejar-party-tenant-1'},
            ],
            'idempotency_key': 'test-idem-ack-001',
        }

        from ..services.webhook_processor import EjarWebhookProcessor

        processor = EjarWebhookProcessor(self.env)
        processor.process_webhook(
            webhook_data=webhook_data,
            correlation_id='corr-789',
        )

        # Verify parties synced
        lessor.invalidate_cache()
        tenant.invalidate_cache()
        self.assertEqual(lessor.sync_state, 'synced')
        self.assertEqual(tenant.sync_state, 'synced')

    def test_webhook_creates_sync_log(self):
        """Test that webhook processing creates ejar.sync.log entry."""
        webhook_data = {
            '_company_id': self.company.id,
            'contract_id': self.contract.id,
            'event_type': 'contract.approved',
            'webhook_id': 'webhook-uuid-4',
            'ejar_contract_number': 'EJAR-2024-002',
            'idempotency_key': 'test-idem-log-001',
        }

        from ..services.webhook_processor import EjarWebhookProcessor

        processor = EjarWebhookProcessor(self.env)
        processor.process_webhook(
            webhook_data=webhook_data,
            correlation_id='corr-log-1',
        )

        # Verify sync log created
        sync_log = self.env['ejar.sync.log'].search([
            ('correlation_id', '=', 'corr-log-1'),
            ('action', '=', 'webhook_contract.approved'),
        ])
        self.assertTrue(sync_log)
        self.assertEqual(sync_log.direction, 'inbound')
        self.assertEqual(sync_log.http_method, 'POST')
        self.assertEqual(sync_log.endpoint, '/ejar/webhook')
        self.assertEqual(sync_log.status, 'success')

    def test_webhook_unknown_event_type(self):
        """Test webhook with unknown event type."""
        webhook_data = {
            '_company_id': self.company.id,
            'contract_id': self.contract.id,
            'event_type': 'unknown.event',
            'webhook_id': 'webhook-uuid-5',
            'idempotency_key': 'test-idem-unknown-001',
        }

        from ..services.webhook_processor import EjarWebhookProcessor
        from ..services.exceptions import EjarWebhookUnknownEventType

        processor = EjarWebhookProcessor(self.env)

        with self.assertRaises(EjarWebhookUnknownEventType):
            processor.process_webhook(
                webhook_data=webhook_data,
                correlation_id='corr-unknown-1',
            )

    def test_webhook_contract_not_found(self):
        """Test webhook for non-existent contract."""
        webhook_data = {
            '_company_id': self.company.id,
            'contract_id': 99999,
            'event_type': 'contract.approved',
            'webhook_id': 'webhook-uuid-6',
            'idempotency_key': 'test-idem-notfound-001',
        }

        from ..services.webhook_processor import EjarWebhookProcessor
        from ..services.exceptions import EjarWebhookContractNotFound

        processor = EjarWebhookProcessor(self.env)

        with self.assertRaises(EjarWebhookContractNotFound):
            processor.process_webhook(
                webhook_data=webhook_data,
                correlation_id='corr-notfound-1',
            )
