from __future__ import annotations

import pytest
from conftest import REQUEST_1, run_build

from pebs.engine import ExplicitSkillDenied
from pebs.pipeline import parse_explicit_skills


def test_parse_explicit_skills():
    request = "任务1 观察记录。\n/evidence-review\n/script-writer 每节 200 字。"
    assert parse_explicit_skills(request) == ["evidence-review", "script-writer"]
    assert parse_explicit_skills("路径 /usr/local 与日期 2024/05 不匹配") == []


def test_explicit_invocation_is_recorded(engine):
    run_id, changeset_id = run_build(engine, REQUEST_1 + "\n/evidence-review")
    invocations = engine.store.get_revision(engine.store.revisions_of("skill_invocations")[-1])["content"]
    assert invocations["requested"] == ["evidence-review"]
    resolved = invocations["resolved"][0]
    assert resolved["skill"] == "evidence-reviewer"
    assert resolved["requested_as"] == "evidence-review"
    assert resolved["steps"] == ["evidence", "evidence_topup"]
    step = next(s for s in engine.store.get_steps(run_id) if s["step_id"] == "parse_inputs")
    assert "显式调用" in (step["note"] or "")
    preview = engine.store.get_revision(engine.store.revisions_of("preview")[-1])["content"]["markdown"]
    assert "/evidence-review" in preview


def test_unknown_or_unauthorized_skill_denied_before_run(engine):
    with pytest.raises(ExplicitSkillDenied):
        engine.start_build("/skills-mgr 帮我写课程")
    with pytest.raises(ExplicitSkillDenied):
        engine.start_build("/not-a-real-skill 帮我写课程")
    assert engine.store.list_changesets() == []


def test_explicit_evidence_review_forces_reassessment(engine):
    run_id, changeset_id = run_build(engine, REQUEST_1 + "\n/evidence-review")
    step = next(s for s in engine.store.get_steps(run_id) if s["step_id"] == "evidence")
    assert "重新核验" in (step["note"] or "")
