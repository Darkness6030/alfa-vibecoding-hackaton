"""Validated policy files; secrets are supplied through environment variables."""

from __future__ import annotations
import hmac
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

ALL_TYPES = frozenset(
    {
        "PERSON",
        "BIRTH_DATE",
        "BIRTH_PLACE",
        "PASSPORT",
        "CITIZENSHIP",
        "ISSUING_AUTHORITY",
        "DIVISION_CODE",
        "ISSUE_DATE",
        "DRIVING_LICENSE",
        "ADDRESS",
        "EMAIL",
        "PHONE",
        "INN",
        "CARD",
        "CVV",
        "PIN",
        "CARD_HOLDER",
        "LOCATION",
    }
)


class AccessDeniedError(Exception):
    pass


class UnauthorizedError(Exception):
    pass


def credentials_match(expected: str, supplied: str) -> bool:
    """Compare bytes so arbitrary header characters cannot trigger TypeError."""
    return hmac.compare_digest(expected.encode("utf-8"), supplied.encode("utf-8"))


@dataclass(frozen=True)
class SystemPolicy:
    name: str
    api_key: str | None = None
    mask_types: frozenset[str] = ALL_TYPES
    demask_allowed: bool = False
    enabled: bool = True
    detect_types: frozenset[str] = ALL_TYPES
    masking_enabled: bool = True
    mask_mode: str = "token"
    combinations: tuple[tuple[str, tuple[str, ...]], ...] = ()


@dataclass
class PolicyConfig:
    systems: dict[str, SystemPolicy] = field(default_factory=dict)
    open_system: str | None = None
    custom_patterns: tuple[tuple[str, str], ...] = ()

    def authenticate(self, api_key: str | None, *, allow_open: bool = True) -> str:
        if not api_key:
            if allow_open and self.open_system is not None:
                return self.open_system
            raise UnauthorizedError("missing credentials")
        for name, policy in self.systems.items():
            if policy.api_key and credentials_match(policy.api_key, api_key):
                return name
        raise UnauthorizedError("invalid credentials")

    def get(self, system: str) -> SystemPolicy:
        try:
            return self.systems[system]
        except KeyError:
            raise AccessDeniedError("unknown consumer") from None

    def check_enabled(self, system: str) -> None:
        if not self.get(system).enabled:
            raise AccessDeniedError("disabled")

    def check_demask(self, system: str) -> None:
        self.check_enabled(system)
        if not self.get(system).demask_allowed:
            raise AccessDeniedError("demask denied")


def build_demo_secure() -> PolicyConfig:
    return PolicyConfig(
        systems={
            "crm": SystemPolicy(
                name="crm",
                api_key=os.getenv("ALFAGEN_CRM_API_KEY"),
                demask_allowed=True,
            ),
            "analytics": SystemPolicy(
                name="analytics",
                api_key=os.getenv("ALFAGEN_ANALYTICS_API_KEY"),
                mask_types=frozenset({"EMAIL", "PHONE"}),
            ),
        }
    )


def build_evaluation_open() -> PolicyConfig:
    config = build_demo_secure()
    config.systems["stand"] = SystemPolicy(name="stand", demask_allowed=True)
    config.open_system = "stand"
    return config


def _system_policy(name: str, values: dict, allowed: frozenset[str]) -> SystemPolicy:
    if not re.fullmatch("[a-zA-Z0-9_-]{1,40}", name):
        raise ValueError("invalid consumer name")
    v = dict(values)
    key_env = v.pop("api_key_env", None)
    v["api_key"] = os.environ.get(key_env) if key_env else None
    for attr in ("detect_types", "mask_types"):
        v[attr] = frozenset(v.get(attr, allowed))
        if not v[attr].issubset(allowed):
            raise ValueError("unknown type")
    if not v["mask_types"].issubset(v["detect_types"]):
        raise ValueError("masked types must be detected")
    for flag in ("enabled", "masking_enabled", "demask_allowed"):
        if flag in v and type(v[flag]) is not bool:
            raise ValueError("policy flags must be boolean")
    if v.get("mask_mode", "token") not in ("token", "redact"):
        raise ValueError("invalid mask mode")
    combinations = v.get("combinations", {})
    if any(
        t not in allowed or not set(req) <= allowed for t, req in combinations.items()
    ):
        raise ValueError("invalid combination")
    v["combinations"] = tuple((t, tuple(req)) for t, req in combinations.items())
    return SystemPolicy(name=name, **v)


def load_policy(path: str, profile: str) -> PolicyConfig:
    if not path:
        return (
            build_evaluation_open()
            if profile == "evaluation-open"
            else build_demo_secure()
        )
    data = json.loads(Path(path).read_text())
    patterns = tuple((p["type"], p["pattern"]) for p in data.get("custom_patterns", []))
    for type_, pattern in patterns:
        if not re.fullmatch("[A-Z_]{1,40}", type_) or len(pattern) > 500:
            raise ValueError("invalid custom detector")
        re.compile(pattern)
    allowed = ALL_TYPES | {t for t, _ in patterns}
    systems = {
        name: _system_policy(name, values, allowed)
        for name, values in data["systems"].items()
    }
    keys = [s.api_key for s in systems.values() if s.api_key]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate API keys")
    open_system = (
        data.get("open_system", "stand") if profile == "evaluation-open" else None
    )
    if open_system and open_system not in systems:
        raise ValueError("unknown open system")
    return PolicyConfig(systems, open_system, patterns)
