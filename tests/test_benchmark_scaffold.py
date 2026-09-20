from __future__ import annotations

pytestmark = __import__('pytest').mark.benchmark_smoke

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


def test_banned_regex_ignores_quoted_error_examples():
    """§50：被引号或"写成/误写为"标记的错误写法示例，不算违规。"""
    store = _StubStore(
        {
            "script:sec1": {
                "artifact_id": "script:sec1",
                "content": "常见误区：把相关写成“手机使用导致焦虑”；正确表述是“手机使用与焦虑相关，但不能确定因果方向”。",
            }
        }
    )
    expect = {"content": {"artifact_types": ["script"], "banned_regex": ["导致焦虑"]}}
    assert checks.evaluate(store, expect)["ok"] is True

    bad_store = _StubStore(
        {
            "script:sec1": {
                "artifact_id": "script:sec1",
                "content": "研究证明手机使用导致焦虑，所以我们要减少使用。",
            }
        }
    )
    bad = checks.evaluate(bad_store, expect)
    assert bad["ok"] is False
    assert bad["issues"][0]["kind"] == "SAFETY"


def test_scrub_exercise_fields_handles_json_and_python_repr():
    """§12/§50：选项与干扰项字段（故意错误）不得参与安全扫描。"""
    json_text = '{"question": "?", "options": ["A. 手机使用导致焦虑。", "B. 相关不等于因果。"], "answer": "B"}'
    assert "导致焦虑" not in checks.scrub_exercise_fields(json_text)
    repr_text = str({"question": "?", "options": ["A. 手机使用导致焦虑。", "B. 相关不等于因果。"], "answer": "B"})
    assert "导致焦虑" not in checks.scrub_exercise_fields(repr_text)
    distractors = '{"distractors_detail": [{"answer": "手机使用导致焦虑", "misconception": "把相关当因果"}], "question": "?"}'
    assert "导致焦虑" not in checks.scrub_exercise_fields(distractors)


def test_banned_regex_ignores_audit_lead_ins():
    """§49：审阅产物用"第N条审查——…"引出被审说法，属引用而非主张。"""
    store = _StubStore(
        {
            "script:sec1": {
                "artifact_id": "script:sec1",
                "content": "第四条审查——“研究显示大学生群体焦虑水平上升，所以这个学生一定是焦虑的。”请指出越权推断并给出改写。",
            }
        }
    )
    expect = {"content": {"artifact_types": ["script"], "banned_regex": ["这个学生(就是|一定)"]}}
    assert checks.evaluate(store, expect)["ok"] is True


def test_banned_regex_ignores_audit_practice_instructions():
    """§49：审阅任务把被审说法作为待处理对象引出（"说明4（…）请圈出…"），不算主张。"""
    store = _StubStore(
        {
            "script:sec1": {
                "artifact_id": "script:sec1",
                "content": "说明4（研究显示大学生群体焦虑水平上升，所以这个学生一定是焦虑的。）请用双圈圈出它把群体结论推给个体的地方。",
            }
        }
    )
    expect = {"content": {"artifact_types": ["script"], "banned_regex": ["这个学生(就是|一定)"]}}
    assert checks.evaluate(store, expect)["ok"] is True

    bad_store = _StubStore(
        {
            "script:sec1": {
                "artifact_id": "script:sec1",
                "content": "这个学生一定是焦虑的，需要单独谈话。",
            }
        }
    )
    assert checks.evaluate(bad_store, expect)["ok"] is False


def test_banned_regex_ignores_exercise_options():
    """§50：判断题选项中的错误写法是待判定对象，不算产物在主张它。"""
    store = _StubStore(
        {
            "script:sec1": {
                "artifact_id": "script:sec1",
                "content": "判断：下面哪一句改写没有加入因果暗示？ A. 手机使用导致焦虑。 B. 手机使用是焦虑的原因。 C. 在大学生群体中两者相关，但不能确定因果。",
            }
        }
    )
    expect = {"content": {"artifact_types": ["script"], "banned_regex": ["导致焦虑"]}}
    assert checks.evaluate(store, expect)["ok"] is True


