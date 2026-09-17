from __future__ import annotations

import threading
import time

from conftest import REQUEST_2, run_dynamic_build

from pebs import config
from pebs.runtime import executor


def _instrument(monkeypatch):
    records: list[tuple[str, int, float, float]] = []
    lock = threading.Lock()
    original = executor._Runner._builtin_handler

    def wrapper(self, ctx, node, record):
        started = time.time()
        thread_id = threading.get_ident()
        try:
            return original(self, ctx, node, record)
        finally:
            with lock:
                records.append((node["node_id"], thread_id, started, time.time()))

    monkeypatch.setattr(executor._Runner, "_builtin_handler", wrapper)
    return records


def _overlaps(records):
    pairs = []
    for index, first in enumerate(records):
        for second in records[index + 1 :]:
            if first[0] == second[0]:
                continue
            if first[2] < second[3] and second[2] < first[3] and first[1] != second[1]:
                pairs.append((first[0], second[0]))
    return pairs


def test_independent_nodes_run_in_parallel(engine, monkeypatch):
    records = _instrument(monkeypatch)
    start, status = run_dynamic_build(engine, REQUEST_2)
    assert status["run"]["status"] == "succeeded", [
        (step["step_id"], step["status"], step["error"]) for step in status["steps"]
    ]
    plan = engine.store.accepted_content("build_plan_dynamic")
    groups: dict[int, list[str]] = {}
    for node in plan["nodes"]:
        groups.setdefault(int(node["parallel_group"]), []).append(node["node_id"])
    parallel_groups = [nodes for nodes in groups.values() if len(nodes) > 1]
    assert parallel_groups, "planner produced no parallel group"
    overlapping = set(_overlaps(records))
    assert overlapping, f"no node pair overlapped in time; groups={parallel_groups}"


def test_nodes_respect_dependency_order(engine, monkeypatch):
    records = _instrument(monkeypatch)
    start, status = run_dynamic_build(engine, REQUEST_2)
    assert status["run"]["status"] == "succeeded"
    plan = engine.store.accepted_content("build_plan_dynamic")
    starts = {node_id: started for node_id, _, started, _ in records}
    ends = {node_id: ended for node_id, _, _, ended in records}
    for node in plan["nodes"]:
        for dependency in node.get("depends_on", []):
            if dependency in ends and node["node_id"] in starts:
                assert ends[dependency] <= starts[node["node_id"]] + 1e-6, (
                    f"{node['node_id']} started before dependency {dependency} finished"
                )


def test_concurrency_limits_come_from_config(engine):
    runner = executor._Runner(engine, engine._new_context(
        run_id="run_probe",
        changeset_id="cs_probe",
        request="probe",
        template_path=None,
        material_paths=[],
        environment="production",
    ))
    runtime_cfg = config.RULES["runtime"]
    assert runner.max_workers >= (
        runtime_cfg["max_parallel_llm"] + runtime_cfg["max_parallel_research"] + runtime_cfg["max_parallel_sandbox"]
    )
    assert set(runner.semaphores) == {"llm", "research", "sandbox"}
    kinds = {
        "builtin-research": executor._node_kind({"runtime": "builtin", "estimated_cost": {"research_calls": 1}}),
        "builtin-llm": executor._node_kind({"runtime": "builtin", "estimated_cost": {"model_calls": 2}}),
        "builtin-local": executor._node_kind({"runtime": "builtin", "estimated_cost": {}}),
        "prompt": executor._node_kind({"runtime": "prompt_skill"}),
        "sandbox": executor._node_kind({"runtime": "sandbox_skill"}),
    }
    assert kinds == {
        "builtin-research": "research",
        "builtin-llm": "llm",
        "builtin-local": "local",
        "prompt": "llm",
        "sandbox": "sandbox",
    }


def test_research_concurrency_is_capped(engine, monkeypatch):
    """同一时间进入 research 节点的数量不得超过 max_parallel_research。"""
    live = {"current": 0, "peak": 0}
    lock = threading.Lock()
    original = executor._Runner._builtin_handler

    def wrapper(self, ctx, node, record):
        kind = executor._node_kind(record)
        if kind != "research":
            return original(self, ctx, node, record)
        with lock:
            live["current"] += 1
            live["peak"] = max(live["peak"], live["current"])
        time.sleep(0.05)
        try:
            return original(self, ctx, node, record)
        finally:
            with lock:
                live["current"] -= 1

    monkeypatch.setattr(executor._Runner, "_builtin_handler", wrapper)
    start, status = run_dynamic_build(engine, REQUEST_2)
    assert status["run"]["status"] == "succeeded"
    assert live["peak"] <= config.RULES["runtime"]["max_parallel_research"]


