"""Benchmark 执行器（M6 §28–§29, §41）：三种模式跑同一个 Golden Case 并落盘。

- builtin: 固定 Pipeline（planner=static）
- dynamic: Semantic Router + Dynamic DAG（planner=dynamic）
- direct_codex: 固定 baseline prompt 直接调用同一 LLM Provider（公平对照）
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .. import config, providers
from ..engine import Engine
from . import cases, checks, metrics, trace

DIRECT_BASELINE_SYSTEM = (
    "你是一位资深教师教育设计者。请直接完成用户给出的课程生产任务，"
    "输出完整、可直接使用的教学产品；不要解释你的过程，不要省略内容。"
)


def direct_baseline_prompt(case: dict[str, Any]) -> str:
    """§29：Direct Codex baseline prompt 固定，给足信息，不故意写差。"""
    return (
        "任务：\n"
        f"{case['request']}\n\n"
        "要求：\n"
        "- 输出语言文字与用户任务一致（中文）。\n"
        "- 结构化输出：先列学习目标，再按章节（或 8.1/8.2…）给出完整教学内容。\n"
        "- 每节包含教学策略、案例、讲解要点；案例必须可核查、不编造机构或研究。\n"
        "- 心理学结论保持审慎：区分相关与因果，标注理论不确定性。\n"
        "- 不做诊断、不给学生贴标签。\n"
    )


def run_dir(case_id: str, mode: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    return cases.runs_dir() / f"{stamp}-{case_id}-{mode}"


def _fixture_hashes(case: dict[str, Any]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for key in ("template_fixture",):
        path = cases.fixture_path(case, key)
        if path:
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    for name in case.get("material_fixtures") or []:
        path = cases.benchmark_dir() / str(name)
        if path.exists():
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    return hashes


def run_case(case_id: str, *, mode: str = "dynamic", project_id: str | None = None, budgets: dict[str, int] | None = None, accept: bool = True) -> dict[str, Any]:
    case = cases.get_case(case_id)
    errors = cases.validate_case(case)
    if errors:
        raise ValueError("; ".join(errors))
    if mode not in cases.VALID_MODES:
        raise ValueError(f"unknown mode: {mode}")
    project = project_id or f"bench-{case_id.lower()}-{mode}"
    target = run_dir(case_id, mode)
    target.mkdir(parents=True, exist_ok=True)
    started = time.time()

    if mode == "direct_codex":
        record = _run_direct(case, target)
    else:
        record = _run_pebs(case, mode=mode, project=project, budgets=budgets, accept=accept)

    record.update(
        {
            "case_id": case["id"],
            "case_title": case.get("title", ""),
            "mode": mode,
            "project_id": project,
            "wall_time_seconds": round(time.time() - started, 2),
            "fixtures": _fixture_hashes(case),
            "reproducibility": trace.reproducibility(fixture_hashes=_fixture_hashes(case)),
            "run_dir": str(target),
        }
    )
    (target / "run.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def _run_pebs(case: dict[str, Any], *, mode: str, project: str, budgets: dict[str, int] | None, accept: bool) -> dict[str, Any]:
    engine = Engine(project)
    request = case["request"]
    template_path = cases.fixture_path(case, "template_fixture")
    material_paths = [cases.benchmark_dir() / name for name in case.get("material_fixtures") or []]
    planner_mode = "dynamic" if mode in ("dynamic", "mixed") else "static"
    start = engine.start_build(
        request,
        template_path=template_path,
        material_paths=material_paths,
        budgets=budgets,
        planner_mode=planner_mode,
    )
    run_id = start["run_id"]
    status = _wait(engine, run_id)
    if accept and status["run"]["status"] == "succeeded":
        engine.accept(start["changeset_id"])

    steps = status["steps"]
    run_record = engine.store.get_run(run_id)
    skill_trace = trace.build_trace(
        engine,
        run_id,
        case_id=case["id"],
        mode=mode,
        reproduce=trace.reproducibility(fixture_hashes=_fixture_hashes(case)),
    )
    summary = metrics.summarize_run(skill_trace)
    hashes = metrics.snapshot_hashes(engine.store)
    plan = engine.store.accepted_content("build_plan_dynamic") or {}
    route = engine.store.accepted_content("router_result") or {}
    automatic = checks.evaluate(engine.store, case.get("expect") or {}, plan=plan, route=route)
    return {
        "run_id": run_id,
        "changeset_id": start["changeset_id"],
        "run_status": status["run"]["status"],
        "steps": [(step["step_id"], step["status"], step.get("error") or "") for step in steps],
        "metrics": {
            **summary,
            "model_calls": int(run_record.get("calls_used", 0)),
            "research_calls": int(run_record.get("research_used", 0)),
        },
        "artifact_hashes": hashes,
        "automatic_issues": automatic,
        "trace": skill_trace,
    }


def _run_direct(case: dict[str, Any], target: Path) -> dict[str, Any]:
    llm = providers.get_llm()
    availability = llm.availability()
    if not availability.get("available"):
        return {
            "run_id": "",
            "run_status": "blocked",
            "metrics": {"model_calls": 0, "research_calls": 0},
            "artifact_hashes": {},
            "trace": {},
            "blocked_reason": "; ".join(availability.get("reasons", [])),
        }
    prompt = direct_baseline_prompt(case)
    response = llm.generate_text(system=DIRECT_BASELINE_SYSTEM, prompt=prompt) if hasattr(llm, "generate_text") else None
    if response is None:
        data = llm.generate_json(
            task="benchmark_direct",
            system=DIRECT_BASELINE_SYSTEM,
            prompt=prompt + "\n输出 JSON：{\"content\": \"...\"}",
        )
        response = str(data.get("content") or "")
    (target / "direct_output.md").write_text(str(response), encoding="utf-8")
    (target / "direct_prompt.txt").write_text(prompt, encoding="utf-8")
    return {
        "run_id": "",
        "run_status": "succeeded",
        "metrics": {"model_calls": 1, "research_calls": 0, "output_chars": metrics.char_count(str(response))},
        "artifact_hashes": {},
        "trace": {},
        "output_chars": metrics.char_count(str(response)),
    }


def _wait(engine: Engine, run_id: str, timeout: float = 3600.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    status = engine.run_status(run_id)
    while status["run"]["status"] == "running" and time.time() < deadline:
        time.sleep(1.0)
        status = engine.run_status(run_id)
    return status


def simulate_local_edit(case_id: str, *, project: str, instruction: str, preserve: list[str]) -> dict[str, Any]:
    """§26 / Acceptance 7：在动态模式完成后执行自然语言局部修改，并验证 preserve 集 hash 不变。"""
    engine = Engine(project)
    before = metrics.snapshot_hashes(engine.store)
    result = engine.conversation_edit(instruction)
    after = metrics.snapshot_hashes(engine.store)
    locality = metrics.locality_report(before, after, preserve=preserve)
    if result.get("run_status") == "succeeded":
        engine.accept(result["changeset_id"])
        locality["accepted"] = True
    return {"edit": result, "locality": locality}
