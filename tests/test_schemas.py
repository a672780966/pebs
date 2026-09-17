from __future__ import annotations

from pebs import schemas
from pebs.pipeline import count_words


def test_count_words_counts_narration_and_case_only():
    units = [
        {"unit_id": "u1", "kind": "title", "text": "标题不应计数"},
        {"unit_id": "u2", "kind": "narration", "text": "这是讲解正文。"},
        {"unit_id": "u3", "kind": "visual", "text": "画面指令不应计数"},
        {"unit_id": "u4", "kind": "case", "text": "案例正文计入。"},
        {"unit_id": "u5", "kind": "note", "text": "备注不应计数"},
    ]
    expected = len("这是讲解正文。") + len("案例正文计入。")
    assert count_words(units) == expected


def test_count_words_ignores_whitespace_keeps_punctuation():
    units = [{"unit_id": "u1", "kind": "narration", "text": "a b，c。 1 2"}]
    assert count_words(units) == len("ab，c。12")


def test_requirements_schema_rejects_missing_sections():
    bad = {"project_id": "p", "course": "c", "language": "zh", "outputs": [], "items": []}
    try:
        schemas.validate(bad, "requirements")
        raised = False
    except schemas.SchemaError:
        raised = True
    assert raised


def test_gate_result_not_applicable_requires_reason():
    result = {
        "gate_id": "G6",
        "check_version": "g6-1.0",
        "target": {"artifact_id": "script:sec1", "revision_id": "script:sec1@r1", "content_hash": "x"},
        "rules_version": "rules-x",
        "status": "NOT_APPLICABLE",
        "issues": [],
        "run_id": "run_1",
        "created_at": "2026-01-01T00:00:00",
    }
    try:
        schemas.validate(result, "gate_result")
        raised = False
    except schemas.SchemaError:
        raised = True
    assert raised
    result["not_applicable_reason"] = "无动画候选"
    schemas.validate(result, "gate_result")


def test_evidence_assessment_rejects_unknown_support_relation():
    bad = {
        "assessment_id": "a1",
        "claim_id": "clm_x",
        "claim_version": 1,
        "source_id": "src_x",
        "source_version": 1,
        "quote": "quote",
        "quote_location": "",
        "support": "sort-of",
        "result": "SUPPORTED",
        "method": "m",
        "method_version": "0",
        "verified_at": "2026-01-01T00:00:00",
    }
    try:
        schemas.validate(bad, "evidence_assessment")
        raised = False
    except schemas.SchemaError:
        raised = True
    assert raised
