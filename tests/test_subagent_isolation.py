from __future__ import annotations

import pytest
from conftest import REQUEST_1, run_dynamic_build

from pebs import pipeline, registry
from pebs.agents import (
    AgentContractError,
    IsolationViolation,
    RestrictedContext,
    Subagent,
    default_agents,
    for_skill,
)


class _StubContext:
    def __init__(self) -> None:
        self.outputs: dict[str, str] = {"script:sec1": "script:sec1@r1"}
        self.written: list[str] = []

    def content(self, artifact_id: str):
        return {"artifact_id": artifact_id}

    def rev(self, artifact_id: str):
        return self.outputs.get(artifact_id)

    def artifact_ids_of_type(self, artifact_type: str) -> list[str]:
        return [artifact_id for artifact_id in self.outputs if artifact_id.split(":", 1)[0] == artifact_type]

    def content_by_type(self, artifact_type: str):
        ids = self.artifact_ids_of_type(artifact_type)
        return self.content(ids[0]) if ids else None

    def emit(self, artifact_id, artifact_type, content, produced_by, deps=None):
        self.written.append(artifact_type)
        self.outputs[artifact_id] = f"{artifact_id}@r2"
        return {"revision_id": f"{artifact_id}@r2"}

    def sections(self):
        return [{"section_id": "sec1", "title": "t"}]

    def store(self):
        return None


def test_registry_agent_field_drives_dispatch():
    from pebs.agents.kinds import AGENT_NAMES

    for name, record in registry.load_skills().items():
        agent = for_skill(record)
        assert agent.name in AGENT_NAMES
        assert agent.name == record["agent"], f"{name} dispatched to {agent.name}, registry says {record['agent']}"


def test_declared_reads_are_allowed_and_undeclared_reads_blocked():
    ctx = RestrictedContext(
        _StubContext(), agent="media-agent", allowed_inputs=("script",), produces=("media_plan",), strict_reads=True
    )
    assert ctx.content("script:sec1") == {"artifact_id": "script:sec1"}
    with pytest.raises(IsolationViolation):
        ctx.content("evidence_index")
    with pytest.raises(IsolationViolation):
        ctx.rev("case:sec1:1")


def test_declared_writes_are_allowed_and_undeclared_writes_blocked():
    inner = _StubContext()
    ctx = RestrictedContext(
        inner, agent="media-agent", allowed_inputs=("script",), produces=("media_plan",), strict_reads=True
    )
    ctx.emit("media_plan:sec1", "media_plan", {}, "media-agent")
    assert inner.written == ["media_plan"]
    with pytest.raises(AgentContractError):
        ctx.emit("script:sec1", "script", {}, "media-agent")
    assert inner.written == ["media_plan"]


def test_capability_objects_are_unreachable_for_external_skills():
    inner = _StubContext()
    ctx = RestrictedContext(inner, agent="research-agent", allowed_inputs=("claims_set",), produces=("evidence_index",))
    for attribute in ("store", "evidence", "hooks", "permissions", "llm"):
        with pytest.raises(IsolationViolation):
            getattr(ctx, attribute)
    assert ctx.sections() == [{"section_id": "sec1", "title": "t"}]


def test_outputs_visibility_is_limited_to_the_contract():
    inner = _StubContext()
    inner.outputs["case:sec1:1"] = "case:sec1:1@r1"
    ctx = RestrictedContext(inner, agent="qa-agent", allowed_inputs=("script",), produces=("gate_result",))
    assert set(ctx.outputs) == {"script:sec1"}


def test_subagents_have_no_channel_to_each_other():
    agents = default_agents()
    for name, agent in agents.items():
        for other_name, other in agents.items():
            if name == other_name:
                continue
            assert other not in vars(agent).values()
    for attribute in ("send", "ask", "chat", "broadcast", "call_agent"):
        assert not hasattr(Subagent, attribute)


def test_agent_contract_comes_from_the_registry_record():
    agent = default_agents()["pedagogy-agent"]
    record = registry.get("script-writer")
    contract = agent.contract_for(record)
    assert contract.inputs == tuple(record["requires"])
    assert set(contract.outputs) == set(record.get("emits") or record["produces"])


def test_undeclared_output_fails_the_node(engine, monkeypatch):
    original = pipeline.step_requirements

    def leaky(ctx):
        ctx.emit("unexpected", "evidence_index", {}, "requirements-builder")
        return original(ctx)

    monkeypatch.setitem(pipeline.STEPS, "requirements", leaky)
    start, status = run_dynamic_build(engine, REQUEST_1)
    steps = {step["step_id"]: step for step in status["steps"]}
    assert steps["requirements-builder"]["status"] == "FAILED"
    assert "契约违规" in steps["requirements-builder"]["error"]
    assert engine.store.revisions_of("unexpected") == []
