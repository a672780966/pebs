"""自动期望检查（M6 §36–§38, §50–§58 的可自动部分）。

人工评分负责价值判断；这里只检查可判定的事实：
Plan 是否出现被禁止的能力、必需产物是否存在、禁用措辞是否出现、动画是否被门禁批准。
"""

from __future__ import annotations

import re
from typing import Any


def _artifact_texts(store: Any, artifact_types: tuple[str, ...]) -> dict[str, str]:
    texts: dict[str, str] = {}
    for item in store.list_artifacts():
        if not item.get("accepted_rev"):
            continue
        if artifact_types and item["artifact_type"] not in artifact_types:
            continue
        content = store.accepted_content(item["artifact_id"])
        texts[item["artifact_id"]] = str(content)
    return texts


def plan_checks(plan: dict[str, Any], expect: dict[str, Any]) -> list[dict[str, Any]]:
    plan_expect = expect.get("plan") or {}
    executed = [node for node in plan.get("nodes", []) if not node.get("reused")]
    reused = [node for node in plan.get("nodes", []) if node.get("reused")]
    skills = [str(node.get("skill")) for node in executed]
    steps = [step for node in executed for step in (node.get("steps") or [])]
    issues: list[dict[str, Any]] = []
    for required in plan_expect.get("must_include_skills", []):
        if required not in [str(node.get("skill")) for node in plan.get("nodes", [])]:
            issues.append({"kind": "PLANNING", "detail": f"缺少必需 Skill：{required}"})
    for forbidden in plan_expect.get("must_exclude_skills", []):
        if forbidden in skills:
            issues.append({"kind": "PLANNING", "detail": f"出现被禁止的 Skill：{forbidden}"})
    for required in plan_expect.get("must_include_steps", []):
        if required not in steps and required not in skills:
            issues.append({"kind": "PLANNING", "detail": f"缺少必需步骤：{required}"})
    for forbidden in plan_expect.get("must_exclude_steps", []):
        if forbidden in steps or forbidden in skills:
            issues.append({"kind": "PLANNING", "detail": f"出现被禁止的步骤：{forbidden}"})
    for terminal in plan_expect.get("terminal_outputs", []):
        if terminal not in (plan.get("terminal_outputs") or []):
            issues.append({"kind": "PLANNING", "detail": f"terminal_outputs 缺少：{terminal}"})
    nodes = plan.get("nodes", [])
    if nodes and plan_expect.get("min_reuse_rate") is not None:
        reused = len([node for node in nodes if node.get("reused")])
        rate = reused / len(nodes)
        if rate < float(plan_expect["min_reuse_rate"]):
            issues.append({"kind": "PLANNING", "detail": f"复用率 {rate:.2f} 低于期望 {plan_expect['min_reuse_rate']}"})
    for required_type in plan_expect.get("must_reuse_artifact_types", []):
        if not any(
            node.get("reused") and any(str(output).split(":", 1)[0] == required_type for output in node.get("outputs", []))
            for node in nodes
        ):
            issues.append({"kind": "PLANNING", "detail": f"未复用已有产物类型：{required_type}"})
    return issues


def routing_checks(route: dict[str, Any], expect: dict[str, Any]) -> list[dict[str, Any]]:
    routing = expect.get("routing") or {}
    issues: list[dict[str, Any]] = []
    knowledge = set(route.get("knowledge_types") or [])
    required_any = set(routing.get("knowledge_types_any_of") or [])
    if required_any and not (knowledge & required_any):
        issues.append({"kind": "ROUTING", "detail": f"knowledge_types 未命中：{sorted(required_any)}（实际 {sorted(knowledge)}）"})
    for required in routing.get("knowledge_types_all_of", []):
        if required not in knowledge:
            issues.append({"kind": "ROUTING", "detail": f"knowledge_types 缺少：{required}"})
    outputs = set(route.get("requested_outputs") or [])
    for required in routing.get("requested_outputs", []):
        if required not in outputs:
            issues.append({"kind": "ROUTING", "detail": f"requested_outputs 缺少：{required}"})
    research = str(route.get("research_need") or "")
    if routing.get("research_need") and research != routing["research_need"]:
        issues.append({"kind": "ROUTING", "detail": f"research_need={research}，期望 {routing['research_need']}"})
    if routing.get("media_need") and str(route.get("media_need") or "") != routing["media_need"]:
        issues.append({"kind": "ROUTING", "detail": f"media_need={route.get('media_need')}，期望 {routing['media_need']}"})
    return issues


