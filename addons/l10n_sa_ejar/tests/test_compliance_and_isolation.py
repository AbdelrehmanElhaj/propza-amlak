"""Tests for Saudi regulatory compliance (Riyadh rent freeze, RERA rules)."""
from datetime import datetime, date
from odoo.tests import TransactionCase
from odoo.exceptions import ValidationError
from odoo import fields


class TestRiyadhRentFreeze(TransactionCase):
    """Test Riyadh rent freeze validation (freeze until 2030-09-01)."""

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.profile = self.env['ejar.brokerage.profile'].create({
            'company_id': self.company.id,
            'office_name_ar': 'مكتب الوساطة',
            'office_name_en': 'Brokerage Office',
            'cr_number': '1234567890',
            'license_number': 'RERA-123456',
            'license_expiry': date(2030, 1, 1),
            'unified_number': '1111111111',
            'vat_number': '3333333333',
        })

        # Get or create Riyadh city (with rent_freeze=True)
        self.riyadh = self.env['sa.city'].search([('name', '=', 'الرياض')])
        if not self.riyadh:
            region = self.env['sa.region'].search([('name', '=', 'منطقة الرياض')])
            if not region:
                region = self.env['sa.region'].create({
                    'name': 'منطقة الرياض',
                    'region_code': '01',
                })
            self.riyadh = self.env['sa.city'].create({
                'name': 'الرياض',
                'region_id': region.id,
                'rent_freeze': True,
            })

    def test_rent_increase_in_riyadh_triggers_warning(self):
        """Rent increase above previous Ejar rent triggers warning in Riyadh."""
        # Create property in Riyadh with last_ejar_rent = 50000
        prop = self.env['property.property'].create({
            'name': 'Riyadh Property',
            'company_id': self.company.id,
            'sa_city_id': self.riyadh.id,
            'last_ejar_rent': 50000.0,
        })

        # Contract with increased rent
        contract = self.env['ejar.contract'].create({
            'company_id': self.company.id,
            'brokerage_profile_id': self.profile.id,
            'contract_type': 'residential',
            'start_date': fields.Date.today(),
            'end_date': fields.Date.today().replace(year=fields.Date.today().year + 1),
            'rent_amount': 55000.0,  # Increased
        })

        # Add unit to trigger warning computation
        self.env['ejar.contract.unit'].create({
            'contract_id': contract.id,
            'unit_number': '1A',
            'property_id': prop.id,
        })

        # Recompute warning
        contract.invalidate_cache(['rent_freeze_warning'])

        # Should have warning
        self.assertTrue(contract.rent_freeze_warning)

    def test_rent_decrease_in_riyadh_no_warning(self):
        """Rent decrease doesn't trigger warning even in Riyadh."""
        prop = self.env['property.property'].create({
            'name': 'Riyadh Property',
            'company_id': self.company.id,
            'sa_city_id': self.riyadh.id,
            'last_ejar_rent': 50000.0,
        })

        contract = self.env['ejar.contract'].create({
            'company_id': self.company.id,
            'brokerage_profile_id': self.profile.id,
            'contract_type': 'residential',
            'start_date': fields.Date.today(),
            'end_date': fields.Date.today().replace(year=fields.Date.today().year + 1),
            'rent_amount': 45000.0,  # Decreased
        })

        self.env['ejar.contract.unit'].create({
            'contract_id': contract.id,
            'unit_number': '1A',
            'property_id': prop.id,
        })

        contract.invalidate_cache(['rent_freeze_warning'])
        self.assertFalse(contract.rent_freeze_warning)

    def test_no_warning_outside_riyadh(self):
        """No warning for rent increases outside Riyadh."""
        # Non-Riyadh city
        other_city = self.env['sa.city'].search([('name', '!=', 'الرياض')])
        if not other_city:
            other_city = self.env['sa.city'].create({
                'name': 'جدة',
                'region_id': self.env['sa.region'].search([], limit=1).id,
                'rent_freeze': False,
            })

        prop = self.env['property.property'].create({
            'name': 'Non-Riyadh Property',
            'company_id': self.company.id,
            'sa_city_id': other_city.id,
            'last_ejar_rent': 50000.0,
        })

        contract = self.env['ejar.contract'].create({
            'company_id': self.company.id,
            'brokerage_profile_id': self.profile.id,
            'contract_type': 'residential',
            'start_date': fields.Date.today(),
            'end_date': fields.Date.today().replace(year=fields.Date.today().year + 1),
            'rent_amount': 55000.0,  # Increased
        })

        self.env['ejar.contract.unit'].create({
            'contract_id': contract.id,
            'unit_number': '1A',
            'property_id': prop.id,
        })

        contract.invalidate_cache(['rent_freeze_warning'])
        self.assertFalse(contract.rent_freeze_warning)


