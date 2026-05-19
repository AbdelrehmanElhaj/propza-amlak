from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import json

_logger = logging.getLogger(__name__)


class EjarApiConnector(models.AbstractModel):
    """
    Ejar API Connector
    ==================
    Handles all communication with Ejar platform API.
    Currently in SIMULATION mode — ready for real credentials.

    To activate real API:
    1. Get credentials from Ejar developer portal
    2. Set config params:
       - ejar.api.url
       - ejar.api.key
       - ejar.api.secret
    3. Change SIMULATION_MODE to False
    """
    _name = 'ejar.api.connector'
    _description = 'Ejar API Connector'

    SIMULATION_MODE = True  # Set to False when real API credentials available

    def _get_config(self):
        params = self.env['ir.config_parameter'].sudo()
        return {
            'url':    params.get_param('ejar.api.url', 'https://api.ejar.sa/v1'),
            'key':    params.get_param('ejar.api.key', ''),
            'secret': params.get_param('ejar.api.secret', ''),
        }

    def _build_headers(self):
        config = self._get_config()
        return {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-API-Key': config['key'],
            'X-API-Secret': config['secret'],
        }

    def _build_contract_payload(self, contract):
        """Build Ejar API payload from Odoo contract"""
        prop = contract.property_id
        return {
            "contractInfo": {
                "startDate": str(contract.start_date),
                "endDate": str(contract.end_date),
                "annualRent": contract.rent_amount,
                "paymentSchedule": contract.payment_schedule.upper(),
                "subleaseAllowed": contract.sublease_allowed,
                "feesBearer": contract.fee_bearer.upper(),
            },
            "propertyInfo": {
                "deedNumber": prop.deed_number or '',
                "deedType": prop.deed_type or 'electronic',
                "unitType": prop.ejar_unit_type or 'residential',
                "nationalAddressCode": prop.national_address_code or '',
                "buildingNumber": prop.building_number or '',
                "district": prop.district_ar or prop.district or '',
                "city": prop.sa_city_id.name_ar if prop.sa_city_id else '',
                "region": prop.sa_region_id.code if prop.sa_region_id else '',
                "postalCode": prop.postal_code or '',
            },
            "lessorInfo": {
                "nationalId": contract.lessor_partner_id.sa_national_id or '',
                "idType": (contract.lessor_partner_id.sa_id_type or 'national_id').upper(),
                "iban": contract.lessor_partner_id.sa_iban or '',
                "mobile": contract.lessor_partner_id.mobile or contract.lessor_partner_id.phone or '',
            },
            "tenantInfo": {
                "nationalId": contract.tenant_national_id or '',
                "idType": (contract.tenant_id_type or 'national_id').upper(),
                "mobile": contract.tenant_partner_id.mobile or contract.tenant_partner_id.phone or '',
            },
        }

    # ─── Public Methods ──────────────────────────────────────────

    def submit_contract(self, contract):
        """Submit new contract to Ejar"""
        if self.SIMULATION_MODE:
            return self._simulate_submit(contract)

        try:
            import requests
            config = self._get_config()
            if not config['key']:
                raise UserError(_('لم يتم ضبط بيانات اعتماد API إيجار'))

            payload = self._build_contract_payload(contract)
            response = requests.post(
                f"{config['url']}/contracts",
                headers=self._build_headers(),
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            return {
                'success': True,
                'contract_number': data.get('contractNumber'),
                'raw': data,
            }
        except Exception as e:
            _logger.error("Ejar API error: %s", str(e))
            return {'success': False, 'error': str(e)}

    def get_contract_status(self, contract_number):
        """Check contract status from Ejar"""
        if self.SIMULATION_MODE:
            return self._simulate_status(contract_number)

        try:
            import requests
            config = self._get_config()
            response = requests.get(
                f"{config['url']}/contracts/{contract_number}/status",
                headers=self._build_headers(),
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            return {
                'success': True,
                'status': data.get('status'),
                'raw': data,
            }
        except Exception as e:
            _logger.error("Ejar status check error: %s", str(e))
            return {'success': False, 'error': str(e)}

    def renew_contract(self, contract, new_end_date, new_rent):
        """Renew existing Ejar contract"""
        if self.SIMULATION_MODE:
            return {'success': True, 'contract_number': 'SIM-RENEW-001', 'simulated': True}

        try:
            import requests
            config = self._get_config()
            payload = {
                'originalContractNumber': contract.ejar_contract_number,
                'newEndDate': str(new_end_date),
                'newAnnualRent': new_rent,
            }
            response = requests.post(
                f"{config['url']}/contracts/{contract.ejar_contract_number}/renew",
                headers=self._build_headers(),
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            return {'success': True, 'contract_number': data.get('contractNumber')}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ─── Simulation Methods ──────────────────────────────────────

    def _simulate_submit(self, contract):
        """Simulate Ejar API response for testing"""
        import random
        import string
        fake_number = 'EJAR-' + ''.join(random.choices(string.digits, k=10))
        _logger.info("EJAR SIMULATION: Submitting contract → %s", fake_number)
        return {
            'success': True,
            'contract_number': fake_number,
            'simulated': True,
            'message': 'وضع المحاكاة — جاهز للـ API الحقيقي',
        }

    def _simulate_status(self, contract_number):
        _logger.info("EJAR SIMULATION: Checking status for %s", contract_number)
        return {
            'success': True,
            'status': 'ACTIVE',
            'simulated': True,
        }
