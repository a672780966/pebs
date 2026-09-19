from __future__ import annotations

import pytest
from conftest import REQUEST_1, run_build

from pebs import pii
from pebs.engine import PiiBlocked


def test_scan_detects_common_pii():
    text = "学生：张三 学号：20230001 家长李四 姓名：王五 手机 13800138000 邮箱 zhang@example.com 身份证 11010519491231002X"
    hits = pii.scan(text)
    kinds = {hit["type"] for hit in hits}
    assert {"named_student", "student_id", "phone", "email", "id_card", "name_label"} <= kinds
    assert all(hit["masked"] for hit in hits)


def test_common_course_text_not_flagged():
    safe = [
        "观察记录应区分事实与判断。",
        "幼儿午睡时翻来覆去属于行为描述。",
        "学生甲与三名同伴坐在靠窗一侧。",
        "皮亚杰的认知发展理论强调阶段。",
    ]
    for text in safe:
        assert pii.scan(text) == [], text


def test_build_excludes_sensitive_material_from_prompts(engine, tmp_path):
    material = tmp_path / "家长联系表.txt"
    material.write_text("学生：张三 学号：20230001 家长李四 手机 13800138000", encoding="utf-8")
    run_id, changeset_id = run_build(engine, REQUEST_1, material_paths=[material])
    materials = engine.store.get_revision(engine.store.revisions_of("materials")[-1])["content"]
    entry = materials["files"][0]
    assert entry["sensitive"] is True
    assert "student_id" in entry["pii_types"]
    assert engine.llm.prompts, "build should have produced prompts"
    assert all("张三" not in prompt and "13800138000" not in prompt for prompt in engine.llm.prompts)
    step = next(s for s in engine.store.get_steps(run_id) if s["step_id"] == "parse_inputs")
    assert "可识别学生资料" in (step["note"] or "")
    preview = engine.store.get_revision(engine.store.revisions_of("preview")[-1])["content"]["markdown"]
    assert "材料警示" in preview
    user_sources = [s for s in engine.evidence.sources() if s["source_type"] == "user_material"]
    assert user_sources == []


def test_request_with_pii_pauses_before_any_send(engine):
    with pytest.raises(PiiBlocked) as excinfo:
        engine.start_build("请给张三同学写一段课堂评语，联系电话 13800138000。")
    assert "发送前暂停" in str(excinfo.value)
    assert engine.store.list_changesets() == []


def test_masked_summary_does_not_leak_full_value():
    hits = pii.scan("学号：20230001")
    summary = pii.summarize(hits)
    assert "20230001" not in summary


def test_safety_review_requests_are_not_blocked_as_pii():
    """M6 49/35: adversarial safety-review requests are not named-student PII."""
    from pebs.benchmark import cases

    request = cases.get_case("H")["request"]
    assert pii.scan(request) == [], pii.scan(request)
    assert pii.scan("这个总独处的学生可能是什么心理疾病？") == []
    assert pii.scan("所以这个学生一定是焦虑的。") == []
    # real named students still fire
    assert pii.scan("学生：小明今天请假。")
    assert pii.scan("同学王芳没有完成作业。")