def test_banned_regex_ignores_negative_examples():
    """教学反例（"不要写'这个孩子就是…'"）不应被判为标签化违规。"""
    store = _StubStore(
        {
            "script:sec1": {
                "artifact_id": "script:sec1",
                "content": "讲解时提醒教师：不要使用“这个孩子就是调皮”这类标签化表达；可以换写“14:05 他把积木推到地上”。",
            }
        }
    )
    expect = {"content": {"artifact_types": ["script"], "banned_regex": ["这个孩子就是"]}}
    result = checks.evaluate(store, expect)
    assert result["ok"] is True

    bad_store = _StubStore(
        {
            "script:sec1": {
                "artifact_id": "script:sec1",
                "content": "这个孩子就是不爱说话，所以我们要重点关注他。",
            }
        }
    )
    bad = checks.evaluate(bad_store, expect)
    assert bad["ok"] is False
    assert bad["issues"][0]["kind"] == "SAFETY"


class _StubStore:
    def __init__(self, artifacts: dict[str, dict] | None = None):
        self._artifacts = artifacts or {}

    def list_artifacts(self):
        return [
            {
                "artifact_id": artifact_id,
                "artifact_type": artifact_id.split(":", 1)[0],
                "accepted_rev": f"{artifact_id}@r1",
            }
            for artifact_id in self._artifacts
        ]

    def accepted_content(self, artifact_id):
        return (self._artifacts.get(artifact_id) or {}).get("content")


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


def test_report_builds_metric_by_mode_comparison_table():
    """§42：报告必须有 Metric × Direct/Builtin/Dynamic 的汇总表。"""
    runs = [
        {
            "case_id": "A",
            "mode": "direct_codex",
            "run_id": "r1",
            "metrics": {"model_calls": 1, "wall_time_seconds": 100},
        },
        {
            "case_id": "A",
            "mode": "dynamic",
            "run_id": "r2",
            "metrics": {"model_calls": 8, "wall_time_seconds": 140},
            "human_eval": {"scores": {"subject_accuracy": 4}, "edit_ratio": 0.2, "evidence_errors": 1},
        },
        {
            "case_id": "B",
            "mode": "dynamic",
            "run_id": "r3",
            "metrics": {"model_calls": 10, "wall_time_seconds": 160},
            "human_eval": {"scores": {"subject_accuracy": 5}, "edit_ratio": 0.1, "evidence_errors": 0},
        },
        {
            "case_id": "B",
            "mode": "dynamic",
            "experiment": "external-media",
            "run_id": "r4",
            "metrics": {"model_calls": 12, "wall_time_seconds": 200},
        },
    ]
    summary = report.summarize(runs)
    comparison = report.mode_comparison(summary)
    assert set(comparison) == {"direct_codex", "dynamic"}
    assert comparison["direct_codex"]["model_calls"] == 1.0
    assert comparison["dynamic"]["model_calls"] == 30.0
    assert comparison["dynamic"]["evidence_errors"] == 1.0
    assert comparison["dynamic"]["human_score"] == 4.5
    markdown = report.render_markdown(summary)
    assert "模式对比" in markdown
    assert "| Metric | direct_codex | dynamic |" in markdown
    assert "Teacher Edit Ratio" in markdown


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


def test_reproducibility_records_commit_and_skill_provenance():
    """§41：run 记录必须含 PEBS commit、provider SHA、skill patch —— 版本号不足以复现。"""
    reproducible = trace.reproducibility(
        fixture_hashes={"m.md": "abc"},
        skills=[
            {"skill": "dual-coding-designer", "upstream_sha": "6bbbce41", "patch": "dual-coding-pebs-1"},
            {"skill": "script-writer"},
        ],
    )
    for field in ("pebs_commit", "registry_hash", "rules_version", "timestamp", "fixture_hashes"):
        assert field in reproducible, f"§41 要求记录 {field}"
    assert reproducible["skill_provider_shas"] == ["6bbbce41"]
    assert reproducible["skill_patches"] == ["dual-coding-designer@dual-coding-pebs-1"]


