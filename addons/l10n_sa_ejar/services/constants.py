"""
Ejar ECRS API — Constants, Enums, and Configuration
=====================================================
All values sourced from the official Ejar ECRS API specification.

Endpoint reference:
  UAT Ejar:  https://uat-ejar3.housingapps.sa/api/v1/ecrs
  UAT Moho:  https://integration-gw.housingapps.sa/nhc/uat/v1/ejar/ecrs
  Auth:      HTTP Basic — Base64(api_key:api_secret_key)
  Format:    JSON API spec (data.attributes envelope)
"""

# ---------------------------------------------------------------------------
# Environments
# ---------------------------------------------------------------------------

ENV_UAT = "uat"
ENV_PRODUCTION = "production"

VALID_ENVIRONMENTS = {ENV_UAT, ENV_PRODUCTION}

# Base URLs indexed by environment — use Ejar-direct URLs (not Moho gateway)
# for all production contract operations.
BASE_URLS = {
    ENV_UAT: "https://uat-ejar3.housingapps.sa/api/v1/ecrs",
    ENV_PRODUCTION: "https://ejar3.housingapps.sa/api/v1/ecrs",
}

# NHC/Moho integration gateway (alternative routing — same endpoints, different host)
MOHO_BASE_URLS = {
    ENV_UAT: "https://integration-gw.housingapps.sa/nhc/uat/v1/ejar/ecrs",
    ENV_PRODUCTION: "https://integration-gw.housingapps.sa/nhc/v1/ejar/ecrs",
}

# ---------------------------------------------------------------------------
# Timeouts  (seconds)
# ---------------------------------------------------------------------------

CONNECT_TIMEOUT = 10     # Time to establish TCP connection
READ_TIMEOUT = 45        # Time to receive the first byte of response body
UPLOAD_READ_TIMEOUT = 120  # Extended timeout for file/PDF upload operations

DEFAULT_TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)
UPLOAD_TIMEOUT = (CONNECT_TIMEOUT, UPLOAD_READ_TIMEOUT)

# ---------------------------------------------------------------------------
# Retry Configuration
# ---------------------------------------------------------------------------

MAX_RETRIES = 5
RETRY_BACKOFF_FACTOR = 1.5   # sleep = backoff_factor * (2 ** (attempt - 1))
RETRY_BACKOFF_MAX = 120      # Cap backoff at 2 minutes
RETRY_JITTER_RANGE = 5       # ± seconds of random jitter added to each backoff

# HTTP status codes that warrant a retry (transient server/infra errors only)
RETRY_ON_STATUS = frozenset({429, 500, 502, 503, 504})

# HTTP methods safe to retry (all ECRS methods are idempotent via idempotency key)
RETRY_ON_METHODS = frozenset({"GET", "POST", "PATCH", "DELETE"})

# HTTP status codes that must NOT be retried (permanent/client errors)
NO_RETRY_ON_STATUS = frozenset({400, 401, 403, 404, 422})

# ---------------------------------------------------------------------------
# HTTP Headers
# ---------------------------------------------------------------------------

HDR_CONTENT_TYPE = "Content-Type"
HDR_ACCEPT = "Accept"
HDR_AUTHORIZATION = "Authorization"
HDR_CORRELATION_ID = "X-Correlation-ID"
HDR_IDEMPOTENCY_KEY = "X-Idempotency-Key"
HDR_RETRY_AFTER = "Retry-After"

CONTENT_TYPE_JSON = "application/json; charset=utf-8"
CONTENT_TYPE_MULTIPART = "multipart/form-data"

# ---------------------------------------------------------------------------
# API Endpoint Path Templates
# ---------------------------------------------------------------------------

# Contracts
EP_CONTRACTS = "/contracts"
EP_CONTRACT = "/contracts/{contract_id}"
EP_CONTRACT_SUBMIT = "/contracts/{contract_id}/submit"
EP_CONTRACT_STATUS = "/contracts/contract_status"
EP_CONTRACT_PDF = "/contracts/{contract_id}/download_pdf"
EP_CONTRACT_INVOICES = "/contracts/{contract_id}/invoices"