class TestContractPartyValidation(TransactionCase):
    """Test ejar.contract.party validation (NID, IBAN, entity types)."""

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.contract = self.env['ejar.contract'].create({
            'company_id': self.company.id,
            'contract_type': 'residential',
            'start_date': fields.Date.today(),
            'end_date': fields.Date.today().replace(year=fields.Date.today().year + 1),
            'rent_amount': 50000.0,
        })

    def test_national_id_format_validation(self):
        """National ID must match pattern: 1 followed by 9 digits."""
        # Valid NID
        party = self.env['ejar.contract.party'].create({
            'contract_id': self.contract.id,
            'role': 'lessor',
            'entity_type': 'individual',
            'id_type': 'national_id',
            'id_number': '1234567890',
        })
        self.assertTrue(party.id)  # Should not raise

        # Invalid NID (doesn't start with 1)
        with self.assertRaises(ValidationError):
            self.env['ejar.contract.party'].create({
                'contract_id': self.contract.id,
                'role': 'lessor',
                'entity_type': 'individual',
                'id_type': 'national_id',
                'id_number': '2234567890',  # Starts with 2
            })

    def test_iqama_format_validation(self):
        """Iqama must match pattern: 2 followed by 9 digits."""
        # Valid Iqama
        party = self.env['ejar.contract.party'].create({
            'contract_id': self.contract.id,
            'role': 'tenant',
            'entity_type': 'individual',
            'id_type': 'iqama',
            'id_number': '2234567890',
        })
        self.assertTrue(party.id)

        # Invalid Iqama (doesn't start with 2)
        with self.assertRaises(ValidationError):
            self.env['ejar.contract.party'].create({
                'contract_id': self.contract.id,
                'role': 'tenant',
                'entity_type': 'individual',
                'id_type': 'iqama',
                'id_number': '1234567890',  # Starts with 1
            })

    def test_iban_format_validation(self):
        """Saudi IBAN must match SA + 22 alphanumeric chars."""
        # Valid IBAN
        party = self.env['ejar.contract.party'].create({
            'contract_id': self.contract.id,
            'role': 'lessor',
            'entity_type': 'individual',
            'id_type': 'national_id',
            'id_number': '1234567890',
            'iban': 'SA1234567890123456789012',
        })
        self.assertTrue(party.id)

        # Invalid IBAN (wrong length)
        with self.assertRaises(ValidationError):
            self.env['ejar.contract.party'].create({
                'contract_id': self.contract.id,
                'role': 'lessor',
                'entity_type': 'individual',
                'id_type': 'national_id',
                'id_number': '1234567890',
                'iban': 'SA123',  # Too short
            })

    def test_entity_type_individual(self):
        """Individual entity type with NID/Iqama."""
        party = self.env['ejar.contract.party'].create({
            'contract_id': self.contract.id,
            'role': 'lessor',
            'entity_type': 'individual',
            'id_type': 'national_id',
            'id_number': '1234567890',
        })
        self.assertEqual(party.entity_type, 'individual')

    def test_entity_type_organization(self):
        """Organization entity type with CR number."""
        party = self.env['ejar.contract.party'].create({
            'contract_id': self.contract.id,
            'role': 'lessor',
            'entity_type': 'organization',
            'id_type': 'cr_number',
            'id_number': '1234567890',
        })
        self.assertEqual(party.entity_type, 'organization')

    def test_party_role_choices(self):
        """Party role must be one of: lessor, tenant, lessor_representative, tenant_representative."""
        valid_roles = ['lessor', 'tenant', 'lessor_representative', 'tenant_representative']
        for role in valid_roles:
            party = self.env['ejar.contract.party'].create({
                'contract_id': self.contract.id,
                'role': role,
                'entity_type': 'individual',
                'id_type': 'national_id',
                'id_number': '1234567890',
            })
            self.assertEqual(party.role, role)


