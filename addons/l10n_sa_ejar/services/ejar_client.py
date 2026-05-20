"""
Ejar ECRS API — Production-Grade API Gateway
==============================================
Centralises all HTTP communication with the Ejar ECRS platform.

Key design decisions:
- One requests.Session per EjarApiClient instance (connection pool reuse).
- Retry adapter handles transient 5xx / 429 at the transport layer;
  application-level retry decisions are left to the caller.
- Every request carries a Correlation-ID (UUID4) for end-to-end tracing.
- Idempotency keys (SHA-256) prevent duplicate state mutations on retry.
- raise_for_ejar_status() maps every HTTP status to a typed exception so
  callers never need to inspect raw status codes.
- Sensitive fields are scrubbed from log output (see constants.SENSITIVE_FIELDS).

Propza identity isolation:
  The client sends the brokerage company's credentials (not Propza's).
  Propza never appears in any Ejar contract payload.
  Credential resolution is fully delegated to EjarAuthService.

Usage::

    from odoo.addons.l10n_sa_ejar.services import EjarApiClient

    client = EjarApiClient(env, company_id=self.env.company.id)
    contract = client.create_contract({...})
    client.add_party(contract["id"], {...})
    client.submit_contract(contract["id"])
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from typing import Any, BinaryIO, Dict, List, Optional, Tuple, Union

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency guard
# ---------------------------------------------------------------------------

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError as _err:
    raise ImportError(
        "The 'requests' package is required by l10n_sa_ejar. "
        "Install it with: pip install requests"
    ) from _err

from .auth_service import EjarAuthService, EjarCredentials
from .constants import (
    BASE_URLS,
    CB_FAILURE_THRESHOLD,
    CB_RECOVERY_TIMEOUT,
    CB_SUCCESS_THRESHOLD,
    CONNECT_TIMEOUT,
    CONTENT_TYPE_JSON,
    DEFAULT_TIMEOUT,
    ENV_UAT,
    EP_BROKERAGE_AGREEMENTS,
    EP_CONTRACT,
    EP_CONTRACT_INVOICES,
    EP_CONTRACT_PARTIES,
    EP_CONTRACT_PARTY,
    EP_CONTRACT_PDF,
    EP_CONTRACT_PROPERTIES,
    EP_CONTRACT_STATUS,
    EP_CONTRACT_SUBMIT,
    EP_CONTRACT_TERMS,
    EP_CONTRACT_UNIT,
    EP_CONTRACT_UNIT_SERVICES,
    EP_CONTRACT_UNITS,
    EP_CONTRACTS,
    EP_CUSTOM_TERMS,
    EP_FINANCIAL_INFO,
    EP_INDIVIDUAL_ENTITIES,
    EP_INDIVIDUAL_ENTITY,
    EP_OFFICE_WALLET,
    EP_ORGANIZATION_ENTITIES,
    EP_ORGANIZATION_ENTITY,
    EP_OWNERSHIP_DOCUMENT,
    EP_OWNERSHIP_DOCUMENT_OWNERS,
    EP_OWNERSHIP_DOCUMENTS,
    EP_OWNERSHIP_PROXY_DOCUMENTS,
    EP_PROPERTIES,
    EP_PROPERTY,
    EP_PROPERTY_UNIT,
    EP_PROPERTY_UNITS,
    EP_PROXY_DOCUMENT,
    EP_PROXY_DOCUMENTS,
    EP_RENTAL_FEE,
    EP_SIGNED_DOCUMENT,
    EP_SIGNED_DOCUMENTS,
    HDR_AUTHORIZATION,
    HDR_CONTENT_TYPE,
    HDR_CORRELATION_ID,
    HDR_IDEMPOTENCY_KEY,
    HDR_RETRY_AFTER,
    LOG_FIELD_ATTEMPT,
    LOG_FIELD_COMPANY_ID,
    LOG_FIELD_CONTRACT_ID,
    LOG_FIELD_CORRELATION_ID,
    LOG_FIELD_DURATION_MS,
    LOG_FIELD_ENDPOINT,
    LOG_FIELD_IDEMPOTENCY_KEY,
    LOG_FIELD_KEY_FINGERPRINT,
    LOG_FIELD_METHOD,
    LOG_FIELD_STATUS_CODE,
    MAX_RETRIES,
    PAGE_SIZE,
    READ_TIMEOUT,
    RETRY_BACKOFF_FACTOR,
    RETRY_BACKOFF_MAX,
    RETRY_JITTER_RANGE,
    RETRY_ON_METHODS,
    RETRY_ON_STATUS,
    UPLOAD_TIMEOUT,
    VALID_ENVIRONMENTS,
)
from .exceptions import (
    EjarAuthError,
    EjarCircuitOpenError,
    EjarNetworkError,
    EjarRateLimitError,
    EjarServerError,
    EjarTimeoutError,
    raise_for_ejar_status,
)


# ---------------------------------------------------------------------------
# Internal: circuit breaker state (per-company, in-process)
# ---------------------------------------------------------------------------

import threading
import dataclasses
import enum


class _CBState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclasses.dataclass
class _CircuitBreakerState:
    state: _CBState = _CBState.CLOSED
    failure_count: int = 0
    last_failure_at: float = 0.0
    half_open_success_count: int = 0
    lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)


_CIRCUIT_BREAKERS: Dict[int, _CircuitBreakerState] = {}
_CB_LOCK = threading.Lock()


def _get_circuit(company_id: int) -> _CircuitBreakerState:
    with _CB_LOCK:
        if company_id not in _CIRCUIT_BREAKERS:
            _CIRCUIT_BREAKERS[company_id] = _CircuitBreakerState()
        return _CIRCUIT_BREAKERS[company_id]


# ---------------------------------------------------------------------------
# EjarApiClient
# ---------------------------------------------------------------------------


class EjarApiClient:
    """
    Production-grade HTTP client for the Ejar ECRS API.

    One instance per request is fine; the session is not shared across threads.
    For long-lived service objects, instantiate once per company and reuse.

    Args:
        env:        Odoo environment (self.env from a model method).
        company_id: Odoo company ID whose Ejar credentials to use.
        environment: Override environment; defaults to company configuration.
    """

    def __init__(
        self,
        env: Any,
        *,
        company_id: int,
        environment: Optional[str] = None,
    ) -> None:
        self._env = env
        self._company_id = company_id

        auth_service = EjarAuthService(env)
        self._credentials: EjarCredentials = auth_service.get_credentials(company_id)

        self._environment = environment or self._credentials.environment
        if self._environment not in VALID_ENVIRONMENTS:
            from .exceptions import EjarConfigurationError
            raise EjarConfigurationError(
                f"Unknown environment {self._environment!r}",
                company_id=company_id,
            )

        self._base_url = BASE_URLS[self._environment]
        self._session = self._build_session()
        self._circuit = _get_circuit(company_id)

    # ------------------------------------------------------------------
    # Session / transport
    # ------------------------------------------------------------------

    def _build_session(self) -> requests.Session:
        session = requests.Session()

        retry_strategy = Retry(
            total=MAX_RETRIES,
            backoff_factor=RETRY_BACKOFF_FACTOR,
            status_forcelist=list(RETRY_ON_STATUS),
            allowed_methods=list(RETRY_ON_METHODS),
            raise_on_status=False,
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        session.headers.update({
            HDR_CONTENT_TYPE: CONTENT_TYPE_JSON,
            "Accept": "application/json",
            HDR_AUTHORIZATION: self._credentials.to_auth_header(),
        })
        return session

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    @staticmethod
    def _build_idempotency_key(*parts: Any) -> str:
        """SHA-256 of colon-joined string representations of *parts*."""
        raw = ":".join(str(p) for p in parts).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    # ------------------------------------------------------------------
    # Circuit breaker
    # ------------------------------------------------------------------

    def _circuit_check(self, correlation_id: str) -> None:
        cb = self._circuit
        with cb.lock:
            if cb.state == _CBState.OPEN:
                elapsed = time.monotonic() - cb.last_failure_at
                if elapsed < CB_RECOVERY_TIMEOUT:
                    raise EjarCircuitOpenError(
                        f"Circuit open for company {self._company_id} "
                        f"— retry in {int(CB_RECOVERY_TIMEOUT - elapsed)}s",
                        retry_after=int(CB_RECOVERY_TIMEOUT - elapsed),
                        failure_count=cb.failure_count,
                        company_id=self._company_id,
                        correlation_id=correlation_id,
                    )
                _logger.info(
                    "Circuit moving to HALF_OPEN | company_id=%s",
                    self._company_id,
                )
                cb.state = _CBState.HALF_OPEN
                cb.half_open_success_count = 0

    def _circuit_record_success(self) -> None:
        cb = self._circuit
        with cb.lock:
            if cb.state == _CBState.HALF_OPEN:
                cb.half_open_success_count += 1
                if cb.half_open_success_count >= CB_SUCCESS_THRESHOLD:
                    cb.state = _CBState.CLOSED
                    cb.failure_count = 0
                    _logger.info(
                        "Circuit CLOSED (recovered) | company_id=%s",
                        self._company_id,
                    )
            elif cb.state == _CBState.CLOSED:
                cb.failure_count = 0

    def _circuit_record_failure(self, exc: Exception) -> None:
        cb = self._circuit
        with cb.lock:
            cb.failure_count += 1
            cb.last_failure_at = time.monotonic()
            if cb.failure_count >= CB_FAILURE_THRESHOLD:
                if cb.state != _CBState.OPEN:
                    _logger.warning(
                        "Circuit OPEN after %s failures | company_id=%s",
                        cb.failure_count,
                        self._company_id,
                    )
                cb.state = _CBState.OPEN

    # ------------------------------------------------------------------
    # Core request dispatcher
    # ------------------------------------------------------------------

    def _make_request(
        self,
        method: str,
        endpoint: str,
        *,
        correlation_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        timeout: Optional[Tuple[int, int]] = None,
    ) -> Dict[str, Any]:
        """
        Execute one HTTP request and return the parsed JSON body.

        Raises typed EjarAPIError subclasses on any non-2xx response.
        """
        cid = correlation_id or str(uuid.uuid4())
        url = self._base_url + endpoint

        self._circuit_check(cid)

        extra_headers: Dict[str, str] = {HDR_CORRELATION_ID: cid}
        if idempotency_key:
            extra_headers[HDR_IDEMPOTENCY_KEY] = idempotency_key

        effective_timeout = timeout or DEFAULT_TIMEOUT
        t_start = time.monotonic()

        _logger.info(
            "Ejar API request | %s=%s %s=%s %s=%s %s=%s %s=%s",
            LOG_FIELD_CORRELATION_ID, cid,
            LOG_FIELD_COMPANY_ID, self._company_id,
            LOG_FIELD_METHOD, method,
            LOG_FIELD_ENDPOINT, endpoint,
            LOG_FIELD_KEY_FINGERPRINT, self._credentials.fingerprint,
        )

        try:
            if files:
                # Multipart upload — remove Content-Type so requests sets boundary
                merged_headers = {**extra_headers}
                send_headers = {
                    k: v for k, v in self._session.headers.items()
                    if k.lower() != "content-type"
                }
                send_headers.update(merged_headers)
                response = self._session.request(
                    method,
                    url,
                    headers=send_headers,
                    params=params,
                    files=files,
                    timeout=effective_timeout,
                )
            else:
                response = self._session.request(
                    method,
                    url,
                    headers=extra_headers,
                    params=params,
                    json=json_body,
                    timeout=effective_timeout,
                )

        except requests.exceptions.Timeout as exc:
            self._circuit_record_failure(exc)
            raise EjarTimeoutError(
                f"Request timed out: {method} {endpoint}",
                original_error=exc,
                correlation_id=cid,
                company_id=self._company_id,
                endpoint=endpoint,
            ) from exc

        except requests.exceptions.ConnectionError as exc:
            self._circuit_record_failure(exc)
            raise EjarNetworkError(
                f"Connection error: {method} {endpoint}",
                original_error=exc,
                correlation_id=cid,
                company_id=self._company_id,
                endpoint=endpoint,
            ) from exc

        except requests.exceptions.RequestException as exc:
            self._circuit_record_failure(exc)
            raise EjarNetworkError(
                f"Request failed: {method} {endpoint} — {exc}",
                original_error=exc,
                correlation_id=cid,
                company_id=self._company_id,
                endpoint=endpoint,
            ) from exc

        duration_ms = int((time.monotonic() - t_start) * 1000)

        _logger.info(
            "Ejar API response | %s=%s %s=%s %s=%d %s=%dms",
            LOG_FIELD_CORRELATION_ID, cid,
            LOG_FIELD_ENDPOINT, endpoint,
            LOG_FIELD_STATUS_CODE, response.status_code,
            LOG_FIELD_DURATION_MS, duration_ms,
        )

        # Parse body (best-effort)
        try:
            body: Dict[str, Any] = response.json()
        except ValueError:
            body = {"_raw": response.text}

        # Raise on non-2xx
        try:
            raise_for_ejar_status(
                response.status_code,
                body,
                correlation_id=cid,
                company_id=self._company_id,
                endpoint=endpoint,
            )
        except (EjarServerError, EjarRateLimitError, EjarNetworkError) as exc:
            self._circuit_record_failure(exc)
            raise
        except EjarAuthError:
            # Invalidate cached credentials so next attempt re-resolves
            EjarAuthService.invalidate_cache(self._company_id)
            raise

        self._circuit_record_success()
        return body

    # ------------------------------------------------------------------
    # Convenience wrappers
    # ------------------------------------------------------------------

    def _get(self, endpoint: str, *, correlation_id: Optional[str] = None,
             params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._make_request("GET", endpoint, correlation_id=correlation_id, params=params)

    def _post(self, endpoint: str, body: Dict[str, Any], *,
              correlation_id: Optional[str] = None,
              idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        return self._make_request(
            "POST", endpoint,
            json_body=body,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    def _patch(self, endpoint: str, body: Dict[str, Any], *,
               correlation_id: Optional[str] = None,
               idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        return self._make_request(
            "PATCH", endpoint,
            json_body=body,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    def _delete(self, endpoint: str, *,
                correlation_id: Optional[str] = None,
                idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        return self._make_request(
            "DELETE", endpoint,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    def _upload(self, endpoint: str, files: Dict[str, Any], *,
                correlation_id: Optional[str] = None,
                idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        return self._make_request(
            "POST", endpoint,
            files=files,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            timeout=UPLOAD_TIMEOUT,
        )

    # ==================================================================
    # ECRS API — Contracts
    # ==================================================================

    def create_contract(
        self,
        attributes: Dict[str, Any],
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        POST /contracts
        Create a new draft contract on Ejar.

        Args:
            attributes: JSON API attributes dict for the contract.
                        See Ejar spec: contract_type, sub_type, start_date,
                        end_date, number_of_years, use_type, etc.

        Returns:
            Parsed response body (JSON API format).
        """
        cid = correlation_id or str(uuid.uuid4())
        ikey = self._build_idempotency_key(
            "create_contract",
            self._company_id,
            attributes.get("contract_start_date", ""),
            attributes.get("contract_end_date", ""),
            attributes.get("contract_type", ""),
        )
        body = {"data": {"type": "contracts", "attributes": attributes}}
        return self._post(EP_CONTRACTS, body, correlation_id=cid, idempotency_key=ikey)

    def get_contract(
        self,
        contract_id: str,
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """GET /contracts/{contract_id}"""
        ep = EP_CONTRACT.format(contract_id=contract_id)
        return self._get(ep, correlation_id=correlation_id)

    def list_contracts(
        self,
        *,
        page: int = 1,
        page_size: int = PAGE_SIZE,
        correlation_id: Optional[str] = None,
        **filters: Any,
    ) -> Dict[str, Any]:
        """
        GET /contracts  — paginated list.

        Additional Ejar filter params can be passed as kwargs
        (e.g., status="active", contract_type="residential").
        """
        params = {"page[number]": page, "page[size]": page_size, **filters}
        return self._get(EP_CONTRACTS, correlation_id=correlation_id, params=params)

    def get_contract_status(
        self,
        *,
        id_number: Optional[str] = None,
        contract_number: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """GET /contracts/contract_status — look up by ID number or contract number."""
        params: Dict[str, Any] = {}
        if id_number:
            params["id_number"] = id_number
        if contract_number:
            params["contract_number"] = contract_number
        return self._get(EP_CONTRACT_STATUS, correlation_id=correlation_id, params=params)

    def submit_contract(
        self,
        contract_id: str,
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        POST /contracts/{contract_id}/submit
        Finalise and submit a draft contract for Ejar registration.
        """
        cid = correlation_id or str(uuid.uuid4())
        ep = EP_CONTRACT_SUBMIT.format(contract_id=contract_id)
        ikey = self._build_idempotency_key("submit_contract", self._company_id, contract_id)
        return self._post(ep, {}, correlation_id=cid, idempotency_key=ikey)

    def download_contract_pdf(
        self,
        contract_id: str,
        *,
        correlation_id: Optional[str] = None,
    ) -> bytes:
        """
        GET /contracts/{contract_id}/download_pdf
        Returns raw PDF bytes.
        """
        ep = EP_CONTRACT_PDF.format(contract_id=contract_id)
        url = self._base_url + ep
        cid = correlation_id or str(uuid.uuid4())
        response = self._session.get(
            url,
            headers={HDR_CORRELATION_ID: cid},
            timeout=UPLOAD_TIMEOUT,
            stream=True,
        )
        raise_for_ejar_status(
            response.status_code,
            {},
            correlation_id=cid,
            company_id=self._company_id,
            endpoint=ep,
        )
        return response.content

    def get_contract_invoices(
        self,
        contract_id: str,
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """GET /contracts/{contract_id}/invoices"""
        ep = EP_CONTRACT_INVOICES.format(contract_id=contract_id)
        return self._get(ep, correlation_id=correlation_id)

    # ==================================================================
    # ECRS API — Contract Units
    # ==================================================================

    def attach_unit(
        self,
        contract_id: str,
        property_id: str,
        unit_id: str,
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        POST /contracts/{contract_id}/units
        Attach an existing Ejar portfolio unit to a draft contract.

        property_id and unit_id must be Ejar portfolio UUIDs (not Odoo IDs).
        """
        cid = correlation_id or str(uuid.uuid4())
        ep = EP_CONTRACT_UNITS.format(contract_id=contract_id)
        ikey = self._build_idempotency_key(
            "attach_unit", self._company_id, contract_id, unit_id, property_id,
        )
        body = {
            "data": {
                "contract_property": {"id": property_id},
                "contract_units": [{"id": unit_id}],
            }
        }
        return self._post(ep, body, correlation_id=cid, idempotency_key=ikey)

    def remove_unit(
        self,
        contract_id: str,
        unit_id: str,
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """DELETE /contracts/{contract_id}/units/{unit_id}"""
        cid = correlation_id or str(uuid.uuid4())
        ep = EP_CONTRACT_UNIT.format(contract_id=contract_id, unit_id=unit_id)
        ikey = self._build_idempotency_key("remove_unit", self._company_id, contract_id, unit_id)
        return self._delete(ep, correlation_id=cid, idempotency_key=ikey)

    def remove_property(
        self,
        contract_id: str,
        *,
        property_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        DELETE /contracts/{contract_id}/properties
        Remove all units of a specific property from a draft contract.
        """
        cid = correlation_id or str(uuid.uuid4())
        ep = EP_CONTRACT_PROPERTIES.format(contract_id=contract_id)
        ikey = self._build_idempotency_key(
            "remove_property", self._company_id, contract_id, property_id or ""
        )
        params = {"property_id": property_id} if property_id else None
        return self._make_request(
            "DELETE", ep,
            params=params,
            correlation_id=cid,
            idempotency_key=ikey,
        )

    def add_contract_unit_service(
        self,
        contract_id: str,
        unit_id: str,
        attributes: Dict[str, Any],
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /contracts/{contract_id}/contract_units/{unit_id}/contract_unit_services"""
        cid = correlation_id or str(uuid.uuid4())
        ep = EP_CONTRACT_UNIT_SERVICES.format(contract_id=contract_id, unit_id=unit_id)
        body = {"data": {"type": "contract_unit_services", "attributes": attributes}}
        return self._post(ep, body, correlation_id=cid)

    # ==================================================================
    # ECRS API — Parties
    # ==================================================================

    def add_party(
        self,
        contract_id: str,
        attributes: Dict[str, Any],
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        POST /contracts/{contract_id}/parties
        Add a lessor, tenant, or representative party to a draft contract.

        attributes must contain: role, protect_identity, is_representative,
        _entity_id, _entity_type (prefixed keys are popped into relationships).
        """
        cid = correlation_id or str(uuid.uuid4())
        ep = EP_CONTRACT_PARTIES.format(contract_id=contract_id)

        entity_id = attributes.pop("_entity_id", "")
        entity_type = attributes.pop("_entity_type", "individual_entities")

        ikey = self._build_idempotency_key(
            "add_party", self._company_id, contract_id,
            attributes.get("role", ""),
            entity_id,
        )
        body = {
            "data": {
                "type": "contract_parties",
                "attributes": attributes,
                "relationships": {
                    "entity": {
                        "data": {"id": entity_id, "type": entity_type}
                    }
                },
            }
        }
        return self._post(ep, body, correlation_id=cid, idempotency_key=ikey)

    def update_party(
        self,
        contract_id: str,
        party_id: str,
        attributes: Dict[str, Any],
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """PATCH /contracts/{contract_id}/parties/{party_id}"""
        cid = correlation_id or str(uuid.uuid4())
        ep = EP_CONTRACT_PARTY.format(contract_id=contract_id, party_id=party_id)
        ikey = self._build_idempotency_key(
            "update_party", self._company_id, contract_id, party_id
        )
        body = {
            "data": {
                "type": "contract_parties",
                "id": party_id,
                "attributes": attributes,
            }
        }
        return self._patch(ep, body, correlation_id=cid, idempotency_key=ikey)

    def delete_party(
        self,
        contract_id: str,
        party_id: str,
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """DELETE /contracts/{contract_id}/parties/{party_id}"""
        cid = correlation_id or str(uuid.uuid4())
        ep = EP_CONTRACT_PARTY.format(contract_id=contract_id, party_id=party_id)
        ikey = self._build_idempotency_key(
            "delete_party", self._company_id, contract_id, party_id
        )
        return self._delete(ep, correlation_id=cid, idempotency_key=ikey)

    # ==================================================================
    # ECRS API — Proxy Documents (representative parties)
    # ==================================================================

    def upload_proxy_document(
        self,
        contract_id: str,
        party_id: str,
        file_content: bytes,
        filename: str,
        *,
        doc_type: str = "paper_poa",
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        POST /contracts/{contract_id}/parties/{party_id}/proxy_documents
        Upload power-of-attorney for a representative party.
        """
        cid = correlation_id or str(uuid.uuid4())
        ep = EP_PROXY_DOCUMENTS.format(contract_id=contract_id, party_id=party_id)
        ikey = self._build_idempotency_key(
            "upload_proxy_doc", self._company_id, contract_id, party_id,
            hashlib.sha256(file_content).hexdigest()[:16],
        )
        files = {
            "file": (filename, file_content, "application/pdf"),
            "document_type": (None, doc_type),
        }
        return self._upload(ep, files, correlation_id=cid, idempotency_key=ikey)

    def delete_proxy_document(
        self,
        contract_id: str,
        party_id: str,
        doc_id: str,
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """DELETE /contracts/{contract_id}/parties/{party_id}/proxy_documents/{doc_id}"""
        cid = correlation_id or str(uuid.uuid4())
        ep = EP_PROXY_DOCUMENT.format(
            contract_id=contract_id, party_id=party_id, doc_id=doc_id
        )
        return self._delete(ep, correlation_id=cid)

    # ==================================================================
    # ECRS API — Signed Documents
    # ==================================================================

    def upload_signed_document(
        self,
        contract_id: str,
        file_content: bytes,
        filename: str,
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        POST /contracts/{contract_id}/signed_documents
        Upload the signed contract PDF.
        """
        cid = correlation_id or str(uuid.uuid4())
        ep = EP_SIGNED_DOCUMENTS.format(contract_id=contract_id)
        ikey = self._build_idempotency_key(
            "upload_signed_doc", self._company_id, contract_id,
            hashlib.sha256(file_content).hexdigest()[:16],
        )
        files = {"file": (filename, file_content, "application/pdf")}
        return self._upload(ep, files, correlation_id=cid, idempotency_key=ikey)

    def delete_signed_document(
        self,
        contract_id: str,
        doc_id: str,
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """DELETE /contracts/{contract_id}/signed_documents/{doc_id}"""
        cid = correlation_id or str(uuid.uuid4())
        ep = EP_SIGNED_DOCUMENT.format(contract_id=contract_id, doc_id=doc_id)
        return self._delete(ep, correlation_id=cid)

    # ==================================================================
    # ECRS API — Financial Information
    # ==================================================================

    def add_financial_information(
        self,
        contract_id: str,
        attributes: Dict[str, Any],
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        POST /contracts/{contract_id}/financial_information
        Set rent amount, billing type, payment option, IBAN details.
        """
        cid = correlation_id or str(uuid.uuid4())
        ep = EP_FINANCIAL_INFO.format(contract_id=contract_id)
        ikey = self._build_idempotency_key(
            "add_financial_info", self._company_id, contract_id
        )
        body = {"data": {"type": "financial_informations", "attributes": attributes}}
        return self._post(ep, body, correlation_id=cid, idempotency_key=ikey)

    def add_rental_fee(
        self,
        contract_id: str,
        attributes: Dict[str, Any],
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        POST /contracts/{contract_id}/rental_fee
        Add brokerage fee information.
        """
        cid = correlation_id or str(uuid.uuid4())
        ep = EP_RENTAL_FEE.format(contract_id=contract_id)
        ikey = self._build_idempotency_key(
            "add_rental_fee", self._company_id, contract_id
        )
        body = {"data": {"type": "rental_fees", "attributes": attributes}}
        return self._post(ep, body, correlation_id=cid, idempotency_key=ikey)

    # ==================================================================
    # ECRS API — Contract Terms
    # ==================================================================

    def add_contract_terms(
        self,
        contract_id: str,
        attributes: Dict[str, Any],
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /contracts/{contract_id}/contract_terms"""
        cid = correlation_id or str(uuid.uuid4())
        ep = EP_CONTRACT_TERMS.format(contract_id=contract_id)
        body = {"data": {"type": "contract_terms", "attributes": attributes}}
        return self._post(ep, body, correlation_id=cid)

    def add_custom_terms(
        self,
        contract_id: str,
        attributes: Dict[str, Any],
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /contracts/{contract_id}/custom_terms"""
        cid = correlation_id or str(uuid.uuid4())
        ep = EP_CUSTOM_TERMS.format(contract_id=contract_id)
        body = {"data": {"type": "custom_terms", "attributes": attributes}}
        return self._post(ep, body, correlation_id=cid)

    # ==================================================================
    # ECRS API — Properties & Units Portfolio
    # ==================================================================

    def create_property(
        self,
        attributes: Dict[str, Any],
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /properties"""
        cid = correlation_id or str(uuid.uuid4())
        ikey = self._build_idempotency_key(
            "create_property", self._company_id,
            attributes.get("deed_number", ""),
        )
        body = {"data": {"type": "properties", "attributes": attributes}}
        return self._post(EP_PROPERTIES, body, correlation_id=cid, idempotency_key=ikey)

    def get_property(
        self,
        property_id: str,
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """GET /properties/{property_id}"""
        ep = EP_PROPERTY.format(property_id=property_id)
        return self._get(ep, correlation_id=correlation_id)

    def create_property_unit(
        self,
        property_id: str,
        attributes: Dict[str, Any],
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /properties/{property_id}/units"""
        cid = correlation_id or str(uuid.uuid4())
        ep = EP_PROPERTY_UNITS.format(property_id=property_id)
        ikey = self._build_idempotency_key(
            "create_property_unit", self._company_id, property_id,
            attributes.get("unit_number", ""),
        )
        body = {"data": {"type": "units", "attributes": attributes}}
        return self._post(ep, body, correlation_id=cid, idempotency_key=ikey)

    def get_property_unit(
        self,
        property_id: str,
        unit_id: str,
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """GET /properties/{property_id}/units/{unit_id}"""
        ep = EP_PROPERTY_UNIT.format(property_id=property_id, unit_id=unit_id)
        return self._get(ep, correlation_id=correlation_id)

    def upload_ownership_document(
        self,
        property_id: str,
        file_content: bytes,
        filename: str,
        *,
        attributes: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /properties/{property_id}/ownership_documents"""
        cid = correlation_id or str(uuid.uuid4())
        ep = EP_OWNERSHIP_DOCUMENTS.format(property_id=property_id)
        ikey = self._build_idempotency_key(
            "upload_ownership_doc", self._company_id, property_id,
            hashlib.sha256(file_content).hexdigest()[:16],
        )
        files: Dict[str, Any] = {"file": (filename, file_content, "application/pdf")}
        if attributes:
            for k, v in attributes.items():
                files[k] = (None, str(v))
        return self._upload(ep, files, correlation_id=cid, idempotency_key=ikey)

    def add_ownership_document_owner(
        self,
        property_id: str,
        doc_id: str,
        attributes: Dict[str, Any],
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /properties/{property_id}/ownership_documents/{doc_id}/owners"""
        cid = correlation_id or str(uuid.uuid4())
        ep = EP_OWNERSHIP_DOCUMENT_OWNERS.format(property_id=property_id, doc_id=doc_id)
        body = {"data": {"type": "owners", "attributes": attributes}}
        return self._post(ep, body, correlation_id=cid)

    def upload_ownership_proxy_document(
        self,
        property_id: str,
        doc_id: str,
        file_content: bytes,
        filename: str,
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /properties/{property_id}/ownership_documents/{doc_id}/proxy_documents"""
        cid = correlation_id or str(uuid.uuid4())
        ep = EP_OWNERSHIP_PROXY_DOCUMENTS.format(property_id=property_id, doc_id=doc_id)
        files = {"file": (filename, file_content, "application/pdf")}
        return self._upload(ep, files, correlation_id=cid)

    # ==================================================================
    # ECRS API — Individual Entities
    # ==================================================================

    def create_individual_entity(
        self,
        attributes: Dict[str, Any],
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        POST /individual_entities
        Register or look up an individual (lessor/tenant/representative).
        """
        cid = correlation_id or str(uuid.uuid4())
        ikey = self._build_idempotency_key(
            "create_individual_entity", self._company_id,
            attributes.get("id_number", ""),
            attributes.get("id_type", ""),
        )
        body = {"data": {"type": "individual_entities", "attributes": attributes}}
        return self._post(EP_INDIVIDUAL_ENTITIES, body, correlation_id=cid, idempotency_key=ikey)

    def get_individual_entity(
        self,
        entity_id: str,
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """GET /individual_entities/{entity_id}"""
        ep = EP_INDIVIDUAL_ENTITY.format(entity_id=entity_id)
        return self._get(ep, correlation_id=correlation_id)

    # ==================================================================
    # ECRS API — Organization Entities
    # ==================================================================

    def create_organization_entity(
        self,
        attributes: Dict[str, Any],
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /organization_entities"""
        cid = correlation_id or str(uuid.uuid4())
        ikey = self._build_idempotency_key(
            "create_org_entity", self._company_id,
            attributes.get("cr_number", ""),
            attributes.get("unified_number", ""),
        )
        body = {"data": {"type": "organization_entities", "attributes": attributes}}
        return self._post(EP_ORGANIZATION_ENTITIES, body, correlation_id=cid, idempotency_key=ikey)

    def get_organization_entity(
        self,
        entity_id: str,
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """GET /organization_entities/{entity_id}"""
        ep = EP_ORGANIZATION_ENTITY.format(entity_id=entity_id)
        return self._get(ep, correlation_id=correlation_id)

    # ==================================================================
    # ECRS API — Brokerage Agreements
    # ==================================================================

    def create_brokerage_agreement(
        self,
        attributes: Dict[str, Any],
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /brokerage_agreements"""
        cid = correlation_id or str(uuid.uuid4())
        body = {"data": {"type": "brokerage_agreements", "attributes": attributes}}
        return self._post(EP_BROKERAGE_AGREEMENTS, body, correlation_id=cid)

    # ==================================================================
    # ECRS API — Office Wallet
    # ==================================================================

    def recharge_office_wallet(
        self,
        attributes: Dict[str, Any],
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /office/wallet/recharge"""
        cid = correlation_id or str(uuid.uuid4())
        body = {"data": {"type": "wallet_recharges", "attributes": attributes}}
        return self._post(EP_OFFICE_WALLET, body, correlation_id=cid)

    # ==================================================================
    # Context manager support
    # ==================================================================

    def __enter__(self) -> "EjarApiClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        """Release the underlying connection pool."""
        self._session.close()

    def __repr__(self) -> str:
        return (
            f"EjarApiClient("
            f"company_id={self._company_id}, "
            f"environment={self._environment!r}, "
            f"fingerprint={self._credentials.fingerprint!r})"
        )
