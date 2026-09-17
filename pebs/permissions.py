from __future__ import annotations

import json
from typing import Any

from . import config, registry


class PermissionDenied(Exception):
    pass


WRITE_ACTIONS = {
    "cnki_download",
    "zotero_write",
    "zotero_pdf_attach",
    "publish",
    "email",
    "external_upload",
    "git_push",
}


class PermissionManager:
    def __init__(self) -> None:
        self.skills = json.loads((config.REGISTRY_DIR / "skills.json").read_text(encoding="utf-8"))
        self.allowlist = json.loads((config.REGISTRY_DIR / "allowlist.json").read_text(encoding="utf-8"))

    def skill(self, name: str) -> dict[str, Any]:
        if registry.is_denied(name):
            raise PermissionDenied(f"skill is denylisted: {name}")
        canonical = registry.resolve_alias(name) or name
        if canonical not in self.allowlist.get("skills", []):
            raise PermissionDenied(f"skill not in allowlist: {canonical}")
        record = self.skills.get(canonical) or registry.get(canonical)
        if record is None:
            raise PermissionDenied(f"skill not registered: {canonical}")
        status = record.get("status")
        review_status = record.get("review_status")
        approved = status in ("APPROVED", "PATCHED") or review_status == "APPROVED"
        if not approved:
            raise PermissionDenied(f"skill not approved: {canonical} (status={status or review_status})")
        if not record.get("enabled_by_default", True):
            raise PermissionDenied(f"skill disabled by default: {canonical}")
        policy = record.get("execution_policy")
        if policy not in ("NO_CODE", "TRUSTED_RUNNER", None):
            from . import sandbox

            if not sandbox.available():
                raise PermissionDenied(
                    f"no verified sandbox adapter available for execution_policy={policy}: {canonical}"
                )
        return record

    def provider(self, skill_name: str, provider_name: str | None) -> None:
        record = self.skill(skill_name)
        allowed = record.get("provider") or record.get("allowed_providers") or []
        if provider_name and provider_name not in allowed:
            raise PermissionDenied(f"provider {provider_name} not allowed for {skill_name}")

    def tool(self, tool_name: str) -> None:
        if tool_name not in self.allowlist.get("tools", []):
            raise PermissionDenied(f"tool not allowed: {tool_name}")

    def external_action(self, action: str) -> None:
        raise PermissionDenied(
            f"external write action denied in M1: {action} (需明确的用户授权记录，M1 未启用外部写操作)"
        )

    def network_target(self, url: str) -> None:
        allowed = self.allowlist.get("network_hosts", [])
        host = url.split("/")[2] if "://" in url else url
        if not any(host.endswith(a) for a in allowed):
            raise PermissionDenied(f"network host not allowed: {host}")