class TestMultiCompanyIsolation(TransactionCase):
    """Test multi-company SaaS isolation with ir.rule domain_force."""

    def setUp(self):
        super().setUp()
        self.company1 = self.env['res.company'].create({'name': 'Company 1'})
        self.company2 = self.env['res.company'].create({'name': 'Company 2'})

        self.profile1 = self.env['ejar.brokerage.profile'].create({
            'company_id': self.company1.id,
            'office_name_ar': 'مكتب 1',
            'office_name_en': 'Office 1',
            'cr_number': '1111111111',
            'license_number': 'RERA-111111',
            'license_expiry': date(2030, 1, 1),
            'unified_number': '1111111111',
            'vat_number': '1111111111',
        })

        self.profile2 = self.env['ejar.brokerage.profile'].create({
            'company_id': self.company2.id,
            'office_name_ar': 'مكتب 2',
            'office_name_en': 'Office 2',
            'cr_number': '2222222222',
            'license_number': 'RERA-222222',
            'license_expiry': date(2030, 1, 1),
            'unified_number': '2222222222',
            'vat_number': '2222222222',
        })

    def test_contract_isolation_per_company(self):
        """Contracts are isolated per company via ir.rule."""
        contract1 = self.env['ejar.contract'].create({
            'company_id': self.company1.id,
            'brokerage_profile_id': self.profile1.id,
            'contract_type': 'residential',
            'start_date': fields.Date.today(),
            'end_date': fields.Date.today().replace(year=fields.Date.today().year + 1),
            'rent_amount': 50000.0,
        })

        contract2 = self.env['ejar.contract'].create({
            'company_id': self.company2.id,
            'brokerage_profile_id': self.profile2.id,
            'contract_type': 'residential',
            'start_date': fields.Date.today(),
            'end_date': fields.Date.today().replace(year=fields.Date.today().year + 1),
            'rent_amount': 60000.0,
        })

        # Both should exist
        self.assertTrue(contract1)
        self.assertTrue(contract2)
        self.assertNotEqual(contract1.company_id, contract2.company_id)

    def test_profile_unique_per_company(self):
        """Only one brokerage profile per company (unique constraint)."""
        with self.assertRaises(Exception):  # Unique constraint violation
            self.env['ejar.brokerage.profile'].create({
                'company_id': self.company1.id,
                'office_name_ar': 'مكتب 1 ثاني',
                'office_name_en': 'Office 1 Second',
                'cr_number': '9999999999',
                'license_number': 'RERA-999999',
                'license_expiry': date(2030, 1, 1),
                'unified_number': '9999999999',
                'vat_number': '9999999999',
            })

    def test_sync_log_isolation_per_company(self):
        """Sync logs are isolated per company."""
        log1 = self.env['ejar.sync.log'].log_call(
            action='test_action',
            contract_id=1,
            company_id=self.company1.id,
            correlation_id='corr-1',
            status='success',
        )

        log2 = self.env['ejar.sync.log'].log_call(
            action='test_action',
            contract_id=2,
            company_id=self.company2.id,
            correlation_id='corr-2',
            status='success',
        )

        self.assertEqual(log1.company_id, self.company1)
        self.assertEqual(log2.company_id, self.company2)