# Units / Property
EP_CONTRACT_UNITS = "/contracts/{contract_id}/units"
EP_CONTRACT_UNIT = "/contracts/{contract_id}/units/{unit_id}"
EP_CONTRACT_PROPERTIES = "/contracts/{contract_id}/properties"

# Parties
EP_CONTRACT_PARTIES = "/contracts/{contract_id}/parties"
EP_CONTRACT_PARTY = "/contracts/{contract_id}/parties/{party_id}"

# Proxy documents (for representative parties)
EP_PROXY_DOCUMENTS = "/contracts/{contract_id}/parties/{party_id}/proxy_documents"
EP_PROXY_DOCUMENT = "/contracts/{contract_id}/parties/{party_id}/proxy_documents/{doc_id}"

# Signed documents
EP_SIGNED_DOCUMENTS = "/contracts/{contract_id}/signed_documents"
EP_SIGNED_DOCUMENT = "/contracts/{contract_id}/signed_documents/{doc_id}"

# Financial
EP_FINANCIAL_INFO = "/contracts/{contract_id}/financial_information"
EP_RENTAL_FEE = "/contracts/{contract_id}/rental_fee"
EP_CONTRACT_UNIT_SERVICES = (
    "/contracts/{contract_id}/contract_units/{unit_id}/contract_unit_services"
)

# Terms
EP_CONTRACT_TERMS = "/contracts/{contract_id}/contract_terms"
EP_CUSTOM_TERMS = "/contracts/{contract_id}/custom_terms"

# Properties & Units Portfolio (pre-contract registration)
EP_PROPERTIES = "/properties"
EP_PROPERTY = "/properties/{property_id}"
EP_PROPERTY_UNITS = "/properties/{property_id}/units"
EP_PROPERTY_UNIT = "/properties/{property_id}/units/{unit_id}"
EP_OWNERSHIP_DOCUMENTS = "/properties/{property_id}/ownership_documents"
EP_OWNERSHIP_DOCUMENT = "/properties/{property_id}/ownership_documents/{doc_id}"
EP_OWNERSHIP_DOCUMENT_OWNERS = "/properties/{property_id}/ownership_documents/{doc_id}/owners"
EP_OWNERSHIP_PROXY_DOCUMENTS = (
    "/properties/{property_id}/ownership_documents/{doc_id}/proxy_documents"
)

# Entities
EP_INDIVIDUAL_ENTITIES = "/individual_entities"
EP_INDIVIDUAL_ENTITY = "/individual_entities/{entity_id}"
EP_ORGANIZATION_ENTITIES = "/organization_entities"
EP_ORGANIZATION_ENTITY = "/organization_entities/{entity_id}"

# Brokerage
EP_BROKERAGE_AGREEMENTS = "/brokerage_agreements"
EP_OFFICE_WALLET = "/office/wallet/recharge"

# ---------------------------------------------------------------------------
# Ejar Pagination
# ---------------------------------------------------------------------------

PAGE_SIZE = 50   # Ejar returns max 50 contracts per page

# ---------------------------------------------------------------------------
# Contract Types
# ---------------------------------------------------------------------------

class ContractType:
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    ALL = {RESIDENTIAL, COMMERCIAL}


class ContractSubType:
    MAIN = "main"
    RENEWAL = "renewal"
    SUBLEASE = "sublease"


class ContractState:
    DRAFT = "draft"
    SUBMITTED = "submitted"
    REGISTERED = "registered"
    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"
    REJECTED = "rejected"
    ARCHIVED = "archived"

    # States that accept further mutations
    MUTABLE_STATES = {DRAFT}

    # Terminal states — no further API calls meaningful
    TERMINAL_STATES = {TERMINATED, REJECTED, ARCHIVED}

    # States that can be polled for progress
    PENDING_STATES = {SUBMITTED, REGISTERED}


# ---------------------------------------------------------------------------
# Party Roles & Entity Types
# ---------------------------------------------------------------------------

