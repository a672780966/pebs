from __future__ import annotations

from conftest import REQUEST_1, run_build

from pebs import gates

RULES = """# PROJECT_RULES.md（项目规则）
- 称谓统一使用“婴幼儿”。
- 每节脚本至少 2 个案例。
- 脚本讲解正文字数 100–200。
- 输出语言：中文。
"""


def _write_rules(engine, text):
    (engine.base / "PROJECT_RULES.md").write_text(text, encoding="utf-8")


def _latest(engine, artifact_id):
    return engine.store.get_revision(engine.store.revisions_of(artifact_id)[-1])["content"]


def test_project_rules_applied_and_request_overrides_word_range(engine):
    _write_rules(engine, RULES)
    run_id, changeset_id = run_build(engine, REQUEST_1)
    requirements = _latest(engine, "requirements")
    assert "婴幼儿" in requirements["terminology"]
    assert (requirements["word_rules"]["min"], requirements["word_rules"]["max"]) == (10, 9999)
    items = {i["req_id"]: i for i in requirements["items"]}
    assert items["req_wordcount_rule_revision"]["status"] == "confirmed"
    assert requirements["sections"][0]["required_case_count"] == 2

    engine.accept(changeset_id)
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g1_requirements(ctx, "script:sec1")
    assert result["status"] == "FAIL"
    assert any("至少 2 个案例" in issue["reason"] for issue in result["issues"])
    assert any("婴幼儿" in issue["reason"] for issue in result["issues"])


def test_project_rules_supply_word_range_when_request_has_none(engine):
    _write_rules(engine, RULES)
    run_id, changeset_id = run_build(engine, "任务1 观察记录。")
    requirements = _latest(engine, "requirements")
    assert (requirements["word_rules"]["min"], requirements["word_rules"]["max"]) == (100, 200)
    items = {i["req_id"]: i for i in requirements["items"]}
    assert items["req_wordcount_rules"]["source"] == "user_explicit"


def test_template_request_word_conflict_is_flagged_and_fails_g1(engine, tmp_path):
    template = tmp_path / "t.md"
    template.write_text(
        "# 模板\n\n正文 300–400 字。\n\n| 教师讲解 | 画面提示 | 案例 |\n|---|---|---|\n|  |  |  |\n",
        encoding="utf-8",
    )
    run_id, changeset_id = run_build(engine, REQUEST_1, template_path=template)
    requirements = _latest(engine, "requirements")
    conflicted = [i for i in requirements["items"] if i["status"] == "conflicted"]
    assert conflicted and "模板字数" in conflicted[0]["text"]
    engine.accept(changeset_id)
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    result = gates.g1_requirements(ctx, "script:sec1")
    assert result["status"] == "FAIL"
    assert any("未解决的要求冲突" in issue["reason"] for issue in result["issues"])


def test_template_word_range_used_when_no_request_range(engine, tmp_path):
    template = tmp_path / "t.md"
    template.write_text(
        "# 模板\n\n正文 100–200 字。\n\n| 教师讲解 | 画面提示 | 案例 |\n|---|---|---|\n|  |  |  |\n",
        encoding="utf-8",
    )
    run_id, changeset_id = run_build(engine, "任务1 观察记录。", template_path=template)
    requirements = _latest(engine, "requirements")
    assert (requirements["word_rules"]["min"], requirements["word_rules"]["max"]) == (100, 200)
    items = {i["req_id"]: i for i in requirements["items"]}
    assert items["req_wordcount_template"]["source"] == "template_extracted"
