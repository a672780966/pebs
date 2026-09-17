"""M6 §60：Input Budget —— 超限必须显式 reject/summarize，禁止静默截断。"""

from __future__ import annotations

import pytest
from conftest import REQUEST_1, FakeLLM, run_build

from pebs import config, input_budget


def test_budget_measure_and_enforce_rejects_over_limit():
    rules = {"max_material_chars": 10, "max_template_chars": 5, "max_sections": 2, "max_files": 1, "on_exceed": "reject"}
    measurement = input_budget.measure(
        materials=[{"name": "a.md", "text": "一二三四五六七八九十十一"}],
        template_spec={"raw_text": "模板"},
        sections=[{"section_id": "s1"}, {"section_id": "s2"}, {"section_id": "s3"}],
    )
    assert measurement["material_chars"] == 12
    problems = input_budget.exceeded(measurement, rules=rules)
    assert any("材料文本" in problem for problem in problems)
    assert any("章节数" in problem for problem in problems)
    with pytest.raises(input_budget.InputBudgetExceeded):
        input_budget.enforce(measurement, rules=rules)


def test_budget_summarize_mode_records_decision_without_truncating():
    rules = {"max_material_chars": 1, "max_template_chars": 1, "max_sections": 1, "max_files": 1, "on_exceed": "summarize"}
    measurement = input_budget.measure(materials=[{"name": "a.md", "text": "超过预算的材料"}])
    report = input_budget.enforce(measurement, rules=rules)
    assert report["decision"] == "summarize"
    assert report["problems"]
    assert "禁止静默截断" in report["note"]


def test_parse_inputs_rejects_oversize_material(engine, tmp_path, monkeypatch):
    rules = dict(config.RULES)
    rules["input_budget"] = {
        "max_material_chars": 20,
        "max_template_chars": 1000,
        "max_sections": 10,
        "max_files": 5,
        "on_exceed": "reject",
    }
    monkeypatch.setattr(config, "RULES", rules)
    material = tmp_path / "big.md"
    material.write_text("观察记录" * 30, encoding="utf-8")
    run_id, changeset_id = run_build(engine, REQUEST_1, material_paths=[material])
    status = engine.run_status(run_id)
    step = next(item for item in status["steps"] if item["step_id"] == "parse_inputs")
    assert step["status"] == "FAILED"
    assert "输入超出预算" in (step["error"] or "")
    assert "静默截断" in (step["error"] or "")


def test_budget_report_is_recorded_in_materials(engine):
    run_id, changeset_id = run_build(engine, REQUEST_1)
    engine.accept(changeset_id)
    materials = engine.store.accepted_content("materials")
    assert "budget_report" in materials
    report = materials["budget_report"]
    assert report["decision"] == "accept"
    assert report["limits"]["max_material_chars"] > 0