NEGATION_WINDOW = ("不要", "不能", "避免", "禁止", "别", "不得", "拒绝", "不将", "不应")


def _in_negative_context(text: str, start: int, *, window: int = 14) -> bool:
    """禁用表达若出现在"不要/避免……"等否定语境中，属于教学反例而非违规。"""
    prefix = text[max(0, start - window) : start]
    return any(token in prefix for token in NEGATION_WINDOW)


def content_checks(store: Any, expect: dict[str, Any]) -> list[dict[str, Any]]:
    content = expect.get("content") or {}
    issues: list[dict[str, Any]] = []
    artifacts = content.get("artifact_types") or []
    texts = _artifact_texts(store, tuple(artifacts))
    if content.get("must_exist", []):
        existing = {item["artifact_id"] for item in store.list_artifacts() if item.get("accepted_rev")}
        for artifact_id in content["must_exist"]:
            if artifact_id not in existing:
                issues.append({"kind": "CONTENT", "detail": f"缺少产物：{artifact_id}"})
    for artifact_id, text in texts.items():
        for pattern in content.get("banned_regex", []):
            for match in re.finditer(pattern, text):
                if _in_negative_context(text, match.start()):
                    continue
                issues.append({"kind": "SAFETY", "detail": f"{artifact_id} 命中禁用表达：{pattern}"})
                break
        for pattern in content.get("required_regex", []):
            if not re.search(pattern, text):
                issues.append({"kind": "CONTENT", "detail": f"{artifact_id} 缺少必需表达：{pattern}"})
    return issues


def safety_fixture_checks(store: Any, expect: dict[str, Any]) -> list[dict[str, Any]]:
    """§49–§52：对抗性 fixtures 的 forbidden/required 自动检查（硬门）。"""
    case_ids = expect.get("safety_cases") or []
    if not case_ids:
        return []
    from . import cases as cases_mod
    from . import safety as safety_mod

    fixture = safety_mod.load_safety_cases(cases_mod.benchmark_dir())
    by_id = {case["id"]: case for case in fixture.get("cases", [])}
    texts = list(_artifact_texts(store, tuple()).values())
    issues: list[dict[str, Any]] = []
    for case_id in case_ids:
        case = by_id.get(case_id)
        if case is None:
            issues.append({"kind": "SAFETY", "detail": f"未找到安全 fixture：{case_id}"})
            continue
        for text in texts:
            issues.extend(safety_mod.safety_checks(text, case))
    return issues


def animation_checks(store: Any, expect: dict[str, Any]) -> list[dict[str, Any]]:
    """§56：用户要求"每页都加动画"时，只允许被 Animation Gate 批准的部分。"""
    expectation = expect.get("animation") or {}
    if not expectation:
        return []
    issues: list[dict[str, Any]] = []
    for item in store.list_artifacts():
        if item["artifact_type"] != "animation_decisions" or not item.get("accepted_rev"):
            continue
        content = store.accepted_content(item["artifact_id"]) or {}
        decisions = content.get("decisions", [])
        approved = [d for d in decisions if d.get("decision") == "ANIMATION"]
        if expectation.get("max_approved") is not None and len(approved) > expectation["max_approved"]:
            issues.append({"kind": "MEDIA", "detail": f"{item['artifact_id']} 批准动画 {len(approved)} 个，超过上限 {expectation['max_approved']}"})
        if expectation.get("forbid_all") and approved:
            issues.append({"kind": "MEDIA", "detail": f"{item['artifact_id']} 不应批准任何动画"})
    return issues


def evaluate(store: Any, expect: dict[str, Any], *, plan: dict[str, Any] | None = None, route: dict[str, Any] | None = None) -> dict[str, Any]:
    issues = (
        plan_checks(plan or {}, expect)
        + routing_checks(route or {}, expect)
        + content_checks(store, expect)
        + safety_fixture_checks(store, expect)
        + animation_checks(store, expect)
    )
    counts: dict[str, int] = {}
    for issue in issues:
        counts[issue["kind"]] = counts.get(issue["kind"], 0) + 1
    return {"issues": issues, "counts": counts, "ok": not issues}
