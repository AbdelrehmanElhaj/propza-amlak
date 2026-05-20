"""Tests for ejar.contract state machine and transitions."""
from odoo.tests import TransactionCase
from odoo.exceptions import UserError, ValidationError
from odoo import fields


class TestEjarContractStateMachine(TransactionCase):
    """Test 9-state contract machine and transition guard."""

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.profile = self._create_brokerage_profile()
        self.contract = self._create_contract('draft')

    def _create_brokerage_profile(self):
        return self.env['ejar.brokerage.profile'].create({
            'company_id': self.company.id,
            'office_name_ar': 'مكتب الوساطة',
            'office_name_en': 'Brokerage Office',
            'cr_number': '1234567890',
            'license_number': 'RERA-123456',
            'license_expiry': fields.Date.today().replace(year=fields.Date.today().year + 1),
            'unified_number': '1111111111',
            'vat_number': '3333333333',
        })

    def _create_contract(self, status='draft'):
        return self.env['ejar.contract'].create({
            'company_id': self.company.id,
            'brokerage_profile_id': self.profile.id,
            'ejar_status': status,
            'contract_type': 'residential',
            'start_date': fields.Date.today(),
            'end_date': fields.Date.today().replace(year=fields.Date.today().year + 1),
            'rent_amount': 50000.0,
        })

    def test_transition_draft_to_building(self):
        """draft → building allowed."""
        self.contract.action_start_building()
        self.assertEqual(self.contract.ejar_status, 'building')

    def test_transition_building_to_ready(self):
        """building → ready requires complete data."""
        self.contract._set_status('building')
        # Add required data
        self.env['ejar.contract.party'].create({
            'contract_id': self.contract.id,
            'role': 'lessor',
            'entity_type': 'individual',
            'id_type': 'national_id',
            'id_number': '1234567890',
        })
        self.env['ejar.contract.party'].create({
            'contract_id': self.contract.id,
            'role': 'tenant',
            'entity_type': 'individual',
            'id_type': 'national_id',
            'id_number': '9876543210',
        })
        self.env['ejar.contract.unit'].create({
            'contract_id': self.contract.id,
            'unit_number': '1A',
            'property_id': self.env['property.property'].create({
                'name': 'Test Property',
                'company_id': self.company.id,
            }).id,
        })
        self.contract.signed_doc = b'fake_pdf_data'

        self.contract.action_mark_ready()
        self.assertEqual(self.contract.ejar_status, 'ready')

    def test_transition_ready_to_submitting(self):
        """ready → submitting via submission wizard."""
        self.contract._set_status('ready')
        self.contract._set_status('submitting')
        self.assertEqual(self.contract.ejar_status, 'submitting')

    def test_transition_submitting_to_submitted(self):
        """submitting → submitted after API success."""
        self.contract._set_status('submitting')
        self.contract._set_status('submitted')
        self.assertEqual(self.contract.ejar_status, 'submitted')

    def test_transition_submitted_to_approved(self):
        """submitted → approved via webhook or polling."""
        self.contract._set_status('submitted')
        self.contract._set_status('approved')
        self.assertEqual(self.contract.ejar_status, 'approved')

    def test_transition_submitted_to_rejected(self):
        """submitted → rejected via webhook or polling."""
        self.contract._set_status('submitted')
        self.contract._set_status('rejected')
        self.contract.rejection_reason = 'Invalid data'
        self.assertEqual(self.contract.ejar_status, 'rejected')

    def test_transition_rejected_to_draft(self):
        """rejected → draft for resubmission."""
        self.contract._set_status('rejected')
        self.contract.action_reset_to_draft()
        self.assertEqual(self.contract.ejar_status, 'draft')

    def test_transition_invalid_draft_to_submitted(self):
        """draft → submitted is not allowed."""
        with self.assertRaises(ValidationError):
            self.contract._set_status('submitted')

    def test_transition_invalid_approved_to_rejected(self):
        """approved → rejected is not allowed."""
        self.contract._set_status('approved')
        with self.assertRaises(ValidationError):
            self.contract._set_status('rejected')

    def test_terminal_states_no_transition(self):
        """Terminal states (expired, cancelled) have no outgoing transitions."""
        self.contract._set_status('expired')
        with self.assertRaises(UserError):
            self.contract.action_cancel()

        self.contract._set_status('cancelled')
        with self.assertRaises(UserError):
            self.contract.action_cancel()

    def test_cancel_from_any_non_terminal(self):
        """cancel() works from any non-terminal state."""
        for status in ['draft', 'building', 'ready', 'submitting', 'submitted', 'approved', 'rejected']:
            contract = self._create_contract(status)
            contract.action_cancel()
            self.assertEqual(contract.ejar_status, 'cancelled')

    def test_chatter_posted_on_status_change(self):
        """Chatter message posted on state transitions."""
        self.contract.action_start_building()
        messages = self.contract.message_ids
        self.assertTrue(any('إعداد' in m.body for m in messages))


