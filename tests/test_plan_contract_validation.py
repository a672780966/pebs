"""Stage E/3: static gate + precondition contract validation.

Gate applicability comes from the deliverable contract (plan terminal outputs) only -
never from artifact reuse. Evaluator identity is the runtime step. Ordering, evaluator
data ordering, the reused-evaluator guard and precondition truthfulness are all
validated statically, before anything executes.
"""

from __future__ import annotations

import pytest

from pebs import gates, preconditions
from pebs.planner import planner, validation
from pebs.planner.contracts import KNOWN_GATES, PlanNode

# Registry-consistent node templates (steps must match registry/skills.json).
SCRIPT_NODE = dict(steps=["scripts"], inputs=["teaching_plan", "evidence_index"], outputs=["script"])
GATE_NODE = dict(steps=["gates"], inputs=["script", "evidence_index"], outputs=["gate_result"])
ANIMATION_NODE = dict(steps=["storyboard"], inputs=["media_plan", "script"], outputs=["animation_decisions"])
PREVIEW_NODE = dict(steps=["preview"], inputs=["script"], outputs=["preview"])
STORYBOARD_NODE = dict(steps=["storyboard"], inputs=["animation_decisions"], outputs=["storyboard"])
DIAGRAM_NODE = dict(steps=["diagrams"], inputs=["media_plan"], outputs=["diagrams"])
LESSON_NODE = dict(steps=["lesson_plans"], inputs=["teaching_plan"], outputs=["lesson_plan"])
PPTX_NODE = dict(steps=["pptx"], inputs=["slide_plan"], outputs=["pptx_deck"])
EXPORT_NODE = dict(steps=["export"], inputs=["preview"], outputs=["export_manifest"])
EVIDENCE_NODE = dict(steps=["evidence", "evidence_topup"], inputs=["claims_set"], outputs=["evidence_index"])
PCK_NODE = dict(steps=["teaching_plan"], inputs=["learning_design", "evidence_index"], outputs=["teaching_plan"])


def _node(node_id, *, steps=(), inputs=(), outputs=(), depends_on=(), gate_before=(), gate_after=(),
          preconditions_=(), reused=False):
    return {
        "node_id": node_id,
        "title": node_id,
        "skill": node_id,
        "steps": list(steps),
        "inputs": list(inputs),
        "outputs": list(outputs),
        "depends_on": list(depends_on),
        "gate_before": list(gate_before),
        "gate_after": list(gate_after),
        "preconditions": [dict(item) for item in preconditions_],
        "reused": reused,
    }


def _plan(nodes, terminals, reused_artifacts=()):
    return {
        "nodes": nodes,
        "terminal_outputs": list(terminals),
        "reused_artifacts": list(reused_artifacts),
        "estimated": {},
    }


def _script_route(*extra):
    """A minimal valid script route: requirements -> script -> gate-runner."""
    return [
        _node("requirements-builder", steps=["requirements"], outputs=["requirements"]),
        _node("script-writer", depends_on=["requirements-builder"], **SCRIPT_NODE),
        _node("gate-runner", depends_on=["script-writer"], **GATE_NODE),
    ] + list(extra)


# --------------------------------------------------------------- map invariants
def test_gate_contract_map_keys_are_identical():
    keys = [
        set(KNOWN_GATES),
        set(gates.ALL_GATES),
        set(gates.GATE_FUNCTIONS),
        set(gates.GATE_SCOPE),
        set(gates.GATE_EVALUATOR_STEP),
        set(gates.GATE_OBSERVED_ARTIFACTS),
    ]
    assert all(keys[0] == other for other in keys[1:])


def test_precondition_contract_map_keys_are_identical():
    assert set(preconditions.PRECONDITION_CONTRACTS) == set(preconditions.PRECONDITION_KINDS)
    assert set(preconditions.PRECONDITION_CONTRACTS) == set(preconditions.CHECKERS)


def test_evaluator_step_and_intra_step_contract():
    assert gates.GATE_EVALUATOR_STEP["G6"] == "gates"
    assert gates.GATE_EVALUATOR_STEP["G8"] == "export"
    assert gates.GATE_CONTRACTS["G8"]["produced_and_evaluated_in_same_step"] == ["export_manifest"]


def test_unknown_gate_declaration_survives_construction_and_fails_validation():
    # An unknown declaration must not be filtered away during construction.
    assert PlanNode(node_id="x", title="x", skill="x", gate_before=["G9"]).to_dict()["gate_before"] == ["G9"]
    plan = _plan(_script_route(_node("animation-gate", gate_before=["G9"], **ANIMATION_NODE)), ["script"])
    assert any("未知 Gate G9" in error for error in validation.validate_plan(plan))


