"""
Ejar ECRS Payload Builder
=========================
Converts Odoo record data into Ejar ECRS JSON API attribute dicts.

IDENTITY RULE: The brokerage profile (customer company) identity is
injected into every payload. Propza never appears in any Ejar payload.

All methods return the `attributes` dict for the JSON API envelope:
    {"data": {"type": "...", "attributes": <returned dict>}}

Raises EjarPayloadError for any missing required field so that
validation failures are caught before any HTTP call.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any, Dict, Optional

from .exceptions import EjarPayloadError

_logger = logging.getLogger(__name__)


class EjarPayloadBuilder:
    """
    Stateless builder — instantiate once, call any build_* method.

    Accepts the Odoo `env` only for lookups; never mutates records.
    """

    def __init__(self, env: Any) -> None:
        self._env = env

    # ------------------------------------------------------------------
    # Contracts
    # ------------------------------------------------------------------

    def build_contract_attributes(
        self,
        contract: Any,
        profile: Any,
    ) -> Dict[str, Any]:
        """
        Build attributes for POST /contracts.

        The brokerage office identity comes from *profile*,
        not from any Propza-level configuration.
        """
        self._require(contract.start_date, 'start_date', 'ejar.contract')
        self._require(contract.end_date, 'end_date', 'ejar.contract')
        self._require(contract.rent_amount, 'rent_amount', 'ejar.contract')
        self._require(profile, 'brokerage_profile_id', 'ejar.contract')

        payment_schedule_map = {
            'monthly':  'monthly',
            'quarterly': 'quarterly',
            'biannual': 'biannual',
            'annual':   'annual',
        }

        attrs: Dict[str, Any] = {
            'contract_type': contract.contract_type or 'residential',
            'sub_type': contract.contract_sub_type or 'main',
            'use_type': contract.use_type or 'residential_families',
            'start_date': str(contract.start_date),
            'end_date': str(contract.end_date),
            'number_of_years': round(contract.duration_years, 4),
            'sublease_allowed': contract.sublease_allowed,
            'custom_terms': contract.custom_terms or '',
        }
        return attrs

    # ------------------------------------------------------------------
    # Financial information
    # ------------------------------------------------------------------

    def build_financial_attributes(
        self,
        contract: Any,
    ) -> Dict[str, Any]:
        """POST /contracts/{id}/financial_information"""
        self._require(contract.rent_amount, 'rent_amount', 'ejar.contract')
        self._require(contract.payment_schedule, 'payment_schedule', 'ejar.contract')

        # Lessor IBAN — required for financial info
        lessor_party = self._get_party(contract, role='lessor')
        iban = ''
        iban_belongs_to = 'lessor'
        if lessor_party and lessor_party.iban:
            iban = lessor_party.iban

        return {
            'annual_rent': round(contract.rent_amount, 2),
            'billing_type': contract.payment_schedule,
            'payment_option': contract.payment_option or 'bank_transfer',
            'iban_number': iban,
            'iban_belongs_to': iban_belongs_to,
            'ejar_fees_paid_by': contract.ejar_fees_paid_by or 'brokerage_office',
        }

    # ------------------------------------------------------------------
    # Rental fee (brokerage commission)
    # ------------------------------------------------------------------

    def build_rental_fee_attributes(
        self,
        contract: Any,
        profile: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        POST /contracts/{id}/rental_fee
        Returns None if no brokerage fee configured (optional endpoint).
        """
        if not contract.brokerage_fee:
            return None
        if not profile or not profile.license_number:
            _logger.warning(
                'Brokerage fee set on contract %s but profile has no license_number',
                contract.name,
            )

        return {
            'brokerage_fee': round(contract.brokerage_fee, 2),
            'brokerage_fee_paid_by': contract.brokerage_fee_paid_by or 'lessor',
            'brokerage_license_number': profile.license_number if profile else '',
        }

    # ------------------------------------------------------------------
    # Individual entity (lessor / tenant)
    # ------------------------------------------------------------------

    def build_individual_entity_attributes(
        self,
        party: Any,
    ) -> Dict[str, Any]:
        """POST /individual_entities"""
        self._require(party.id_number, 'id_number', 'ejar.contract.party')
        self._require(party.mobile, 'mobile', 'ejar.contract.party')
        self._require(party.full_name_ar, 'full_name_ar', 'ejar.contract.party')

        return {
            'id_number': party.id_number,
            'id_type': party.id_type or 'national_id',
            'id_expiry_date': str(party.id_expiry) if party.id_expiry else None,
            'full_name': party.full_name_ar,
            'mobile_number': self._normalize_mobile(party.mobile),
            'email': party.email or None,
            'nationality': party.nationality or 'SA',
        }

    # ------------------------------------------------------------------
    # Organization entity (corporate lessor / tenant)
    # ------------------------------------------------------------------

    def build_organization_entity_attributes(
        self,
        party: Any,
    ) -> Dict[str, Any]:
        """POST /organization_entities"""
        self._require(
            party.cr_number or party.unified_number,
            'cr_number / unified_number',
            'ejar.contract.party',
        )

        return {
            'cr_number': party.cr_number or '',
            'unified_number': party.unified_number or '',
            'organization_name': party.full_name_ar or '',
            'mobile_number': self._normalize_mobile(party.mobile or ''),
        }

    # ------------------------------------------------------------------
    # Contract party (add to contract after entity created)
    # ------------------------------------------------------------------

    def build_party_attributes(
        self,
        party: Any,
        entity_id: str,
    ) -> Dict[str, Any]:
        """POST /contracts/{id}/parties"""
        self._require(entity_id, 'ejar_entity_id', 'ejar.contract.party')
        self._require(party.role, 'role', 'ejar.contract.party')

        entity_type_map = {
            'individual':   'individual_entities',
            'organization': 'organization_entities',
        }

        return {
            'role': party.role,
            'entity_type': entity_type_map.get(party.entity_type, 'individual_entities'),
            'entity_id': entity_id,
        }

    # ------------------------------------------------------------------
    # Contract unit
    # ------------------------------------------------------------------

    def build_unit_attributes(
        self,
        unit: Any,
    ) -> Dict[str, Any]:
        """POST /contracts/{id}/units"""
        self._require(unit.deed_number, 'deed_number', 'ejar.contract.unit')
        self._require(unit.unit_number, 'unit_number', 'ejar.contract.unit')

        prop = unit.property_id

        attrs: Dict[str, Any] = {
            'unit_number': unit.unit_number,
            'unit_type': unit.unit_type or 'apartment',
            'area': round(unit.area or 0, 2),
            'floor_number': unit.floor_number or 0,
            'furnishing': unit.furnishing or 'unfurnished',
            'finishing': unit.finishing or 'finished',
        }
        if unit.direction:
            attrs['direction'] = unit.direction
        if unit.bedrooms:
            attrs['bedrooms'] = unit.bedrooms
        if unit.bathrooms:
            attrs['bathrooms'] = unit.bathrooms

        # Property location (from Odoo property.property)
        if prop:
            attrs.update({
                'deed_number': prop.deed_number or '',
                'deed_type': getattr(prop, 'deed_type', 'electronic') or 'electronic',
                'national_address_code': getattr(prop, 'national_address_code', '') or '',
                'building_number': getattr(prop, 'building_number', '') or '',
                'district': getattr(prop, 'district_ar', '') or getattr(prop, 'district', '') or '',
                'city': prop.sa_city_id.name if hasattr(prop, 'sa_city_id') and prop.sa_city_id else '',
                'region': prop.sa_region_id.code if hasattr(prop, 'sa_region_id') and prop.sa_region_id else '',
                'postal_code': getattr(prop, 'postal_code', '') or '',
            })
        return attrs

    # ------------------------------------------------------------------
    # Custom terms
    # ------------------------------------------------------------------

    def build_custom_terms_attributes(
        self,
        contract: Any,
    ) -> Optional[Dict[str, Any]]:
        """POST /contracts/{id}/custom_terms — returns None if no custom terms."""
        if not contract.custom_terms:
            return None
        return {'terms': contract.custom_terms}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require(self, value: Any, field: str, model: str) -> None:
        if not value and value != 0:
            raise EjarPayloadError(
                f"Required field is empty: {field}",
                odoo_field=field,
                odoo_model=model,
            )

    @staticmethod
    def _normalize_mobile(mobile: str) -> str:
        """Normalise Saudi mobile to +966XXXXXXXXX format."""
        if not mobile:
            return ''
        digits = re.sub(r'\D', '', mobile)
        if digits.startswith('966'):
            return '+' + digits
        if digits.startswith('0') and len(digits) == 10:
            return '+966' + digits[1:]
        if len(digits) == 9:
            return '+966' + digits
        return mobile  # return as-is if pattern unrecognised

    @staticmethod
    def _get_party(contract: Any, *, role: str) -> Optional[Any]:
        for party in contract.party_ids:
            if party.role == role:
                return party
        return None
