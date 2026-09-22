"""System policies and access control (K5a).

Defines named systems (consumers), each with:
- ``mask_types``: which PII types to mask for this system.
- ``demask_allowed``: whether this system may demask (restore originals).
- ``enabled``: whether the system is currently allowed to use the service.

Access (``enabled``/``demask_allowed``) is re-checked on every request so a
revocation takes effect immediately, even for already-created pairs (D05).
The masking parameter set (``mask_types``) is fixed at pair creation and stored
with the pair, so changing it does not rewrite existing pairs (immutable).

Two profiles (D07):
- ``demo-secure``: multiple systems authenticated by API key, individual
  policies, foreign demasking forbidden.
- ``evaluation-open``: a single open system for the stand, no API key.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class AccessDeniedError(Exception):
    """System not enabled or demasking forbidden (HTTP 403)."""


class UnauthorizedError(Exception):
    """No valid system credentials (HTTP 401)."""


@dataclass(frozen=True)
class SystemPolicy:
    name: str
    api_key: str | None = None
    mask_types: frozenset[str] = frozenset()
    demask_allowed: bool = False
    enabled: bool = True


@dataclass
class PolicyConfig:
    """Validated set of system policies."""

    systems: dict[str, SystemPolicy] = field(default_factory=dict)
    open_system: str | None = None

    def authenticate(self, api_key: str | None) -> str:
        """Return the authenticated system name or raise UnauthorizedError."""
        if api_key is None:
            if self.open_system is not None:
                return self.open_system
            raise UnauthorizedError("missing credentials")
        for name, policy in self.systems.items():
            if policy.api_key is not None and policy.api_key == api_key:
                return name
        raise UnauthorizedError("invalid credentials")

    def get(self, system: str) -> SystemPolicy:
        return self.systems[system]

    def check_enabled(self, system: str) -> None:
        """Raise AccessDeniedError if the system is disabled (checked per request)."""
        if not self.systems[system].enabled:
            raise AccessDeniedError("system disabled")

    def check_demask(self, system: str) -> None:
        """Raise AccessDeniedError if the system may not demask (checked per request)."""
        if not self.systems[system].demask_allowed:
            raise AccessDeniedError("demasking not allowed for system")


def build_evaluation_open() -> PolicyConfig:
    """Single open system for the stand (no API key)."""
    return PolicyConfig(
        systems={
            "stand": SystemPolicy(
                name="stand",
                mask_types=frozenset(
                    {
                        "PERSON", "BIRTH_DATE", "BIRTH_PLACE", "PASSPORT",
                        "CITIZENSHIP", "ISSUING_AUTHORITY", "DIVISION_CODE",
                        "ISSUE_DATE", "DRIVING_LICENSE", "ADDRESS", "EMAIL",
                        "PHONE", "INN", "CARD", "CVV", "PIN", "CARD_HOLDER",
                        "LOCATION",
                    }
                ),
                demask_allowed=True,
                enabled=True,
            )
        },
        open_system="stand",
    )


def build_demo_secure() -> PolicyConfig:
    """Two systems with individual policies, authenticated by API key."""
    return PolicyConfig(
        systems={
            "crm": SystemPolicy(
                name="crm",
                api_key="crm-secret-key",
                mask_types=frozenset(
                    {"PERSON", "EMAIL", "PHONE", "INN", "CARD", "ADDRESS"}
                ),
                demask_allowed=True,
                enabled=True,
            ),
            "analytics": SystemPolicy(
                name="analytics",
                api_key="analytics-secret-key",
                mask_types=frozenset({"EMAIL", "PHONE"}),
                demask_allowed=False,
                enabled=True,
            ),
        },
        open_system=None,
    )