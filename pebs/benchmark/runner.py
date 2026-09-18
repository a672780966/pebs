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


def seed_case_artifacts(engine: Engine, case: dict[str, Any]) -> list[str]:
    """把 case 声明的"既有产物"（如已有讲稿）以 accepted revision 写入 Store。

    这是 benchmark harness 的输入准备（§25 "输入一份已有心理学讲稿"），
    不新增任何 pipeline 能力；真实产品中的导入能力由 M7 评估。
    """
    from .. import config

    seeded: list[str] = []
    for entry in case.get("seed_artifacts") or []:
        artifact_id = entry["artifact_id"]
        artifact_type = entry["artifact_type"]
        if entry.get("from_markdown"):
            path = cases.benchmark_dir() / str(entry["from_markdown"])
            text = path.read_text(encoding="utf-8")
            section_id = str(entry.get("section_id") or "sec1")
            paragraphs = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith(("#", ">"))]
            units = [
                {"unit_id": f"u{index}", "kind": "narration", "text": paragraph, "claim_refs": []}
                for index, paragraph in enumerate(paragraphs, start=1)
            ]
            content = {
                "section_id": section_id,
                "title": str(entry.get("title") or "已有讲稿"),
                "units": units,
                "word_count": {
                    "count": sum(len(unit["text"]) for unit in units),
                    "min": 0,
                    "max": 99999,
                },
            }
        else:
            content = dict(entry.get("content") or {})
        info = engine.store.add_revision(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            content=content,
            produced_by=str(entry.get("produced_by") or "benchmark-seed"),
            rules_version=config.RULES_VERSION,
        )
        engine.store.set_accepted(artifact_id, info["revision_id"])
        seeded.append(artifact_id)
    return seeded


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


def run_case(
    case_id: str,
    *,
    mode: str = "dynamic",
    project_id: str | None = None,
    budgets: dict[str, int] | None = None,
    accept: bool = True,
    allow_qualified_claims: bool = False,
    extra_skills: list[str] | None = None,
    experiment: str = "",
) -> dict[str, Any]:
    case = cases.get_case(case_id)
    extra_skills = [str(item) for item in (extra_skills or [])]
    if extra_skills:
        # §46 Skill Selection Experiment：显式 `/skill-name` 追加到请求，
        # 用于 Builtin only / External only / Hybrid 对照（不改 case 定义）。
        case = dict(case)
        case["request"] = case["request"].rstrip() + " " + " ".join(f"/{name}" for name in extra_skills)
    errors = cases.validate_case(case)
    if errors:
        raise ValueError("; ".join(errors))
    if mode not in cases.VALID_MODES:
        raise ValueError(f"unknown mode: {mode}")
    # §31：把预算交给 Planner，使其在预算不足时生成降级 Plan（而不是执行到一半 BLOCKED）
    effective_budgets = dict(config.RULES.get("budgets") or {})
    effective_budgets.update(budgets or {})
    # 默认给每次 benchmark run 一个独立项目：否则第二次跑同一 case 会复用上一次的
    # 已接受产物（calls=0、Plan 全 reuse），得到不可比的"空跑"结果。
    project = project_id or f"bench-{case_id.lower()}-{mode}-{time.strftime('%H%M%S', time.localtime())}"
    target = run_dir(case_id, mode)
    target.mkdir(parents=True, exist_ok=True)
    started = time.time()

    original_rules = config.RULES
    effective_policy = list((original_rules.get("evidence") or {}).get("pck_claim_statuses") or ["SUPPORTED"])
    if allow_qualified_claims:
        # M6 §13/§48：操作者显式放行 QUALIFY_REQUIRED（限定语必须保留）；
        # 该设置会写进 run.json 的 evidence_policy，保证可复现与可审计。
        relaxed = dict(original_rules)
        relaxed["evidence"] = {"pck_claim_statuses": ["SUPPORTED", "QUALIFY_REQUIRED"]}
        config.RULES = relaxed
        effective_policy = ["SUPPORTED", "QUALIFY_REQUIRED"]
    try:
        if mode == "direct_codex":
            record = _run_direct(case, target)
        else:
            record = _run_pebs(case, mode=mode, project=project, budgets=effective_budgets, accept=accept)
    finally:
        config.RULES = original_rules

    record.update(
        {
            "case_id": case["id"],
            "case_title": case.get("title", ""),
            "mode": mode,
            "project_id": project,
            "wall_time_seconds": round(time.time() - started, 2),
            "fixtures": _fixture_hashes(case),
            "reproducibility": trace.reproducibility(fixture_hashes=_fixture_hashes(case)),
            "evidence_policy": effective_policy,
            "experiment": experiment or ("+".join(extra_skills) if extra_skills else ""),
            "extra_skills": extra_skills,
            "run_dir": str(target),
        }
    )
    record.setdefault("metrics", {})["wall_time_seconds"] = record["wall_time_seconds"]
    (target / "run.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def _run_pebs(case: dict[str, Any], *, mode: str, project: str, budgets: dict[str, int] | None, accept: bool) -> dict[str, Any]:
    engine = Engine(project)
    seed_case_artifacts(engine, case)
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
    from . import safety as safety_mod

    # §19/§39/§40：每次 benchmark run 都记入 performance registry（只 observe/record）
    from . import performance as performance_mod

    performance_mod.record_trace(skill_trace)

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
        "quality_metrics": safety_mod.content_metrics(engine.store),
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


def _wait_timeout(run: dict[str, Any]) -> float:
    """等待上限必须≥运行自身的时间预算，否则 harness 会在 run 仍运行时误报 running。"""
    budget = int(run.get("budget_seconds") or 0)
    return float(max(3600, budget + 600))


def _wait(engine: Engine, run_id: str, timeout: float | None = None) -> dict[str, Any]:
    if timeout is None:
        try:
            timeout = _wait_timeout(engine.store.get_run(run_id))
        except Exception:  # noqa: BLE001 - 取不到 budget 时退回 1 小时
            timeout = 3600.0
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