# ------------------------------------------------------------ gate applicability
def test_applicable_gate_without_evaluator_is_invalid():
    nodes = [
        _node("requirements-builder", steps=["requirements"], outputs=["requirements"]),
        _node("script-writer", depends_on=["requirements-builder"], **SCRIPT_NODE),
        _node("animation-gate", gate_before=["G6"], **ANIMATION_NODE),
    ]
    errors = validation.validate_plan(_plan(nodes, ["script"]))
    assert any("没有可执行的评估方" in error for error in errors), errors


def test_inapplicable_gate_without_evaluator_is_valid():
    nodes = [
        _node("lesson-designer", **LESSON_NODE),
        _node("animation-gate", gate_before=["G6"], **ANIMATION_NODE),
    ]
    assert validation.validate_plan(_plan(nodes, ["lesson_plan"])) == []


def test_reused_script_with_pptx_terminal_keeps_script_gates_inapplicable():
    """Reuse must never make a gate applicable: the terminal contract decides."""
    nodes = [
        _node("script-writer", reused=True, **SCRIPT_NODE),
        _node("animation-gate", gate_before=["G6"], **ANIMATION_NODE),
        _node("presentation-composer", **PPTX_NODE),
        _node("docx-exporter", depends_on=["presentation-composer"], **EXPORT_NODE),
    ]
    assert validation.validate_plan(_plan(nodes, ["export_manifest", "pptx_deck"], ["script"])) == []


# ------------------------------------------------------------- declaration order
def test_gate_before_evaluator_ancestor_is_valid():
    nodes = _script_route(
        _node("preview-builder", gate_before=["G6"], depends_on=["gate-runner"], **PREVIEW_NODE)
    )
    assert validation.validate_plan(_plan(nodes, ["script"])) == []


def test_gate_before_evaluator_unordered_is_invalid():
    nodes = _script_route(_node("preview-builder", gate_before=["G6"], **PREVIEW_NODE))
    errors = validation.validate_plan(_plan(nodes, ["script"]))
    assert any("评估方必须先于该节点运行" in error for error in errors), errors


def test_gate_after_evaluator_descendant_is_valid():
    nodes = [
        _node("requirements-builder", steps=["requirements"], outputs=["requirements"]),
        _node("script-writer", depends_on=["requirements-builder"], **SCRIPT_NODE),
        _node("animation-gate", gate_after=["G6"], depends_on=["script-writer"], **ANIMATION_NODE),
        _node("gate-runner", depends_on=["animation-gate", "script-writer"], **GATE_NODE),
    ]
    assert validation.validate_plan(_plan(nodes, ["script"])) == []


def test_gate_after_evaluator_unordered_is_invalid():
    nodes = [
        _node("requirements-builder", steps=["requirements"], outputs=["requirements"]),
        _node("script-writer", depends_on=["requirements-builder"], **SCRIPT_NODE),
        _node("animation-gate", gate_after=["G6"], depends_on=["script-writer"], **ANIMATION_NODE),
        _node("gate-runner", depends_on=["script-writer"], **GATE_NODE),
    ]
    errors = validation.validate_plan(_plan(nodes, ["script"]))
    assert any("评估方必须晚于该节点运行" in error for error in errors), errors


# --------------------------------------------------------- evaluator data ordering
def _storyboard_route(*extra):
    return [
        _node("requirements-builder", steps=["requirements"], outputs=["requirements"]),
        _node("script-writer", depends_on=["requirements-builder"], **SCRIPT_NODE),
        _node("animation-gate", **ANIMATION_NODE),
        _node("storyboard-designer", depends_on=["animation-gate"], **STORYBOARD_NODE),
    ] + list(extra)


def test_observed_producer_before_evaluator_is_valid():
    nodes = _storyboard_route(
        _node("gate-runner", depends_on=["storyboard-designer", "script-writer"], **GATE_NODE)
    )
    assert validation.validate_plan(_plan(nodes, ["script", "storyboard"])) == []


def test_observed_producer_after_evaluator_is_invalid():
    """animation-gate ordered, but the storyboard producer is still after the evaluator."""
    nodes = _storyboard_route(_node("gate-runner", depends_on=["animation-gate"], **GATE_NODE))
    errors = validation.validate_plan(_plan(nodes, ["script", "storyboard"]))
    assert any("必须晚于 storyboard 的生产者 storyboard-designer" in error for error in errors), errors


def test_diagram_producer_unordered_after_evaluator_is_invalid():
    nodes = _script_route(_node("diagram-designer", **DIAGRAM_NODE))
    errors = validation.validate_plan(_plan(nodes, ["script"]))
    assert any("diagrams 的生产者 diagram-designer" in error for error in errors), errors


def test_absent_optional_observed_artifact_is_not_an_error():
    """G6 observes load_review; no producer planned is not a static failure."""
    nodes = _storyboard_route(_node("gate-runner", depends_on=["storyboard-designer"], **GATE_NODE))
    assert not any("load_review" in error for error in validation.validate_plan(_plan(nodes, ["script"])))