def test_recorded_gate_failure_blocks_node(engine):
    """A recorded FAIL result blocks the node that declares that gate."""
    from conftest import run_dynamic_build  # noqa: F401  (kept for symmetry)
    from pebs import gates

    run_id = engine.store.create_run(request="gate probe")
    changeset_id = engine.store.create_changeset(run_id, "gate probe", engine.store.current_baseline())
    artifact_id = gates.gate_artifact_id("G1", "script:sec1")
    info = engine.store.add_revision(
        artifact_id=artifact_id,
        artifact_type="gate_result",
        content={
            "gate_id": "G1",
            "target": {"artifact_id": "script:sec1", "revision_id": "script:sec1@r1"},
            "status": "FAIL",
            "issues": [{"code": "probe", "message": "probe"}],
        },
        produced_by="test",
    )
    engine.store.set_accepted(artifact_id, info["revision_id"])
    ctx = engine._new_context(
        run_id=run_id,
        changeset_id=changeset_id,
        request="gate probe",
        template_path=None,
        material_paths=[],
        environment="production",
    )
    plan = {
        "nodes": [
            {
                "node_id": "gate-probe",
                "skill": "case-designer",
                "parallel_group": 0,
                "depends_on": [],
                "inputs": ["script:sec1"],
                "outputs": ["case:sec1:1"],
                "gate_before": ["G1"],
            }
        ]
    }
    executor.execute_plan(engine=engine, run_id=run_id, ctx=ctx, plan=plan)
    step = next(item for item in engine.store.get_steps(run_id) if item["step_id"] == "gate-probe")
    assert step["status"] == "BLOCKED"
    assert "G1@script:sec1" in (step["error"] or "")


def test_missing_gate_result_blocks_export(engine):
    """Absent gate evidence fails closed where it is authoritative: export."""
    from pebs import gates

    info = engine.store.add_revision(
        artifact_id="script:sec1",
        artifact_type="script",
        content={"units": [{"text": "probe"}]},
        produced_by="test",
    )
    engine.store.set_accepted("script:sec1", info["revision_id"])
    readiness = gates.export_readiness(engine.store)
    assert readiness["ready"] is False
    unrun = [item for item in readiness["blocking"] if "script:sec1" in item]
    assert len(unrun) >= 7, readiness["blocking"]


def test_budget_exhaustion_aborts_remaining_nodes(engine):
    """One budget abort must not let every later node re-fail."""
    start, status = run_dynamic_build(
        engine, REQUEST_2, budgets={"model_calls": 0, "research_requests": 0, "run_seconds": 60}
    )
    assert status["run"]["status"] != "succeeded"
    unfinished = [
        (step["step_id"], step["status"], step["error"])
        for step in status["steps"]
        if step["status"] != "SUCCEEDED"
    ]
    assert unfinished, "expected the exhausted budget to block this run"
    assert all(state == "BLOCKED" for _, state, _ in unfinished), unfinished
    assert any("已中止后续步骤" in (error or "") for _, _, error in unfinished), unfinished
    assert start["run_id"]


def test_resume_re_runs_blocked_steps(engine):
    """Section 84: raise the budget and the blocked work runs to completion."""
    start, status = run_dynamic_build(
        engine, REQUEST_2, budgets={"model_calls": 0, "research_requests": 0, "run_seconds": 60}
    )
    blocked = [step["step_id"] for step in status["steps"] if step["status"] == "BLOCKED"]
    assert blocked, [(step["step_id"], step["status"], step["error"]) for step in status["steps"]]

    result = engine.resume(
        start["run_id"], budgets={"model_calls": 400, "research_requests": 400, "run_seconds": 3600}
    )
    assert result["resumed"], result
    after = engine.run_status(start["run_id"])
    assert after["run"]["status"] == "succeeded", [
        (step["step_id"], step["status"], step["error"]) for step in after["steps"]
    ]
