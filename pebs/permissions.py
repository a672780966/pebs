from __future__ import annotations

import json
from typing import Any

from . import config


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
        if name not in self.allowlist.get("skills", []):
            raise PermissionDenied(f"skill not in allowlist: {name}")
        record = self.skills.get(name)
        if record is None:
            raise PermissionDenied(f"skill not registered: {name}")
        if record.get("review_status") != "APPROVED":
            raise PermissionDenied(f"skill not approved: {name} ({record.get('review_status')})")
        if not record.get("enabled_by_default", False):
            raise PermissionDenied(f"skill disabled by default: {name}")
        policy = record.get("execution_policy")
        if policy not in ("NO_CODE", "TRUSTED_RUNNER"):
            from . import sandbox

            if not sandbox.available():
                raise PermissionDenied(
                    f"no verified sandbox adapter available for execution_policy={policy}: {name}"
                )
        return record

    def provider(self, skill_name: str, provider_name: str | None) -> None:
        record = self.skill(skill_name)
        allowed = record.get("allowed_providers", [])
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