def test_producer_equal_to_evaluator_is_invalid_for_a_normal_observed_artifact():
    """Only the explicitly intra-step artifact may be produced by the evaluator itself."""
    nodes = [
        _node("requirements-builder", steps=["requirements"], outputs=["requirements"]),
        _node("script-writer", depends_on=["requirements-builder"], **SCRIPT_NODE),
        _node("gate-runner", steps=["gates"], inputs=["script"], outputs=["gate_result", "storyboard"],
              depends_on=["script-writer"]),
    ]
    errors = validation.validate_plan(_plan(nodes, ["script"]))
    assert any("不能同时是 storyboard 的生产者" in error for error in errors), errors


def test_g8_intra_step_export_manifest_is_allowed():
    nodes = [
        _node("presentation-composer", **PPTX_NODE),
        _node("docx-exporter", depends_on=["presentation-composer"], **EXPORT_NODE),
    ]
    assert validation.validate_plan(_plan(nodes, ["export_manifest", "pptx_deck"])) == []


# --------------------------------------------------------- reused evaluator guard
def test_reused_evaluator_does_not_satisfy_reachability():
    nodes = _script_route(
        _node("animation-gate", gate_before=["G6"], **ANIMATION_NODE),
    )
    nodes[-2] = _node("gate-runner", reused=True, depends_on=["script-writer"], **GATE_NODE)
    errors = validation.validate_plan(_plan(nodes, ["script"]))
    assert any("没有可执行的评估方" in error for error in errors), errors


# --------------------------------------------------------- precondition contract
def test_supported_claims_with_correct_input_is_valid():
    nodes = _script_route(
        _node("evidence-reviewer", **EVIDENCE_NODE),
        _node("pck-developer", preconditions_=[{"kind": "supported_claims", "inputs": ["evidence_index"]}], **PCK_NODE),
    )
    nodes[2] = _node("gate-runner", depends_on=["script-writer", "pck-developer"], **GATE_NODE)
    assert validation.validate_plan(_plan(nodes, ["script"])) == []


def test_supported_claims_with_reachable_but_wrong_input_is_invalid():
    nodes = _script_route(
        _node("claim-extractor", steps=["claims"], inputs=["requirements"], outputs=["claims_set"]),
        _node("pck-developer", steps=["teaching_plan"], inputs=["learning_design", "claims_set"],
              outputs=["teaching_plan"],
              preconditions_=[{"kind": "supported_claims", "inputs": ["claims_set"]}]),
    )
    errors = validation.validate_plan(_plan(nodes, ["script"]))
    assert any("与检查器契约不兼容" in error for error in errors), errors


def test_supported_claims_missing_declared_input_is_invalid():
    nodes = _script_route(
        _node("pck-developer", preconditions_=[{"kind": "supported_claims", "inputs": []}], **PCK_NODE)
    )
    errors = validation.validate_plan(_plan(nodes, ["script"]))
    assert any("作用域无法解析" in error for error in errors), errors


def test_unimplemented_precondition_kind_is_invalid():
    nodes = _script_route(
        _node("pck-developer", preconditions_=[{"kind": "not_a_kind", "inputs": ["evidence_index"]}], **PCK_NODE)
    )
    assert any("未实现的前置条件" in error for error in validation.validate_plan(_plan(nodes, ["script"])))


def test_precondition_input_without_producer_or_reuse_is_invalid():
    nodes = _script_route(
        _node("pck-developer", preconditions_=[{"kind": "supported_claims", "inputs": ["evidence_index"]}], **PCK_NODE)
    )
    assert any("不可达" in error for error in validation.validate_plan(_plan(nodes, ["script"])))


# --------------------------------------------------------- live plan + topology
@pytest.mark.parametrize(
    "requested",
    [["script"], ["script", "storyboard"], ["script", "pptx"], ["pptx"], ["lesson_plan"], ["lesson_plan", "pptx"]],
)
def test_live_plans_validate_clean(requested):
    plan = planner.plan(route={"requested_outputs": requested, "constraints": {}}, goal="probe")
    assert validation.validate_plan(plan) == []


def test_planner_orders_an_applicable_evaluator_after_every_observed_producer():
    plan = planner.plan(route={"requested_outputs": ["script", "storyboard"], "constraints": {}}, goal="probe")
    nodes = {node["node_id"]: node for node in plan["nodes"]}
    evaluator = nodes["gate-runner"]
    assert not evaluator["reused"]
    for observed, producer in (
        ("animation_decisions", "animation-gate"),
        ("storyboard", "storyboard-designer"),
        ("media_plan", "media-router"),
        ("requirements", "requirements-builder"),
    ):
        assert producer in nodes, f"{producer} should be planned for {observed}"
        assert producer in evaluator["depends_on"], (observed, producer, evaluator["depends_on"])
    assert evaluator["parallel_group"] > nodes["animation-gate"]["parallel_group"]
    assert evaluator["parallel_group"] > nodes["storyboard-designer"]["parallel_group"]