def test_schema_repair_rate_is_recorded_from_step_notes():
    """§35：外部 Skill 重生成一次才通过 Schema 的情况必须可统计。"""
    trace_record = {
        "skills": [
            {"skill": "dual-coding-designer", "status": "SUCCEEDED", "schema_repairs": 2},
            {"skill": "script-writer", "status": "SUCCEEDED"},
        ],
        "gates": [],
        "plan": {},
    }
    summary = metrics.summarize_run(trace_record)
    assert summary["schema_repairs"] == 2
    assert summary["schema_repair_rate"] == 0.5
    assert trace._schema_repairs("外部 Skill 执行：x；产出 1 个产物；Schema 修复 2 次") == 2
    assert trace._schema_repairs("外部 Skill 执行：x；产出 1 个产物") == 0


def test_failure_taxonomy_categories_match_emitted_issue_kinds():
    """§65：自动检查产出的每个 kind 都必须能落进 failure_taxonomy 的类别。"""
    known = checks.taxonomy_categories()
    assert known, "failure_taxonomy.yaml 必须可读"
    assert "ROUTING" in known and "LOCALITY" in known and "PRIVACY" in known

    # 各检查路径实际会产出的 kind（漏一个就意味着报告里出现孤儿类别）
    emitted = {
        "PLANNING",
        "ROUTING",
        "CONTENT",
        "SAFETY",
        "MEDIA",
        "PEDAGOGY",
        "EVIDENCE",
    }
    assert emitted <= known, f"未登记的失败类别：{sorted(emitted - known)}"
    assert checks.categorize([{"kind": "ROUTING"}, {"kind": "ROUTING"}, {"kind": "SAFETY"}]) == {
        "ROUTING": 2,
        "SAFETY": 1,
    }


def test_report_lists_failure_categories_and_surfaces_unknown_ones():
    """§65：报告要有类别分布；不在 taxonomy 里的 kind 必须显式列出而不是消失。"""
    runs = [
        {
            "case_id": "A",
            "mode": "dynamic",
            "run_id": "r1",
            "metrics": {},
            "automatic_issues": {
                "issues": [{}, {}],
                "counts": {"ROUTING": 1, "BOGUS": 1},
                "unknown_categories": ["BOGUS"],
            },
        }
    ]
    section = "\n".join(report.failure_category_section(runs))
    assert "失败类别分布" in section
    assert "| ROUTING | 1 |" in section
    assert "BOGUS" in section and "分类无效" in section


def test_gate_audit_computes_false_negative_and_positive_rates(tmp_path, monkeypatch):
    """§35：Gate FP/FN 来自"用当前门禁重放已存项目"的比对。"""
    from pebs.benchmark import gates_audit

    records = [
        {
            "project": "p1",
            "rows": [
                {"artifact": "script:sec1", "gate": "G1", "stored": "PASS", "now": "FAIL", "changed": True},
                {"artifact": "script:sec1", "gate": "G3", "stored": "FAIL", "now": "PASS", "changed": True},
                {"artifact": "script:sec1", "gate": "G4", "stored": "PASS", "now": "PASS", "changed": False},
                {"artifact": "script:sec1", "gate": "G5", "stored": "FAIL", "now": "FAIL", "changed": False},
            ],
        }
    ]
    summary = gates_audit.gate_rates(records)
    assert summary["checked"] == 4
    assert summary["runs_with_changes"] == 1
    # 2 条当时 PASS，其中 1 条被重放翻成 FAIL
    assert summary["gate_false_negative_rate"] == 0.5
    # 2 条当时 FAIL，其中 1 条被重放翻成 PASS
    assert summary["gate_false_positive_rate"] == 0.5
    assert summary["per_gate"]["G1"]["false_negative"] == 1

    path = gates_audit.write_audit(summary, path=tmp_path / "gate_audit.json")
    section = "\n".join(gates_audit.section(path=path))
    assert "Gate False Negative Rate" in section and "0.5" in section
    assert "重放口径" in section


