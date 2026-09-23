"""Demonstrate configuration on synthetic values without changing the service."""

import json
import tempfile
from pathlib import Path

from app.core import TOKEN_RE, restore
from app.engine import MaskingEngine
from app.policy import ALL_TYPES, AccessDeniedError, load_policy


def run_demo() -> dict:
    config = {
        "custom_patterns": [{"type": "EMPLOYEE_ID", "pattern": r"\bEMP-\d{4}\b"}],
        "systems": {
            "crm": {"demask_allowed": True},
            "analytics": {
                "mask_types": ["EMAIL", "PHONE"],
                "mask_mode": "redact",
                "demask_allowed": False,
            },
            "combination": {"combinations": {"PIN": ["CARD"]}},
        },
    }
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "policies.json"
        path.write_text(json.dumps(config))
        policies = load_policy(str(path), "demo-secure")

    def apply(system: str, source: str) -> dict:
        policy = policies.get(system)
        engine = MaskingEngine(
            detect_types=policy.detect_types,
            mask_types=policy.mask_types,
            mask_mode=policy.mask_mode,
            combinations=policy.combinations,
            custom_patterns=policies.custom_patterns,
        )
        result = engine.mask(source)
        display = TOKEN_RE.sub(
            lambda match: "<" + match.group()[2:].split(":")[0] + ">",
            result.masked_text,
        )
        return {
            "input": source,
            "masked_tokens_abbreviated": display,
            "exact_restore": (
                restore(result.masked_text, result.mapping) == source
                if policy.demask_allowed else "not permitted by policy"
            ),
        }

    results = {
        "scope": "Isolated configuration demo on synthetic data; deployed policies unchanged",
        "configuration": config,
        "custom_type": apply("crm", "Employee ID: EMP-4821; Email: demo@example.com"),
        "redact": apply("analytics", "Email: demo@example.com"),
        "pin_alone": apply("combination", "PIN: 1234"),
        "pin_with_card": apply("combination", "PIN: 1234; Card: 4111 1111 1111 1111"),
        "standard_categories": len(ALL_TYPES - {"LOCATION"}),
    }
    try:
        policies.check_demask("analytics")
    except AccessDeniedError:
        results["analytics_restore"] = "DENIED"
    else:
        raise AssertionError("analytics must not restore")
    checks = (
        results["custom_type"]["masked_tokens_abbreviated"] == "Employee ID: <EMPLOYEE_ID>; Email: <EMAIL>",
        results["custom_type"]["exact_restore"],
        results["pin_alone"]["masked_tokens_abbreviated"] == "PIN: 1234",
        results["pin_with_card"]["masked_tokens_abbreviated"] == "PIN: <PIN>; Card: <CARD>",
        "demo@example.com" not in results["redact"]["masked_tokens_abbreviated"],
    )
    if not all(checks):
        raise AssertionError("configuration demo failed")
    return results


if __name__ == "__main__":
    print(json.dumps(run_demo(), ensure_ascii=False, indent=2))
