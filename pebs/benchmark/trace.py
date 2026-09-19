"""Skill Trace（M6 §39–§41）：把一次 Build 的 Skill/版本/门禁/人工复核记录成可复现的 trace。"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
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


def pebs_commit() -> str:
    """§41：run 记录必须能回答"哪个 commit 跑出来的"（版本号不足以复现）。"""
    env = os.environ.get("PEBS_COMMIT")
    if env and env.strip():
        return env.strip()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(Path(__file__).resolve().parents[2]),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def reproducibility(
    *, fixture_hashes: dict[str, str] | None = None, skills: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """§41：每次 benchmark run 必须能回答"用什么跑出来的"。

    `skills` 来自 Skill Trace：补上 provider SHA 与 patch —— 只记 "dual-coding
    performed well" 在升级后没有意义（§40）。
    """
    provider_shas = sorted({str(item.get("upstream_sha") or "") for item in (skills or []) if item.get("upstream_sha")})
    patches = sorted(
        {f"{item.get('skill')}@{item.get('patch')}" for item in (skills or []) if item.get("patch")}
    )
    package_hashes = sorted(
        {str(item.get("package_sha256") or "") for item in (skills or []) if item.get("package_sha256")}
    )
    return {
        "pebs_commit": pebs_commit(),
        "pebs_version": pebs_version(),
        "registry_hash": registry_hash(),
        "rules_version": config.RULES_VERSION,
        "model": str((config.PROVIDERS.get("llm") or {}).get("model") or ""),
        "provider_kind": str((config.PROVIDERS.get("llm") or {}).get("kind") or ""),
        "reasoning_effort": str((config.PROVIDERS.get("llm") or {}).get("reasoning_effort") or ""),
        "skill_provider_shas": provider_shas,
        "skill_patches": patches,
        "skill_package_sha256": package_hashes,
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


def _schema_repairs(note: str) -> int:
    """§35：从 step note 里读出 Schema 修复次数（外部 Skill 第二次生成）。"""
    import re

    match = re.search(r"Schema 修复 (\d+) 次", note or "")
    return int(match.group(1)) if match else 0


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


def _skill_for_step(step_id: str) -> str:
    """把 pipeline step id（静态模式的步骤名）解析回 Registry 中的 Skill 名。

    §40：perf 记录必须绑定 skill 版本；用步骤标题当 skill 名会让历史数据失效。
    """
    if registry.get(step_id):
        return step_id
    for name, record in registry.load_skills().items():
        if step_id in ((record.get("handler") or {}).get("steps") or []):
            return name
    return ""


def _step_duration(step: dict[str, Any]) -> float | None:
    """§39：Skill Trace 需要 per-skill duration；steps 表有 started_at/ended_at（秒精度）。"""
    started = str(step.get("started_at") or "")
    ended = str(step.get("ended_at") or "")
    if not started or not ended:
        return None
    try:
        start_ts = time.mktime(time.strptime(started, "%Y-%m-%dT%H:%M:%S"))
        end_ts = time.mktime(time.strptime(ended, "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return None
    return max(round(end_ts - start_ts, 1), 0.0)


def build_trace(
    engine: Any,
    run_id: str,
    *,
    case_id: str = "",
    mode: str = "",
    reproduce: dict[str, Any] | None = None,
    fixture_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
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
        skill_name = _skill_for_step(step["step_id"])
        resolved = bool(skill_name)
        identity = _skill_identity(skill_name) if resolved else {
            "skill": f"step:{step['step_id']}",
            "version": "",
            "provider": "",
            "runtime": "",
            "agent": "",
            "upstream_sha": "",
            "package_sha256": "",
            "patch": "",
            "pinned": False,
        }
        inputs: list[str] = []
        node = node_by_skill.get(step["step_id"]) or {}
        outputs = [rev["artifact_id"] for rev in produced.get(step["step_id"], [])]
        skills.append(
            {
                **identity,
                "step_id": step["step_id"],
                "status": step["status"],
                "attempts": step.get("attempts", 0),
                "duration": _step_duration(step),
                "schema_repairs": _schema_repairs(str(step.get("note") or "")),
                "started_at": step.get("started_at"),
                "ended_at": step.get("ended_at"),
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
            # §63/§64：Trace 必须带上"为什么选它 / 为什么拒绝其他候选"，
            # 否则 Evaluation Tab 的高级模式永远没有可展示的解释。
            "selection_trace": plan.get("selection_trace", []),
        },
        "skills": skills,
        "gates": gate_results,
        "human_review": human_review,
        # §41：不传 reproduce 时也要带上 provider SHA / patch，否则历史数据升级后失效
        "reproducibility": reproduce or reproducibility(fixture_hashes=fixture_hashes, skills=skills),
    }