class PartyRole:
    LESSOR = "lessor"
    TENANT = "tenant"
    LESSOR_REPRESENTATIVE = "lessor_representative"
    TENANT_REPRESENTATIVE = "tenant_representative"
    ALL = {LESSOR, TENANT, LESSOR_REPRESENTATIVE, TENANT_REPRESENTATIVE}

    # Roles that require proxy documents (power of attorney)
    REQUIRES_PROXY_DOCUMENT = {LESSOR_REPRESENTATIVE, TENANT_REPRESENTATIVE}


class EntityType:
    INDIVIDUAL = "individual_entities"
    ORGANIZATION = "organization_entities"
    ALL = {INDIVIDUAL, ORGANIZATION}


# ---------------------------------------------------------------------------
# Identity / ID Types
# ---------------------------------------------------------------------------

class IdType:
    NATIONAL_ID = "national_id"    # Saudi NID — starts with 1, 10 digits
    IQAMA = "iqama"                # Resident permit — starts with 2, 10 digits
    PASSPORT = "passport"          # Foreign passport
    GCC_ID = "gcc_id"              # GCC national ID
    ALL = {NATIONAL_ID, IQAMA, PASSPORT, GCC_ID}

    # Patterns for pre-validation
    PATTERNS = {
        NATIONAL_ID: r"^1\d{9}$",
        IQAMA: r"^2\d{9}$",
    }


# ---------------------------------------------------------------------------
# Document Types
# ---------------------------------------------------------------------------

class ProxyDocumentType:
    E_POA = "e_poa"                # Electronic power of attorney (Najiz)
    PAPER_POA = "paper_poa"        # Paper power of attorney
    COURT_ORDER = "court_order"
    ALL = {E_POA, PAPER_POA, COURT_ORDER}


class OwnershipDocumentType:
    PAPER_TITLE_DEED = "paper_title_deed"
    ELECTRONIC_TITLE_DEED = "electronic_title_deed"
    USUFRUCT_CONTRACT = "usufruct_contract"
    INHERITANCE_DOCUMENT = "inheritance_document"
    ALL = {
        PAPER_TITLE_DEED,
        ELECTRONIC_TITLE_DEED,
        USUFRUCT_CONTRACT,
        INHERITANCE_DOCUMENT,
    }


# ---------------------------------------------------------------------------
# Unit / Property Enumerations
# ---------------------------------------------------------------------------

class UnitType:
    VILLA = "villa"
    APARTMENT = "apartment"
    FLOOR = "floor"
    ROOM = "room"
    OFFICE = "office"
    STORE = "store"
    WAREHOUSE = "warehouse"
    LAND = "land"
    ALL = {VILLA, APARTMENT, FLOOR, ROOM, OFFICE, STORE, WAREHOUSE, LAND}


class PropertyType:
    BUILDING = "building"
    VILLA = "villa"
    FLOOR = "floor"
    LAND = "land"
    COMMERCIAL_COMPLEX = "commercial_complex"
    ALL = {BUILDING, VILLA, FLOOR, LAND, COMMERCIAL_COMPLEX}


class PropertyUsage:
    RESIDENTIAL_FAMILIES = "residential_families"
    RESIDENTIAL_SINGLES = "residential_singles"
    COMMERCIAL = "commercial"
    INDUSTRIAL = "industrial"
    ALL = {RESIDENTIAL_FAMILIES, RESIDENTIAL_SINGLES, COMMERCIAL, INDUSTRIAL}


class UnitFinishing:
    FINISHED = "finished"
    SEMI_FINISHED = "semi_finished"
    UNFINISHED = "unfinished"
    ALL = {FINISHED, SEMI_FINISHED, UNFINISHED}


class FurnishType:
    FURNISH_NEW = "furnish_new"
    FURNISH_OLD = "furnish_old"
    UNFURNISHED = "unfurnished"
    ALL = {FURNISH_NEW, FURNISH_OLD, UNFURNISHED}


class UnitDirection:
    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"
    ALL = {NORTH, SOUTH, EAST, WEST}


# ---------------------------------------------------------------------------
# Financial / Payment Enumerations
# ---------------------------------------------------------------------------

