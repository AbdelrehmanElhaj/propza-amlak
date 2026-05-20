"""
Ejar ECRS Contract Lifecycle Service
======================================
Orchestrates the full Ejar ECRS submission sequence for one contract.

Execution order (per Ejar spec):
  1.  Resolve brokerage profile & validate
  2.  Create/resolve individual entity — lessor
  3.  Create/resolve individual entity — tenant
  4.  Create/resolve individual entities — representatives (if any)
  5.  POST /contracts  → ejar_contract_id
  6.  POST /contracts/{id}/units  (for each unit)
  7.  POST /contracts/{id}/parties  (lessor)
  8.  POST /contracts/{id}/parties  (tenant)
  9.  POST /contracts/{id}/parties  (representatives, if any)
  10. Upload proxy documents for representative parties
  11. POST /contracts/{id}/signed_documents
  12. POST /contracts/{id}/financial_information
  13. POST /contracts/{id}/rental_fee  (if brokerage fee configured)
  14. POST /contracts/{id}/submit

Idempotency: each step checks whether the Ejar UUID is already stored on
the Odoo record and skips the API call if so — safe to re-run on failure.

Transactional safety: Odoo record updates are committed after each
successful step so that a partial run can be resumed cleanly.

Poll logic:
  GET /contracts/{id}  → maps Ejar state → Odoo ejar_status
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, Optional, Tuple

from .ejar_client import EjarApiClient
from .exceptions import (
    EjarAPIError,
    EjarConflictError,
    EjarPayloadError,
    EjarValidationError,
)
from .payload_builder import EjarPayloadBuilder

_logger = logging.getLogger(__name__)


class EjarContractLifecycleService:
    """
    Orchestrates full ECRS submission for one ejar.contract record.

    Usage (from wizard or model method)::

        svc = EjarContractLifecycleService(self.env)
        svc.execute_full_submission(contract.id)
    """

    def __init__(self, env: Any) -> None:
        self._env = env
        self._builder = EjarPayloadBuilder(env)

    # ==================================================================
    # Public: full submission
    # ==================================================================

    def execute_full_submission(self, contract_id: int) -> Dict[str, Any]:
        """
        Run the full submission pipeline for *contract_id*.

        Returns a dict with keys: success, ejar_contract_id, ejar_contract_number, message.
        Raises EjarAPIError subclasses on failure.

        The Odoo contract is moved to 'submitting' at the start and
        to 'submitted' on success, or back to 'ready' on failure.
        """
        contract = self._env['ejar.contract'].browse(contract_id)
        contract.ensure_one()

        correlation_id = str(uuid.uuid4())
        _logger.info(
            'Starting Ejar submission | contract=%s company=%s correlation=%s',
            contract.name, contract.company_id.id, correlation_id,
        )

        # ── Move to submitting (blocks concurrent submissions) ────────
        contract.sudo().write({
            'ejar_status': 'submitting',
            'submit_attempt': contract.submit_attempt + 1,
            'submit_error': False,
        })
        self._env.cr.commit()

        try:
            result = self._run_pipeline(contract, correlation_id)
            return result
        except Exception as exc:
            # Roll back to 'ready' so the user can retry
            contract.sudo().write({
                'ejar_status': 'ready',
                'submit_error': str(exc)[:2048],
            })
            self._env.cr.commit()
            self._log_error(contract, 'execute_full_submission', exc, correlation_id)
            raise

    # ==================================================================
    # Public: poll status
    # ==================================================================

    def poll_contract_status(self, contract_id: int) -> Dict[str, Any]:
        """
        Poll Ejar for the current status of a submitted contract.

        Returns: {ejar_state, ejar_contract_number, rejection_reason}
        """
        contract = self._env['ejar.contract'].browse(contract_id)
        contract.ensure_one()

        if not contract.ejar_contract_id:
            return {'ejar_state': '', 'ejar_contract_number': '', 'rejection_reason': ''}

        correlation_id = str(uuid.uuid4())
        client = self._build_client(contract)

        self._sync_log(
            contract=contract,
            action='poll_contract_status',
            correlation_id=correlation_id,
        )

        try:
            response = client.get_contract(contract.ejar_contract_id, correlation_id=correlation_id)
        except EjarAPIError as exc:
            self._sync_log(
                contract=contract,
                action='poll_contract_status',
                correlation_id=correlation_id,
                status='error',
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            raise

        data = response.get('data', {})
        attrs = data.get('attributes', {})

        ejar_state = attrs.get('state', '')
        ejar_number = attrs.get('contract_number', '')
        rejection_reason = attrs.get('rejection_reason', '')

        self._sync_log(
            contract=contract,
            action='poll_contract_status',
            correlation_id=correlation_id,
            status='success',
            response_body=json.dumps({'state': ejar_state, 'contract_number': ejar_number}),
        )

        return {
            'ejar_state': ejar_state,
            'ejar_contract_number': ejar_number,
            'rejection_reason': rejection_reason,
        }

    # ==================================================================
    # Pipeline implementation
    # ==================================================================

    def _run_pipeline(
        self,
        contract: Any,
        correlation_id: str,
    ) -> Dict[str, Any]:
        """Execute steps 1–14 in sequence, persisting after each step."""
        profile = self._resolve_profile(contract)
        client = self._build_client(contract)

        # ── Step 2–4: Entities ───────────────────────────────────────
        self._resolve_party_entities(contract, client, correlation_id)
        self._env.cr.commit()

        # ── Step 5: Create contract ──────────────────────────────────
        ejar_contract_id = self._step_create_contract(
            contract, client, profile, correlation_id
        )
        self._env.cr.commit()

        # ── Step 6: Attach units ─────────────────────────────────────
        for unit in contract.unit_ids:
            self._step_attach_unit(contract, unit, client, ejar_contract_id, correlation_id)
        self._env.cr.commit()

        # ── Steps 7–9: Add parties ────────────────────────────────────
        for party in contract.party_ids:
            self._step_add_party(contract, party, client, ejar_contract_id, correlation_id)
        self._env.cr.commit()

        # ── Step 10: Proxy documents ─────────────────────────────────
        for party in contract.party_ids:
            if party.role in ('lessor_representative', 'tenant_representative'):
                self._step_upload_proxy_doc(
                    contract, party, client, ejar_contract_id, correlation_id
                )
        self._env.cr.commit()

        # ── Step 11: Signed document ─────────────────────────────────
        self._step_upload_signed_doc(contract, client, ejar_contract_id, correlation_id)
        self._env.cr.commit()

        # ── Step 12: Financial information ───────────────────────────
        self._step_add_financial_info(contract, client, ejar_contract_id, correlation_id)
        self._env.cr.commit()

        # ── Step 13: Rental fee (optional) ────────────────────────────
        self._step_add_rental_fee(contract, profile, client, ejar_contract_id, correlation_id)
        self._env.cr.commit()

        # ── Step 14: Submit ──────────────────────────────────────────
        self._step_submit(contract, client, ejar_contract_id, correlation_id)

        # ── Finalize ─────────────────────────────────────────────────
        contract.sudo().write({
            'ejar_status': 'submitted',
            'ejar_last_sync': self._env['ir.fields'].datetime_now()
                if hasattr(self._env.get('ir.fields'), 'datetime_now')
                else self._now(),
            'submit_error': False,
        })
        contract.message_post(
            body='تم إرسال العقد إلى إيجار بنجاح. يرجى الانتظار للموافقة.',
        )
        self._env.cr.commit()

        _logger.info(
            'Ejar submission complete | contract=%s ejar_id=%s',
            contract.name, ejar_contract_id,
        )

        return {
            'success': True,
            'ejar_contract_id': ejar_contract_id,
            'ejar_contract_number': contract.ejar_contract_number or '',
            'message': 'تم الإرسال بنجاح',
        }

    # ── Step implementations ──────────────────────────────────────────

    def _resolve_party_entities(
        self,
        contract: Any,
        client: EjarApiClient,
        correlation_id: str,
    ) -> None:
        """Create Ejar entity records for all parties that don't have one yet."""
        for party in contract.party_ids:
            if party.ejar_entity_id:
                self._sync_log(contract=contract, action='create_entity',
                               correlation_id=correlation_id, status='skipped')
                continue
            self._step_create_entity(contract, party, client, correlation_id)

    def _step_create_entity(
        self,
        contract: Any,
        party: Any,
        client: EjarApiClient,
        correlation_id: str,
    ) -> str:
        """Create individual or organization entity on Ejar."""
        if party.entity_type == 'individual':
            attrs = self._builder.build_individual_entity_attributes(party)
            action = 'create_individual_entity'
            try:
                resp = client.create_individual_entity(attrs, correlation_id=correlation_id)
            except EjarConflictError as exc:
                # Already exists — use existing entity ID from response
                entity_id = (exc.existing_resource or {}).get('id', '')
                if not entity_id:
                    raise
                resp = {'data': {'id': entity_id}}
        else:
            attrs = self._builder.build_organization_entity_attributes(party)
            action = 'create_organization_entity'
            try:
                resp = client.create_organization_entity(attrs, correlation_id=correlation_id)
            except EjarConflictError as exc:
                entity_id = (exc.existing_resource or {}).get('id', '')
                if not entity_id:
                    raise
                resp = {'data': {'id': entity_id}}

        entity_id = resp.get('data', {}).get('id', '')
        party.sudo().write({
            'ejar_entity_id': entity_id,
            'sync_state': 'synced',
        })
        self._sync_log(
            contract=contract,
            action=action,
            correlation_id=correlation_id,
            status='success',
            response_body=json.dumps({'entity_id': entity_id}),
        )
        return entity_id

    def _step_create_contract(
        self,
        contract: Any,
        client: EjarApiClient,
        profile: Any,
        correlation_id: str,
    ) -> str:
        """POST /contracts — skip if already created."""
        if contract.ejar_contract_id:
            _logger.info('Contract %s already has ejar_contract_id — skipping creation',
                         contract.name)
            return contract.ejar_contract_id

        attrs = self._builder.build_contract_attributes(contract, profile)
        try:
            resp = client.create_contract(attrs, correlation_id=correlation_id)
        except EjarConflictError as exc:
            # Idempotency: contract already created — extract existing ID
            existing = exc.existing_resource or {}
            ejar_id = existing.get('id', '')
            if not ejar_id:
                raise
            resp = {'data': {'id': ejar_id, 'attributes': existing}}

        ejar_id = resp.get('data', {}).get('id', '')
        attrs_resp = resp.get('data', {}).get('attributes', {})
        ejar_number = attrs_resp.get('contract_number', '')

        contract.sudo().write({
            'ejar_contract_id': ejar_id,
            'ejar_contract_number': ejar_number,
        })
        self._sync_log(
            contract=contract,
            action='create_contract',
            correlation_id=correlation_id,
            status='success',
            response_body=json.dumps({'ejar_contract_id': ejar_id}),
        )
        return ejar_id

    def _step_attach_unit(
        self,
        contract: Any,
        unit: Any,
        client: EjarApiClient,
        ejar_contract_id: str,
        correlation_id: str,
    ) -> None:
        """POST /contracts/{id}/units — skip if already attached."""
        if unit.ejar_contract_unit_id:
            return

        attrs = self._builder.build_unit_attributes(unit)
        try:
            resp = client.attach_unit(ejar_contract_id, attrs, correlation_id=correlation_id)
        except EjarConflictError as exc:
            existing = exc.existing_resource or {}
            unit.sudo().write({
                'ejar_property_id': existing.get('property_id', ''),
                'ejar_unit_id': existing.get('unit_id', ''),
                'ejar_contract_unit_id': existing.get('id', ''),
                'sync_state': 'synced',
            })
            return

        data = resp.get('data', {})
        included = resp.get('included', [{}])
        unit.sudo().write({
            'ejar_contract_unit_id': data.get('id', ''),
            'sync_state': 'synced',
        })
        self._sync_log(
            contract=contract,
            action='attach_unit',
            correlation_id=correlation_id,
            status='success',
        )

    def _step_add_party(
        self,
        contract: Any,
        party: Any,
        client: EjarApiClient,
        ejar_contract_id: str,
        correlation_id: str,
    ) -> None:
        """POST /contracts/{id}/parties — skip if already added."""
        if party.ejar_party_id:
            return

        entity_id = party.ejar_entity_id
        if not entity_id:
            raise EjarPayloadError(
                f"Party {party.display_name} has no ejar_entity_id before add_party",
                odoo_field='ejar_entity_id',
                odoo_model='ejar.contract.party',
            )

        attrs = self._builder.build_party_attributes(party, entity_id)
        try:
            resp = client.add_party(ejar_contract_id, attrs, correlation_id=correlation_id)
        except EjarConflictError as exc:
            existing = exc.existing_resource or {}
            party.sudo().write({
                'ejar_party_id': existing.get('id', ''),
                'sync_state': 'synced',
            })
            return

        party_id = resp.get('data', {}).get('id', '')
        party.sudo().write({
            'ejar_party_id': party_id,
            'sync_state': 'synced',
        })
        self._sync_log(
            contract=contract,
            action='add_party',
            correlation_id=correlation_id,
            status='success',
            response_body=json.dumps({'role': party.role, 'ejar_party_id': party_id}),
        )

    def _step_upload_proxy_doc(
        self,
        contract: Any,
        party: Any,
        client: EjarApiClient,
        ejar_contract_id: str,
        correlation_id: str,
    ) -> None:
        """Upload power-of-attorney for representative parties."""
        if party.ejar_proxy_doc_id or not party.proxy_doc:
            return
        if not party.ejar_party_id:
            return

        import base64
        content = base64.b64decode(party.proxy_doc)
        filename = party.proxy_doc_filename or f'proxy_{party.ejar_party_id}.pdf'

        resp = client.upload_proxy_document(
            ejar_contract_id,
            party.ejar_party_id,
            content,
            filename,
            doc_type=party.proxy_doc_type or 'paper_poa',
            correlation_id=correlation_id,
        )
        doc_id = resp.get('data', {}).get('id', '')
        party.sudo().write({'ejar_proxy_doc_id': doc_id})
        self._sync_log(
            contract=contract,
            action='upload_proxy_document',
            correlation_id=correlation_id,
            status='success',
        )

    def _step_upload_signed_doc(
        self,
        contract: Any,
        client: EjarApiClient,
        ejar_contract_id: str,
        correlation_id: str,
    ) -> None:
        """POST /contracts/{id}/signed_documents"""
        if not contract.signed_doc:
            raise EjarPayloadError(
                'Signed document is missing',
                odoo_field='signed_doc',
                odoo_model='ejar.contract',
            )

        import base64
        content = base64.b64decode(contract.signed_doc)
        filename = contract.signed_doc_filename or f'contract_{contract.name}.pdf'

        resp = client.upload_signed_document(
            ejar_contract_id,
            content,
            filename,
            correlation_id=correlation_id,
        )
        self._sync_log(
            contract=contract,
            action='upload_signed_document',
            correlation_id=correlation_id,
            status='success',
        )

    def _step_add_financial_info(
        self,
        contract: Any,
        client: EjarApiClient,
        ejar_contract_id: str,
        correlation_id: str,
    ) -> None:
        """POST /contracts/{id}/financial_information"""
        attrs = self._builder.build_financial_attributes(contract)
        try:
            client.add_financial_information(ejar_contract_id, attrs, correlation_id=correlation_id)
        except EjarConflictError:
            pass  # already set — idempotent
        self._sync_log(
            contract=contract,
            action='add_financial_information',
            correlation_id=correlation_id,
            status='success',
        )

    def _step_add_rental_fee(
        self,
        contract: Any,
        profile: Any,
        client: EjarApiClient,
        ejar_contract_id: str,
        correlation_id: str,
    ) -> None:
        """POST /contracts/{id}/rental_fee (optional)"""
        attrs = self._builder.build_rental_fee_attributes(contract, profile)
        if not attrs:
            return
        try:
            client.add_rental_fee(ejar_contract_id, attrs, correlation_id=correlation_id)
        except EjarConflictError:
            pass
        self._sync_log(
            contract=contract,
            action='add_rental_fee',
            correlation_id=correlation_id,
            status='success',
        )

    def _step_submit(
        self,
        contract: Any,
        client: EjarApiClient,
        ejar_contract_id: str,
        correlation_id: str,
    ) -> None:
        """POST /contracts/{id}/submit — the point of no return."""
        resp = client.submit_contract(ejar_contract_id, correlation_id=correlation_id)
        self._sync_log(
            contract=contract,
            action='submit_contract',
            correlation_id=correlation_id,
            status='success',
            response_body=json.dumps(resp.get('data', {})),
        )

    # ==================================================================
    # Internal helpers
    # ==================================================================

    def _resolve_profile(self, contract: Any) -> Any:
        """
        Resolve the brokerage profile for the contract's company.
        Raises UserError if not configured.
        """
        profile = contract.brokerage_profile_id
        if not profile:
            profile = self._env['ejar.brokerage.profile'].search(
                [('company_id', '=', contract.company_id.id)], limit=1
            )
            if profile:
                contract.sudo().write({'brokerage_profile_id': profile.id})

        if not profile:
            from odoo.exceptions import UserError
            raise UserError(
                'لم يُعثر على ملف مكتب الوساطة للشركة %s. '
                'يرجى إنشاء ملف وساطة أولاً.' % contract.company_id.name
            )

        profile.validate_for_submission()

        # Validate all parties
        for party in contract.party_ids:
            party.validate_for_submission()

        # Validate all units
        for unit in contract.unit_ids:
            unit.validate_for_submission()

        return profile

    def _build_client(self, contract: Any) -> EjarApiClient:
        return EjarApiClient(
            self._env,
            company_id=contract.company_id.id,
        )

    def _sync_log(
        self,
        *,
        contract: Any,
        action: str,
        correlation_id: str = '',
        status: str = 'success',
        error_type: str = '',
        error_message: str = '',
        response_body: str = '',
    ) -> None:
        self._env['ejar.sync.log'].log_call(
            action=action,
            contract_id=contract.id,
            company_id=contract.company_id.id,
            correlation_id=correlation_id,
            status=status,
            error_type=error_type,
            error_message=error_message,
            response_body=response_body,
        )

    def _log_error(
        self,
        contract: Any,
        action: str,
        exc: Exception,
        correlation_id: str,
    ) -> None:
        is_permanent = getattr(exc, 'is_permanent', False)
        self._sync_log(
            contract=contract,
            action=action,
            correlation_id=correlation_id,
            status='error',
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        contract.message_post(
            body='فشل إرسال العقد إلى إيجار: %s' % str(exc)[:500],
        )

    @staticmethod
    def _now():
        from odoo import fields as odoo_fields
        return odoo_fields.Datetime.now()
