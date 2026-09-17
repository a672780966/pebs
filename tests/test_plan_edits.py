from __future__ import annotations

import pytest
from conftest import REQUEST_1, run_build

from pebs.engine import PlanEditRejected


@pytest.fixture
def plan_engine(engine):
    run_id, changeset_id = run_build(engine, REQUEST_1)
    return engine


def test_disabling_required_step_is_rejected(plan_engine):
    with pytest.raises(PlanEditRejected):
        plan_engine.edit_plan("disable", "scripts")
    with pytest.raises(PlanEditRejected):
        plan_engine.edit_plan("disable", "gates")
    with pytest.raises(PlanEditRejected):
        plan_engine.edit_plan("disable", "export")


def test_illegal_reorder_is_rejected(plan_engine):
    with pytest.raises(PlanEditRejected):
        plan_engine.edit_plan("move", "requirements", 4)
    with pytest.raises(PlanEditRejected):
        plan_engine.edit_plan("move", "export", 0)
    with pytest.raises(PlanEditRejected):
        plan_engine.edit_plan("move", "scripts", 2)
    plan = plan_engine.current_plan()
    step = next(s for s in plan["steps"] if s["step_id"] == "requirements")
    assert step["depends_on"] == ["parse_inputs"]


def test_lock_and_unlock(plan_engine):
    plan = plan_engine.edit_plan("lock", "cases")
    locked = next(s for s in plan["steps"] if s["step_id"] == "cases")
    assert locked["locked"] is True
    plan = plan_engine.edit_plan("unlock", "cases")
    unlocked = next(s for s in plan["steps"] if s["step_id"] == "cases")
    assert unlocked["locked"] is False


def test_legal_reorder_is_accepted(plan_engine):
    plan = plan_engine.edit_plan("move", "preview", 20)
    order = [s["step_id"] for s in plan["steps"]]
    assert order.index("storyboard") < order.index("pptx") < order.index("gates") < order.index("preview") < order.index("export")
    assert order.index("parse_inputs") == 0