class BillingType:
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMI_ANNUAL = "biannual"
    ANNUAL = "annual"
    ALL = {MONTHLY, QUARTERLY, SEMI_ANNUAL, ANNUAL}


class PaymentOption:
    MADA = "mada"
    SADAD = "sadad"
    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    ALL = {MADA, SADAD, CASH, BANK_TRANSFER}


class IbanBelongsTo:
    LESSOR = "lessor"
    TENANT = "tenant"
    ALL = {LESSOR, TENANT}


class BrokerageFeePaidBy:
    LESSOR = "lessor"
    TENANT = "tenant"
    BROKERAGE_OFFICE = "brokerage_office"
    ALL = {LESSOR, TENANT, BROKERAGE_OFFICE}


class UtilitiesPaymentType:
    MONTHLY_FIXED = "monthly_fixed"
    BY_CONSUMPTION = "by_consumption"
    INCLUDED_IN_RENT = "included_in_rent"
    ALL = {MONTHLY_FIXED, BY_CONSUMPTION, INCLUDED_IN_RENT}


class EjarFeesPaidBy:
    BROKERAGE_OFFICE = "brokerage_office"
    LESSOR = "lessor"
    TENANT = "tenant"
    ALL = {BROKERAGE_OFFICE, LESSOR, TENANT}


# ---------------------------------------------------------------------------
# Saudi Regulatory Constants
# ---------------------------------------------------------------------------

SAUDI_VAT_RATE = 15                    # 15% VAT (effective 2020)
CURRENCY_SAR = "SAR"                   # Only accepted currency
MAX_BROKERAGE_FEE_PCT = "2.5"          # RERA cap: 2.5% of annual rent
RIYADH_RENT_FREEZE_UNTIL = "2030-09-01"  # Ministerial decision — no rent increases

# Saudi National Address field lengths
NATIONAL_ADDRESS_LETTERS = 4
NATIONAL_ADDRESS_DIGITS = 4
POSTAL_CODE_LENGTH = 5
ADDITIONAL_NUMBER_LENGTH = 4
BUILDING_NUMBER_MAX_LENGTH = 4

# Identity number lengths
SAUDI_NID_LENGTH = 10
IQAMA_LENGTH = 10
SAUDI_IBAN_LENGTH = 24                 # SA + 2 check + 18 alphanumeric
CR_NUMBER_LENGTH = 10
UNIFIED_NUMBER_LENGTH = 10
VAT_NUMBER_LENGTH = 15

# ---------------------------------------------------------------------------
# Audit / Logging
# ---------------------------------------------------------------------------

LOG_FIELD_CORRELATION_ID = "correlation_id"
LOG_FIELD_COMPANY_ID = "company_id"
LOG_FIELD_METHOD = "method"
LOG_FIELD_ENDPOINT = "endpoint"
LOG_FIELD_STATUS_CODE = "status_code"
LOG_FIELD_DURATION_MS = "duration_ms"
LOG_FIELD_IDEMPOTENCY_KEY = "idempotency_key"
LOG_FIELD_ATTEMPT = "attempt"
LOG_FIELD_CONTRACT_ID = "contract_id"
LOG_FIELD_KEY_FINGERPRINT = "key_fingerprint"

# Fields that must NEVER appear in logs
SENSITIVE_FIELDS = frozenset({
    "api_key", "api_secret", "api_secret_key",
    "iban_number", "swift_code",
    "id_number", "national_id", "iqama",
    "date_of_birth",
})

# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

CB_FAILURE_THRESHOLD = 5      # Open circuit after N consecutive failures
CB_RECOVERY_TIMEOUT = 60      # Seconds before moving to HALF-OPEN
CB_SUCCESS_THRESHOLD = 2      # HALF-OPEN: successes needed to close circuit

# ---------------------------------------------------------------------------
# Idempotency Key Windows
# ---------------------------------------------------------------------------

IDEMPOTENCY_WINDOW_HOURS = 24  # Keys expire after 24 hours (Ejar's dedup window)
