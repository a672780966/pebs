from __future__ import annotations

from typing import Any

from . import schemas
from .evidence import EvidenceStore
from .permissions import PermissionManager
from .store import Store


class HookFailure(Exception):
    pass


class Hooks:
    EVENTS = [
        "before_skill",
        "after_skill",
        "before_external_action",
        "after_artifact_write",
        "before_final_export",
    ]

    def __init__(self, store: Store, evidence: EvidenceStore, permissions: PermissionManager):
        self.store = store
        self.evidence = evidence
        self.permissions = permissions

    def before_skill(
        self,
        skill_name: str,
        *,
        inputs: dict[str, Any] | None = None,
        input_schema: str | None = None,
        requires_evidence_gate: bool = False,
        evidence_gate_cleared: bool | None = None,
    ) -> dict[str, Any]:
        record = self.permissions.skill(skill_name)
        if input_schema and inputs is not None:
            try:
                schemas.validate(inputs, input_schema)
            except schemas.SchemaError as exc:
                raise HookFailure(f"before_skill input schema failed: {exc}") from exc
        if requires_evidence_gate and evidence_gate_cleared is False:
            raise HookFailure("before_skill: 证据核验未完成，相关步骤不允许进入正式生成")
        return {"skill": skill_name, "version": record.get("version"), "policy": record.get("execution_policy")}

    def after_skill(self, skill_name: str, output: Any, *, output_schema: str | None = None) -> dict[str, Any]:
        self.permissions.skill(skill_name)
        if output_schema:
            try:
                schemas.validate(output, output_schema)
            except schemas.SchemaError as exc:
                raise HookFailure(f"after_skill output schema failed: {exc}") from exc
        return {"skill": skill_name, "validated": bool(output_schema)}

    def before_external_action(self, action: str, *, authorization: str | None = None) -> None:
        if authorization != "trusted":
            raise HookFailure(f"before_external_action: 无可信授权记录，拒绝 {action}")

    def after_artifact_write(self, revision_id: str) -> dict[str, Any]:
        rev = self.store.get_revision(revision_id)
        from .store import canonical_json
        import hashlib

        digest = hashlib.sha256(canonical_json(rev["content"]).encode("utf-8")).hexdigest()
        if digest != rev["content_hash"]:
            raise HookFailure(f"after_artifact_write: hash mismatch for {revision_id}")
        return {"revision_id": revision_id, "content_hash": digest, "approved": False}

    def before_final_export(self, readiness: dict[str, Any]) -> None:
        if not readiness.get("ready"):
            reasons = "; ".join(readiness.get("blocking", [])) or "gates not satisfied"
            raise HookFailure(f"before_final_export: 正式导出被阻止：{reasons}")
