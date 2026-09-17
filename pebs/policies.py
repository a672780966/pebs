from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import config

NUMERIC_LOAD_PATTERNS = [
    r"认知负荷\s*[=＝:：]\s*\d",
    r"cognitive\s*load\s*[=:]\s*\d",
    r"\b\d+(\.\d+)?\s*/\s*10\s*(的)?\s*认知负荷",
]
REFERRAL_PATTERNS = [
    r"该学生需要转介",
    r"建议转介",
    r"必须转介",
    r"应当转介",
]


def _path(name: str) -> Path:
    return Path(config.REGISTRY_DIR) / name


def load_patch_policies() -> dict[str, Any]:
    path = _path("patch_policies.json")
    if not path.exists():
        return {"policies": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def load_providers() -> dict[str, Any]:
    path = _path("providers.json")
    if not path.exists():
        return {"providers": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def policy_for(skill_name: str) -> dict[str, Any]:
    policies = load_patch_policies().get("policies", {})
    if skill_name in policies:
        return policies[skill_name]
    for name, policy in policies.items():
        if skill_name.startswith(name):
            return policy
    return {}


def check_skill_record(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    name = str(record.get("name", ""))
    policy = policy_for(name)
    if policy.get("status") == "DISABLED":
        if record.get("status") not in ("DISABLED", "REFERENCE_ONLY"):
            errors.append(f"{name}: 政策要求 DISABLED，当前 status={record.get('status')}")
        if record.get("enabled_by_default"):
            errors.append(f"{name}: 政策要求默认不启用")
    if policy.get("requires_supported_evidence"):
        kinds = {str(item.get("kind")) for item in (record.get("preconditions") or [])}
        if "supported_claims" not in kinds:
            errors.append(
                f"{name}: 政策要求声明 SUPPORTED 证据前置条件（preconditions.supported_claims）"
            )
    return errors


def apply_output_policies(record: dict[str, Any], content: Any) -> list[str]:
    errors: list[str] = []
    name = str(record.get("name", ""))
    policy = policy_for(name)
    text = json.dumps(content, ensure_ascii=False)
    if policy.get("forbid_numeric_load_score"):
        for pattern in NUMERIC_LOAD_PATTERNS:
            if re.search(pattern, text):
                errors.append(f"{name}: 禁止数字化认知负荷评分（命中 {pattern}）")
    if policy.get("forbid_specialist_referral"):
        for pattern in REFERRAL_PATTERNS:
            if re.search(pattern, text):
                errors.append(f"{name}: 禁止自动 specialist referral，应写入 {policy.get('flags_field', 'flags')}")
    return errors


def external_provider_allowed(skill_name: str, provider: str) -> bool:
    providers = load_providers().get("providers", {})
    entry = providers.get(provider)
    if not entry:
        return False
    allowlist = entry.get("initial_allowlist", [])
    return any(skill_name == allowed or skill_name.startswith(allowed) for allowed in allowlist)