class TestEjarContractValidation(TransactionCase):
    """Test contract data validation constraints."""

    def setUp(self):
        super().setUp()
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

    def test_end_date_after_start_date(self):
        """end_date must be after start_date."""
        today = fields.Date.today()
        with self.assertRaises(ValidationError):
            self.env['ejar.contract'].create({
                'company_id': self.company.id,
                'brokerage_profile_id': self.profile.id,
                'contract_type': 'residential',
                'start_date': today,
                'end_date': today,  # Same day — invalid
                'rent_amount': 50000.0,
            })

    def test_brokerage_fee_capped_at_2_5_percent(self):
        """Brokerage fee must not exceed 2.5% RERA cap."""
        today = fields.Date.today()
        annual_rent = 100000.0
        max_fee = annual_rent * 0.025  # 2500

        with self.assertRaises(ValidationError):
            self.env['ejar.contract'].create({
                'company_id': self.company.id,
                'brokerage_profile_id': self.profile.id,
                'contract_type': 'residential',
                'start_date': today,
                'end_date': today.replace(year=today.year + 1),
                'rent_amount': annual_rent,
                'brokerage_fee': max_fee + 1,  # Over cap
            })

    def test_brokerage_fee_under_cap_accepted(self):
        """Brokerage fee under 2.5% is accepted."""
        today = fields.Date.today()
        annual_rent = 100000.0
        max_fee = annual_rent * 0.025  # 2500

        contract = self.env['ejar.contract'].create({
            'company_id': self.company.id,
            'brokerage_profile_id': self.profile.id,
            'contract_type': 'residential',
            'start_date': today,
            'end_date': today.replace(year=today.year + 1),
            'rent_amount': annual_rent,
            'brokerage_fee': max_fee - 100,  # Under cap
        })

        self.assertEqual(contract.brokerage_fee, max_fee - 100)

    def test_is_ready_to_submit_computed_field(self):
        """is_ready_to_submit requires all mandatory fields."""
        contract = self.env['ejar.contract'].create({
            'company_id': self.company.id,
            'brokerage_profile_id': self.profile.id,
            'contract_type': 'residential',
            'start_date': fields.Date.today(),
            'end_date': fields.Date.today().replace(year=fields.Date.today().year + 1),
            'rent_amount': 50000.0,
        })

        # Initially not ready (no parties, units, doc)
        self.assertFalse(contract.is_ready_to_submit)

        # Add lessor
        self.env['ejar.contract.party'].create({
            'contract_id': contract.id,
            'role': 'lessor',
            'entity_type': 'individual',
            'id_type': 'national_id',
            'id_number': '1234567890',
        })
        contract.invalidate_cache(['is_ready_to_submit'])
        self.assertFalse(contract.is_ready_to_submit)  # Still missing tenant, unit, doc

        # Add tenant
        self.env['ejar.contract.party'].create({
            'contract_id': contract.id,
            'role': 'tenant',
            'entity_type': 'individual',
            'id_type': 'national_id',
            'id_number': '9876543210',
        })
        contract.invalidate_cache(['is_ready_to_submit'])
        self.assertFalse(contract.is_ready_to_submit)  # Still missing unit, doc

        # Add unit
        self.env['ejar.contract.unit'].create({
            'contract_id': contract.id,
            'unit_number': '1A',
            'property_id': self.env['property.property'].create({
                'name': 'Test Property',
                'company_id': self.company.id,
            }).id,
        })
        contract.invalidate_cache(['is_ready_to_submit'])
        self.assertFalse(contract.is_ready_to_submit)  # Still missing doc

        # Add signed document
        contract.signed_doc = b'fake_pdf_data'
        contract.invalidate_cache(['is_ready_to_submit'])
        self.assertTrue(contract.is_ready_to_submit)  # Now ready!

    def test_duration_years_computed(self):
        """duration_years computed from start/end dates."""
        contract = self.env['ejar.contract'].create({
            'company_id': self.company.id,
            'brokerage_profile_id': self.profile.id,
            'contract_type': 'residential',
            'start_date': fields.Date.today(),
            'end_date': fields.Date.today().replace(year=fields.Date.today().year + 1),
            'rent_amount': 50000.0,
        })

        self.assertAlmostEqual(contract.duration_years, 1.0, delta=0.01)

    def test_doc_fee_computed(self):
        """doc_fee is computed: ceil(duration_years) * 125 SAR."""
        contract = self.env['ejar.contract'].create({
            'company_id': self.company.id,
            'brokerage_profile_id': self.profile.id,
            'contract_type': 'residential',
            'start_date': fields.Date.today(),
            'end_date': fields.Date.today().replace(year=fields.Date.today().year + 1),
            'rent_amount': 50000.0,
        })

        # 1 year → 125 SAR
        self.assertEqual(contract.doc_fee, 125.0)
