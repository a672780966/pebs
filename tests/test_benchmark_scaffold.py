from __future__ import annotations

import json
from pathlib import Path

from pebs.benchmark import checks, cases, metrics, performance, report, trace


def test_golden_cases_exist_and_validate():
    loaded = cases.load_cases()
    ids = {case["id"] for case in loaded}
    assert {"A", "B", "C", "D", "E", "F", "G"} <= ids
    for case in loaded:
        errors = cases.validate_case(case)
        assert not errors, errors


def test_fixtures_are_synthetic_and_present():
    lecture = cases.fixtures_dir() / "lecture" / "existing_psychology_lecture.md"
    assert lecture.exists()
    research = json.loads((cases.fixtures_dir() / "research" / "phone_anxiety_papers.json").read_text(encoding="utf-8"))
    assert research["synthetic"] is True
    assert len(research["results"]) >= 3
    for result in research["results"]:
        assert result["doi"].startswith("10.0000/")


def test_failure_taxonomy_covers_required_categories():
    import yaml

    data = yaml.safe_load((cases.benchmark_dir() / "failure_taxonomy.yaml").read_text(encoding="utf-8"))
    ids = {item["id"] for item in data["categories"]}
    required = {
        "ROUTING",
        "PLANNING",
        "EVIDENCE",
        "CONTENT",
        "PEDAGOGY",
        "ASSESSMENT",
        "MEDIA",
        "TEMPLATE",
        "RUNTIME",
        "SKILL",
        "SCHEMA",
        "LOCALITY",
        "SAFETY",
        "PRIVACY",
        "EXPORT",
    }
    assert required <= ids


def test_human_rubric_has_fourteen_dimensions():
    import yaml

    data = yaml.safe_load((cases.benchmark_dir() / "rubrics" / "human_eval.yaml").read_text(encoding="utf-8"))
    assert len(data["dimensions"]) == 14
    assert {"score", "comment", "must_fix", "nice_to_have"} <= set(data["notes_required"])


def test_plan_and_routing_checks_detect_errors():
    expect = {
        "plan": {
            "must_include_steps": ["learning_design"],
            "must_exclude_steps": ["pptx"],
            "min_reuse_rate": 0.5,
            "must_reuse_artifact_types": ["script"],
        },
        "routing": {"knowledge_types_any_of": ["attitude"], "requested_outputs": ["lesson_plan"]},
    }
    plan = {
        "nodes": [
            {"skill": "pptx", "steps": ["pptx"], "reused": False, "outputs": ["pptx_deck"]},
            {"skill": "slide-plan", "steps": ["slide_plan"], "reused": True, "outputs": ["slide_plan"]},
        ],
        "terminal_outputs": ["pptx_deck"],
    }
    route = {"knowledge_types": ["concept"], "requested_outputs": ["script"]}
    result = checks.evaluate(_EmptyStore(), expect, plan=plan, route=route)
    kinds = {issue["kind"] for issue in result["issues"]}
    assert {"PLANNING", "ROUTING"} <= kinds
    assert result["ok"] is False


class _EmptyStore:
    def list_artifacts(self):
        return []


def test_report_builds_mode_comparison_table():
    runs = [
        {
            "case_id": "A",
            "mode": "builtin",
            "run_id": "r1",
            "metrics": {"model_calls": 10, "wall_time_seconds": 120},
            "human_eval": {
                "scores": {"subject_accuracy": 4, "teaching_logic": 3},
                "edit_ratio": 0.2,
                "evidence_errors": 1,
                "routing_errors": 0,
            },
        },
        {
            "case_id": "A",
            "mode": "dynamic",
            "run_id": "r2",
            "metrics": {"model_calls": 8, "wall_time_seconds": 140},
            "human_eval": {"scores": {"subject_accuracy": 5, "teaching_logic": 4}, "edit_ratio": 0.1, "evidence_errors": 0, "routing_errors": 1},
        },
    ]
    summary = report.summarize(runs)
    case_a = next(item for item in summary["cases"] if item["case_id"] == "A")
    assert case_a["builtin"]["human_score"] == 3.5
    assert case_a["dynamic"]["human_score"] == 4.5
    assert case_a["dynamic"]["evidence_errors"] == 0
    markdown = report.render_markdown(summary)
    assert "| A | dynamic |" in markdown
    assert "Evidence Errors" in markdown


def test_metrics_edit_ratio_and_locality():
    ratio = metrics.teacher_edit_ratio("一二三四五六七八九十", "一二三四五六七八九十一二")
    assert ratio["generated_chars"] == 10
    assert ratio["edited_chars"] == 12
    assert ratio["edit_ratio"] > 0
    locality = metrics.locality_report(
        {"script:sec1": "a", "script:sec2": "b"},
        {"script:sec1": "a", "script:sec2": "c"},
        preserve=["script:sec1"],
    )
    assert locality["preserve_violations"] == []
    assert locality["locality_preservation_rate"] == 1.0
    broken = metrics.locality_report(
        {"script:sec1": "a"}, {"script:sec1": "b"}, preserve=["script:sec1"]
    )
    assert broken["preserve_violations"] == ["script:sec1"]


def test_performance_registry_records_versions_and_promotion(tmp_path, monkeypatch):
    from pebs import config

    monkeypatch.setattr(config, "REGISTRY_DIR", tmp_path)
    record = performance.record_run(
        skill="dual-coding-designer",
        version="sha-abc",
        provider_sha="sha-abc",
        package_sha256="pkg-1",
        patch="dual-coding-pebs-1",
        domain="media",
        success=True,
        model_calls=2,
        latency=1.5,
        human_score=4.0,
        edit_ratio=0.12,
    )
    assert record["runs"] == 1
    assert record["success_rate"] == 1.0
    assert record["provider_sha"] == "sha-abc"
    saved = json.loads((Path(tmp_path) / "performance.json").read_text(encoding="utf-8"))
    assert saved["skills"]["dual-coding-designer"]["version"] == "sha-abc"

    for _ in range(9):
        record = performance.record_run(skill="dual-coding-designer", version="sha-abc", success=True, human_score=4.0)
    decision = performance.promotion_decision(record)
    assert record["runs"] == 10
    assert decision["eligible"] is True

    demotion = performance.demotion_decision(safety_regression=True)
    assert demotion["demote"] is True


def test_trace_identity_is_bound_to_skill_version():
    identity = trace._skill_identity("script-writer")
    assert identity["skill"] == "script-writer"
    assert identity["runtime"] == "builtin"
    assert identity["agent"] == "pedagogy-agent"
    reproduce = trace.reproducibility(fixture_hashes={"t.docx": "abc"})
    assert reproduce["registry_hash"]
    assert reproduce["rules_version"].startswith("rules-")
    assert reproduce["fixture_hashes"] == {"t.docx": "abc"}