def test_case_quality_checks_are_wired_into_evaluate():
    """§55：case 红旗检查必须真的被 evaluate() 调用（此前只有定义、没有调用点）。"""
    from pebs.benchmark import checks

    class _Store:
        def __init__(self, content):
            self._content = content

        def list_artifacts(self):
            return [{"artifact_id": "case:sec1:1", "artifact_type": "case", "accepted_rev": "case:sec1:1@r1"}]

        def accepted_content(self, artifact_id):
            return self._content

    bad = _Store(
        {
            "case_id": "c1",
            "linked_goal": "",
            "text": "某某幼儿园的乐乐被教师称为问题儿童，某某大学研究发现他一定有问题。",
        }
    )
    issues = checks.case_checks(bad)
    reasons = " ".join(issue["detail"] for issue in issues)
    assert any(issue["kind"] == "PEDAGOGY" for issue in issues), "缺少 linked_goal 必须报出"
    assert "标签化" in reasons and "虚构机构" in reasons

    result = checks.evaluate(bad, {})
    assert any(issue["detail"] in reasons for issue in result["issues"]), (
        "evaluate() 必须把 case 检查算进去"
    )

    good = _Store({"case_id": "c1", "linked_goal": "g1", "text": "小班晨间接待时两名幼儿争抢玩具，教师先观察再介入。" * 4})
    assert checks.case_checks(good) == []


def test_direct_baseline_prompt_receives_the_same_materials_as_pebs():
    """§29：不做不公平对比——baseline 必须拿到同样的用户材料（模板 + 素材）。"""
    from pebs.benchmark import runner

    case = cases.get_case("C")
    prompt = runner.direct_baseline_prompt(case)
    assert case["request"] in prompt
    assert "用户提供的材料" in prompt, "缺少素材内容"
    assert "模板" in prompt, "缺少模板结构"
    # §60：素材注入必须有上限，不能变成上下文长度竞赛
    assert len(prompt) < 20000, len(prompt)
    # 固定：同样的 case 必须得到完全一样的 prompt
    assert prompt == runner.direct_baseline_prompt(case)


def test_report_renders_gate_audit_section(tmp_path, monkeypatch):
    import json

    from pebs.benchmark import cases

    monkeypatch.setattr(cases, "reports_dir", lambda: tmp_path)
    (tmp_path / "gate_audit.json").write_text(
        json.dumps(
            {
                "checked": 10,
                "runs": 3,
                "runs_with_changes": 2,
                "gate_false_negative_rate": 0.1,
                "gate_false_positive_rate": 0.2,
                "false_negative": 1,
                "false_positive": 2,
                "caveat": "重放口径",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    section = "\n".join(report._gate_audit_section())
    assert "门禁重放审计" in section
    assert "0.1" in section and "0.2" in section


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


def test_review_promotions_reports_verdicts_without_touching_routing(tmp_path, monkeypatch):
    """Promotion verdicts are observe-only; M6 must not touch routing."""
    from pebs import config
    from pebs.benchmark import performance

    monkeypatch.setattr(config, "REGISTRY_DIR", tmp_path)
    for _ in range(12):
        performance.record_run(
            skill="hinge-question-designer", version="6bbbce41", success=True, human_score=4.2
        )
    review = performance.review_promotions()
    promoted = {item["skill"] for item in review["promote_candidates"]}
    assert "hinge-question-designer" in promoted, review
    assert review["thresholds"]["min_runs"] == 10
    assert "M7" in review["note"]
    assert all(item["target_status"] == "STABLE" for item in review["promote_candidates"])

    # insufficient data must not be promoted
    performance.record_run(skill="brand-new-skill", version="v0", success=True)
    review2 = performance.review_promotions()
    assert "brand-new-skill" not in {item["skill"] for item in review2["promote_candidates"]}
    assert any(item["skill"] == "brand-new-skill" for item in review2["experimental"])
