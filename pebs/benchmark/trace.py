"""Skill Trace（M6 §39–§41）：把一次 Build 的 Skill/版本/门禁/人工复核记录成可复现的 trace。"""

from __future__ import annotations

import hashlib
import json
import time
from importlib import metadata
from pathlib import Path
from typing import Any

from .. import config, registry


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def registry_hash() -> str:
    path = Path(config.REGISTRY_DIR) / "skills.json"
    if not path.exists():
        return ""
    return _sha256_text(path.read_text(encoding="utf-8"))[:16]


def pebs_version() -> str:
    try:
        return metadata.version("pebs")
    except metadata.PackageNotFoundError:
        return "0.6.0-dev"


def reproducibility(*, fixture_hashes: dict[str, str] | None = None) -> dict[str, Any]:
    """§41：每次 benchmark run 必须能回答"用什么跑出来的"。"""
    return {
        "pebs_version": pebs_version(),
        "registry_hash": registry_hash(),
        "rules_version": config.RULES_VERSION,
        "model": str((config.PROVIDERS.get("llm") or {}).get("model") or ""),
        "provider_kind": str((config.PROVIDERS.get("llm") or {}).get("kind") or ""),
        "reasoning_effort": str((config.PROVIDERS.get("llm") or {}).get("reasoning_effort") or ""),
        "fixture_hashes": fixture_hashes or {},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
    }


def _skill_identity(name: str) -> dict[str, Any]:
    record = registry.get(name) or {}
    pinned = record.get("pinned_version")
    versions = [item for item in (record.get("versions") or []) if isinstance(item, dict)]
    active = next((item for item in versions if item.get("version") == pinned), versions[-1] if versions else {})
    patches = [item for item in (record.get("patches") or []) if isinstance(item, dict)]
    active_patch = next(
        (item for item in reversed(patches) if item.get("upstream_version") == active.get("version")),
        patches[-1] if patches else {},
    )
    return {
        "skill": name,
        "version": str(pinned or active.get("version") or record.get("version") or ""),
        "provider": str(record.get("provider") or ("builtin" if record.get("runtime") == "builtin" else "")),
        "runtime": str(record.get("runtime") or ""),
        "agent": str(record.get("agent") or ""),
        "upstream_sha": str(active.get("upstream_sha") or ""),
        "package_sha256": str(active.get("package_sha256") or ""),
        "patch": str(active_patch.get("patch_version") or ""),
        "pinned": bool(pinned),
    }


def _all_revisions(store: Any) -> list[dict[str, Any]]:
    revisions: list[dict[str, Any]] = []
    for artifact in store.list_artifacts():
        for revision_id in store.revisions_of(artifact["artifact_id"]):
            revisions.append(store.get_revision(revision_id))
    return revisions


def _run_inputs(run: dict[str, Any]) -> dict[str, Any]:
    raw = run.get("inputs") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return raw if isinstance(raw, dict) else {}


def build_trace(engine: Any, run_id: str, *, case_id: str = "", mode: str = "", reproduce: dict[str, Any] | None = None) -> dict[str, Any]:
    """从 Store 里重建一次运行的 Skill Trace（不依赖内存状态）。"""
    store = engine.store
    run = store.get_run(run_id)
    steps = store.get_steps(run_id)
    by_run = [rev for rev in _all_revisions(store) if rev.get("produced_by_run") == run_id]
    produced: dict[str, list[dict[str, Any]]] = {}
    for rev in by_run:
        produced.setdefault(str(rev.get("produced_by") or ""), []).append(
            {"artifact_id": rev["artifact_id"], "revision_id": rev["revision_id"], "content_hash": rev["content_hash"]}
        )

    route = store.accepted_content("router_result") or {}
    plan = store.accepted_content("build_plan_dynamic") or {}
    skills: list[dict[str, Any]] = []
    node_by_skill: dict[str, dict[str, Any]] = {}
    for node in plan.get("nodes", []):
        node_by_skill.setdefault(str(node.get("skill")), node)
    for step in steps:
        skill_name = str(step.get("title") or step["step_id"])
        identity = _skill_identity(step["step_id"]) if registry.get(step["step_id"]) else _skill_identity(skill_name)
        inputs: list[str] = []
        node = node_by_skill.get(step["step_id"]) or {}
        outputs = [rev["artifact_id"] for rev in produced.get(step["step_id"], [])]
        skills.append(
            {
                **identity,
                "step_id": step["step_id"],
                "status": step["status"],
                "attempts": step.get("attempts", 0),
                "note": step.get("note") or "",
                "error": step.get("error") or "",
                "input_artifacts": inputs,
                "output_artifacts": outputs,
                "parallel_group": node.get("parallel_group"),
                "reused": bool(node.get("reused")),
                "gates_before": node.get("gate_before", []),
                "gates_after": node.get("gate_after", []),
                "reason": node.get("reason", ""),
            }
        )

    gate_results = []
    for artifact in store.list_artifacts():
        if artifact["artifact_type"] != "gate_result" or not artifact.get("accepted_rev"):
            continue
        content = store.accepted_content(artifact["artifact_id"]) or {}
        gate_results.append(
            {
                "gate": content.get("gate_id"),
                "target": artifact["artifact_id"],
                "status": content.get("status"),
                "version": content.get("check_version"),
            }
        )

    human_review: list[dict[str, Any]] = []
    for artifact in store.list_artifacts():
        if artifact["artifact_type"] != "review_record" or not artifact.get("accepted_rev"):
            continue
        content = store.accepted_content(artifact["artifact_id"]) or {}
        human_review.append(
            {
                "changeset_id": content.get("changeset_id"),
                "reviewer": content.get("reviewer"),
                "basis": content.get("basis"),
                "created_at": content.get("created_at"),
            }
        )

    return {
        "run_id": run_id,
        "case_id": case_id,
        "mode": mode or str(_run_inputs(run).get("planner", "static")),
        "run_status": run["status"],
        "request": run.get("request", ""),
        "route": {
            "task_intent": route.get("task_intent"),
            "knowledge_types": route.get("knowledge_types"),
            "requested_outputs": route.get("requested_outputs"),
            "research_need": route.get("research_need"),
            "media_need": route.get("media_need"),
            "source": route.get("source"),
        },
        "plan": {
            "plan_id": plan.get("plan_id"),
            "node_count": len(plan.get("nodes", [])),
            "terminal_outputs": plan.get("terminal_outputs", []),
            "reused_artifacts": plan.get("reused_artifacts", []),
            "degraded": plan.get("degraded", False),
        },
        "skills": skills,
        "gates": gate_results,
        "human_review": human_review,
        "reproducibility": reproduce or reproducibility(),
    }
