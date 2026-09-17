from __future__ import annotations

from pathlib import Path

from conftest import REQUEST_1, run_build

REQUEST = REQUEST_1 + " 并输出教案和学习单。"


def _latest(engine, artifact_id):
    return engine.store.get_revision(engine.store.revisions_of(artifact_id)[-1])["content"]


def test_lesson_plan_and_worksheet_artifacts(engine):
    run_id, changeset_id = run_build(engine, REQUEST)
    requirements = _latest(engine, "requirements")
    assert "lesson_plan" in requirements["outputs"]
    assert "worksheet" in requirements["outputs"]
    lesson = _latest(engine, "lesson_plan:sec1")
    assert lesson["process"] and all(stage["minutes"] > 0 for stage in lesson["process"])
    worksheet = _latest(engine, "worksheet:sec1")
    assert worksheet["tasks"] and all(task.get("answer") for task in worksheet["tasks"])

    engine.accept(changeset_id)
    g1 = engine.store.accepted_content("gate:G1:script:sec1")
    assert g1["status"] == "PASS", g1["issues"]


def test_export_splits_student_and_teacher_worksheet(engine):
    run_id, changeset_id = run_build(engine, REQUEST)
    engine.accept(changeset_id)
    result = engine.export_now("draft")
    assert result["ok"] is True
    files = result["manifest"]["files"]
    roles = {entry.get("role") for entry in files}
    assert {"lesson_plan", "worksheet", "worksheet_teacher"} <= roles

    student = next(entry for entry in files if entry.get("role") == "worksheet" and entry["kind"] == "markdown")
    student_text = Path(student["path"]).read_text(encoding="utf-8")
    assert "答案：" not in student_text
    assert "学生版不含答案" in student_text

    teacher = next(entry for entry in files if entry.get("role") == "worksheet_teacher")
    teacher_text = Path(teacher["path"]).read_text(encoding="utf-8")
    assert "答案：" in teacher_text

    lesson = next(entry for entry in files if entry.get("role") == "lesson_plan" and entry["kind"] == "markdown")
    lesson_text = Path(lesson["path"]).read_text(encoding="utf-8")
    assert "教学过程" in lesson_text
    assert "草稿—未通过 QA" in lesson_text


def test_lesson_docx_opens(engine):
    run_id, changeset_id = run_build(engine, REQUEST)
    engine.accept(changeset_id)
    result = engine.export_now("draft")
    lesson_docx = next(
        entry
        for entry in result["manifest"]["files"]
        if entry.get("role") == "lesson_plan" and entry["kind"] == "docx"
    )
    import docx

    document = docx.Document(lesson_docx["path"])
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "教学目标" in text or "教学过程" in text
