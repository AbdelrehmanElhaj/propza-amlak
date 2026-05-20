"""
Ejar ECRS API — Authentication Service
========================================
Per-company credential resolution with in-memory TTL caching.

Credential lookup order (per company_id):
  1. propza.ejar.api.token model (encrypted, preferred)
  2. ir.config_parameter company-scoped keys:
       ejar.api.key.company_{id}
       ejar.api.secret.company_{id}
       ejar.api.environment.company_{id}
  3. ir.config_parameter global fallback keys:
       ejar.api.key
       ejar.api.secret
       ejar.api.environment

EjarCredentials.to_auth_header() produces the Basic auth value
required by Ejar ECRS: Base64(api_key:api_secret_key).

SECURITY NOTES:
- Credentials never appear in logs — only the fingerprint (SHA256[:12]).
- Cache entries expire after TTL_SECONDS to limit stale-credential windows.
- invalidate_cache() must be called after credential rotation.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from .constants import ENV_UAT, ENV_PRODUCTION, VALID_ENVIRONMENTS
from .exceptions import EjarConfigurationError, EjarTokenError, EjarTokenExpiredError

_logger = logging.getLogger(__name__)

# Seconds before a cached credential entry is considered stale
_TTL_SECONDS: int = 300


# ---------------------------------------------------------------------------
# Credential Value Object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EjarCredentials:
    """
    Immutable credential bundle for one company's Ejar API access.

    Never store or log api_key / api_secret in plaintext.
    Use `fingerprint` for audit trails and log lines.
    """

    api_key: str
    api_secret: str
    company_id: int
    environment: str = ENV_UAT

    def __post_init__(self) -> None:
        if not self.api_key:
            raise EjarConfigurationError(
                "api_key is empty",
                company_id=self.company_id,
            )
        if not self.api_secret:
            raise EjarConfigurationError(
                "api_secret is empty",
                company_id=self.company_id,
            )
        if self.environment not in VALID_ENVIRONMENTS:
            raise EjarConfigurationError(
                f"Unknown environment {self.environment!r}. "
                f"Valid: {sorted(VALID_ENVIRONMENTS)}",
                company_id=self.company_id,
            )

    # ------------------------------------------------------------------
    # Auth header
    # ------------------------------------------------------------------

    def to_auth_header(self) -> str:
        """
        Produce the HTTP Authorization header value for Ejar ECRS.

        Format (per spec): Basic Base64(api_key:api_secret_key)
        """
        raw = f"{self.api_key}:{self.api_secret}".encode("utf-8")
        encoded = base64.b64encode(raw).decode("ascii")
        return f"Basic {encoded}"

    # ------------------------------------------------------------------
    # Fingerprint (safe for logs / audit)
    # ------------------------------------------------------------------

    @property
    def fingerprint(self) -> str:
        """
        First 12 hex characters of SHA-256(api_key).

        Safe to include in log lines — cannot be used to reconstruct the key.
        """
        digest = hashlib.sha256(self.api_key.encode("utf-8")).hexdigest()
        return digest[:12]

    # ------------------------------------------------------------------
    # Prevent accidental repr leakage
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"EjarCredentials("
            f"company_id={self.company_id}, "
            f"environment={self.environment!r}, "
            f"fingerprint={self.fingerprint!r})"
        )

    def __str__(self) -> str:
        return repr(self)


# ---------------------------------------------------------------------------
# Thread-safe TTL cache
# ---------------------------------------------------------------------------


@dataclass
class _CacheEntry:
    credentials: EjarCredentials
    expires_at: float  # monotonic clock seconds


class _CredentialCache:
    """
    In-process, thread-safe cache for EjarCredentials keyed by company_id.

    Uses time.monotonic() so it is immune to wall-clock adjustments.
    """

    def __init__(self, ttl_seconds: int = _TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._store: Dict[int, _CacheEntry] = {}

    def get(self, company_id: int) -> Optional[EjarCredentials]:
        with self._lock:
            entry = self._store.get(company_id)
            if entry is None:
                return None
            if time.monotonic() >= entry.expires_at:
                del self._store[company_id]
                return None
            return entry.credentials

    def set(self, credentials: EjarCredentials) -> None:
        with self._lock:
            self._store[credentials.company_id] = _CacheEntry(
                credentials=credentials,
                expires_at=time.monotonic() + self._ttl,
            )

    def invalidate(self, company_id: int) -> None:
        with self._lock:
            self._store.pop(company_id, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


# Module-level singleton shared across all EjarAuthService instances
_CACHE = _CredentialCache(ttl_seconds=_TTL_SECONDS)


# ---------------------------------------------------------------------------
# Auth Service
# ---------------------------------------------------------------------------


class EjarAuthService:
    """
    Resolves per-company Ejar credentials from Odoo configuration.

    Must be instantiated with the Odoo ``env`` object so it can read
    ir.config_parameter and the optional propza.ejar.api.token model.

    Usage::

        auth = EjarAuthService(self.env)
        creds = auth.get_credentials(company_id=7)
        headers = {"Authorization": creds.to_auth_header()}
    """

    def __init__(self, env: object) -> None:
        self._env = env

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_credentials(self, company_id: int) -> EjarCredentials:
        """
        Return resolved credentials for *company_id*.

        Hits the in-process cache first; falls back to Odoo models.
        Raises EjarConfigurationError / EjarTokenError / EjarTokenExpiredError.
        """
        cached = _CACHE.get(company_id)
        if cached is not None:
            _logger.debug(
                "Ejar credentials cache hit | company_id=%s fingerprint=%s",
                company_id,
                cached.fingerprint,
            )
            return cached

        creds = self._resolve(company_id)
        _CACHE.set(creds)
        _logger.info(
            "Ejar credentials resolved | company_id=%s environment=%s fingerprint=%s",
            company_id,
            creds.environment,
            creds.fingerprint,
        )
        return creds

    @staticmethod
    def invalidate_cache(company_id: int) -> None:
        """
        Remove cached credentials for *company_id*.

        Call this immediately after credential rotation so the next
        request picks up the new values.
        """
        _CACHE.invalidate(company_id)
        _logger.info("Ejar credential cache invalidated | company_id=%s", company_id)

    @staticmethod
    def clear_all_cache() -> None:
        """Flush the entire cache — use during testing or emergency re-auth."""
        _CACHE.clear()
        _logger.warning("Ejar credential cache cleared (all companies)")

    # ------------------------------------------------------------------
    # Resolution logic
    # ------------------------------------------------------------------

    def _resolve(self, company_id: int) -> EjarCredentials:
        """
        Try credential sources in priority order.

        1. propza.ejar.api.token Odoo model (encrypted at rest, preferred)
        2. Company-scoped ir.config_parameter keys
        3. Global ir.config_parameter fallback keys
        """
        # --- Source 1: encrypted token model ---
        creds = self._from_token_model(company_id)
        if creds is not None:
            return creds

        # --- Source 2: company-scoped config params ---
        creds = self._from_config_params(company_id, scoped=True)
        if creds is not None:
            return creds

        # --- Source 3: global config params (single-tenant fallback) ---
        creds = self._from_config_params(company_id, scoped=False)
        if creds is not None:
            return creds

        raise EjarConfigurationError(
            f"No Ejar API credentials configured for company {company_id}. "
            "Configure ejar.api.key.company_{id} in System Parameters or "
            "create a propza.ejar.api.token record.",
            company_id=company_id,
        )

    def _from_token_model(self, company_id: int) -> Optional[EjarCredentials]:
        """
        Read from propza.ejar.api.token if the model is installed.

        This model stores credentials AES-256-GCM encrypted.
        If the model does not exist (module not installed), return None silently.
        """
        try:
            Token = self._env.get("propza.ejar.api.token")
            if Token is None:
                return None

            token = Token.sudo().search(
                [("company_id", "=", company_id), ("active", "=", True)],
                limit=1,
                order="create_date desc",
            )
            if not token:
                return None

            # Check expiry if the model supports it
            if hasattr(token, "expires_at") and token.expires_at:
                import datetime
                if token.expires_at < datetime.datetime.now():
                    raise EjarTokenExpiredError(
                        f"Ejar token for company {company_id} expired at {token.expires_at}",
                        company_id=company_id,
                    )

            api_key = getattr(token, "api_key", None) or ""
            api_secret = getattr(token, "api_secret_key", None) or ""
            environment = getattr(token, "environment", ENV_UAT) or ENV_UAT

            if not api_key or not api_secret:
                _logger.warning(
                    "propza.ejar.api.token found for company %s but key/secret empty",
                    company_id,
                )
                return None

            return EjarCredentials(
                api_key=api_key,
                api_secret=api_secret,
                company_id=company_id,
                environment=environment,
            )

        except (EjarTokenExpiredError, EjarConfigurationError):
            raise
        except Exception as exc:
            _logger.warning(
                "Error reading propza.ejar.api.token for company %s: %s",
                company_id,
                exc,
            )
            return None

    def _from_config_params(
        self,
        company_id: int,
        *,
        scoped: bool,
    ) -> Optional[EjarCredentials]:
        """
        Read credentials from ir.config_parameter.

        If *scoped* is True, reads company-specific keys:
            ejar.api.key.company_{id}
            ejar.api.secret.company_{id}
            ejar.api.environment.company_{id}

        If *scoped* is False, reads global fallback keys:
            ejar.api.key
            ejar.api.secret
            ejar.api.environment
        """
        try:
            params = self._env["ir.config_parameter"].sudo()

            if scoped:
                key_param = f"ejar.api.key.company_{company_id}"
                secret_param = f"ejar.api.secret.company_{company_id}"
                env_param = f"ejar.api.environment.company_{company_id}"
            else:
                key_param = "ejar.api.key"
                secret_param = "ejar.api.secret"
                env_param = "ejar.api.environment"

            api_key = params.get_param(key_param, "")
            api_secret = params.get_param(secret_param, "")
            environment = params.get_param(env_param, ENV_UAT)

            if not api_key or not api_secret:
                return None

            if environment not in VALID_ENVIRONMENTS:
                _logger.warning(
                    "Invalid environment %r in %s — defaulting to %s",
                    environment,
                    env_param,
                    ENV_UAT,
                )
                environment = ENV_UAT

            return EjarCredentials(
                api_key=api_key,
                api_secret=api_secret,
                company_id=company_id,
                environment=environment,
            )

        except Exception as exc:
            _logger.warning(
                "Error reading ir.config_parameter for company %s (scoped=%s): %s",
                company_id,
                scoped,
                exc,
            )
            return None

    # ------------------------------------------------------------------
    # Convenience: environment resolution without full credentials
    # ------------------------------------------------------------------

    def get_environment(self, company_id: int) -> str:
        """
        Return the configured environment for *company_id* without
        triggering a full credential resolution (uses cache if warm).
        """
        cached = _CACHE.get(company_id)
        if cached is not None:
            return cached.environment

        # Light read — just the env param
        try:
            params = self._env["ir.config_parameter"].sudo()
            env = params.get_param(
                f"ejar.api.environment.company_{company_id}",
                params.get_param("ejar.api.environment", ENV_UAT),
            )
            return env if env in VALID_ENVIRONMENTS else ENV_UAT
        except Exception:
            return ENV_UAT
