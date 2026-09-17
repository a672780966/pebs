from __future__ import annotations

import re

import pytest

from pebs import config, pipeline, providers, render
from pebs import pptx_foundry as _pptx_foundry
from pebs.engine import Engine

_REAL_FIND_RENDERER = render.find_renderer
_REAL_PPTX_FOUNDRY_AVAILABLE = _pptx_foundry.available
_REAL_PPTX_FOUNDRY_DELIVERY_CHECK = _pptx_foundry.delivery_check


class FakeLLM:
    def __init__(
        self,
        word_range: tuple[int, int] = (10, 9999),
        undershoot_first: int = 0,
        unsafe_first: int = 0,
        fix_bad: bool = False,
        fix_unsafe: bool = False,
        extra_text: str = "",
        invalid_strategy_first: bool = False,
        qualify_flow: bool = False,
        human_review_first: bool = False,
        animation_item: bool = True,
        animation_rejected: bool = False,
        animation_gate_bad: bool = False,
        load_high: bool = False,
        load_bad_diagram: bool = False,
        load_null_fields: bool = False,
        case_new_facts: bool = False,
        weird_enums: bool = False,
    ):
        self.word_range = word_range
        self.undershoot_first = undershoot_first
        self.unsafe_first = unsafe_first
        self.fix_bad = fix_bad
        self.fix_unsafe = fix_unsafe
        self.extra_text = extra_text
        self.invalid_strategy_first = invalid_strategy_first
        self.qualify_flow = qualify_flow
        self.human_review_first = human_review_first
        self.animation_item = animation_item
        self.animation_rejected = animation_rejected
        self.animation_gate_bad = animation_gate_bad
        self.load_high = load_high
        self.load_bad_diagram = load_bad_diagram
        self.load_null_fields = load_null_fields
        self.case_new_facts = case_new_facts
        self.weird_enums = weird_enums
        self.calls: dict[str, int] = {}
        self.prompts: list[str] = []

    def _bump(self, task: str) -> int:
        self.calls[task] = self.calls.get(task, 0) + 1
        return self.calls[task]

    def availability(self):
        return {
            "available": True,
            "reasons": [],
            "id": "fake-llm",
            "model": "fake",
            "base_url": "http://fake.local",
            "api_key_env": "",
            "send_scope": [],
        }

    def _section(self, prompt: str) -> str:
        match = re.search(r"本节：(\S+)", prompt)
        return match.group(1) if match else "sec1"

    def _script_units(self, prompt: str, narration: str, unsafe: bool = False) -> list[dict]:
        if unsafe:
            narration += "该学生患有焦虑症，需要转介。"
        return [
            {"unit_id": "u1", "kind": "title", "text": "测试节"},
            {"unit_id": "u2", "kind": "narration", "text": narration, "claim_refs": []},
            {
                "unit_id": "u3",
                "kind": "visual",
                "text": "事实与判断对比表",
                "visual_function": "comparison",
            },
            {"unit_id": "u4", "kind": "interaction", "text": "请学生口头举一个事实例子"},
        ]

    def _narration_for(self, lo: int, hi: int) -> str:
        target = min(max(lo + 2, lo), hi)
        base = "本课讲解观察记录的方法与要点，注意区分事实与判断。"
        return (base * (target // len(base) + 1))[:target]

    def generate_json(self, *, task, system, prompt, temperature=None, timeout=None):
        self.prompts.append(prompt)
        section = self._section(prompt)
        if task == "learning_design":
            return {
                "section_id": section,
                "title": "测试节",
                "goals": [
                    {
                        "goal_id": "g1",
                        "text": "理解观察记录中的事实与判断区分",
                        "knowledge_type": "concept",
                        "cognitive_demand": "理解",
                    }
                ],
                "prior_knowledge": ["观察基础"],
                "difficulties": [{"text": "容易把判断写成事实", "basis": "model_hypothesis"}],
                "transfer_goal": "迁移到日常观察记录",
                "assessment_evidence": ["能正确区分事实与判断"],
                "sequence": [{"unit_id": "u1", "title": "导入", "goal_ref": "g1"}],
            }
        if task == "claims":
            return {
                "claims": [
                    {
                        "text": "观察记录应区分事实与判断。",
                        "claim_type": "observational" if self.weird_enums else "descriptive",
                        "population": "教师",
                        "usage": "讲解",
                    }
                ]
            }
        if task == "research_query":
            return {"queries": ["observation record fact judgment preschool"]}
        if task == "evidence_review":
            n = self._bump("evidence_review")
            quote_match = re.search(r'"""\s*(.*?)\s*"""', prompt, flags=re.S)
            text = re.sub(r"\s+", "", quote_match.group(1)) if quote_match else ""
            if not text:
                return {"found": False}
            support = "direct"
            if self.qualify_flow and n == 1:
                support = "contextual"
            return {
                "found": True,
                "quote": text[:14],
                "quote_location": "摘要首句",
                "support": support,
                "design_note": "直接支持描述性结论",
                "scope": "职前教师",
                "limitations": "样本有限",
                "uncertainty": "低",
                "human_review": bool(self.human_review_first and n == 1),
            }
        if task == "claim_qualify":
            return {
                "text": "在多项研究中，记录者的既有预期与信息选择存在相关，但不能据此推定单次观察可判断动机。",
                "population": "教师",
                "note": "降低强度并限定范围",
            }
        if task in ("teaching_plan", "teaching_plan_fix"):
            n = self._bump(task)
            strategy = "explicit-instruction"
            if task == "teaching_plan" and self.invalid_strategy_first and n == 1:
                strategy = "error-analysis"
            return {
                "section_id": section,
                "strategies": [
                    {
                        "goal_ref": "g1",
                        "knowledge_type": "concept",
                        "strategy": strategy,
                        "rationale": "概念需要明确讲解",
                    }
                ],
                "pck_notes": ["先给出正反例，再对比总结"],
                "udl": {
                    "barriers": ["术语抽象"],
                    "options": [
                        {
                            "barrier": "术语抽象",
                            "option": "提供事实/判断对比表",
                            "same_goal_ref": "g1",
                            "core_demand_preserved": True,
                            "representation": "对比表",
                        }
                    ],
                    "support_review_flags": [],
                },
            }
        if task in ("case", "case_replace"):
            new_facts = ["观察记录应区分事实与判断。"] if (task == "case" and self.case_new_facts) else []
            return {
                "case_id": "case1",
                "section_id": section,
                "title": "午睡观察记录",
                "kind": "fictional",
                "text": "王老师记录：幼儿午睡时翻来覆去（虚构案例）。",
                "difficulty": "中等",
                "linked_goal": "g1",
                "claim_refs": [],
                "new_factual_claims": new_facts,
            }
        if task == "assessment":
            return {
                "section_id": section,
                "items": [
                    {
                        "assessment_id": "a1",
                        "kind": "transfer_prompt" if self.weird_enums else "hinge_question",
                        "question": "下列哪项是事实描述？",
                        "options": ["A 幼儿很调皮", "B 幼儿在 12:30 入睡", "C 幼儿不开心"],
                        "answer": "B",
                        "distractors": ["A", "C"],
                        "rationale": "B 可观察记录，A、C 是判断",
                        "target_goal": "g1",
                        "claim_refs": [],
                        "student_viewable": True,
                    }
                ],
            }
        if task == "script":
            n = self._bump("script")
            refs = re.findall(r"(clm_[0-9a-f]{10}@v\d+)", prompt)
            refs = list(dict.fromkeys(refs))
            range_match = re.search(r"字数要求：(\d+)–(\d+) 字", prompt)
            if range_match:
                lo, hi = int(range_match.group(1)), int(range_match.group(2))
            else:
                lo, hi = self.word_range
            narration = self._narration_for(lo, hi) + self.extra_text
            if n <= self.undershoot_first:
                narration = "太短。"
            unsafe = n <= self.unsafe_first
            units = self._script_units(prompt, narration, unsafe=unsafe)
            if refs:
                units[1]["claim_refs"] = refs[:1]
            return {"units": units}
        if task == "script_fix":
            self._bump("script_fix")
            range_match = re.search(r"字数要求：(\d+)–(\d+) 字", prompt)
            lo, hi = (int(range_match.group(1)), int(range_match.group(2))) if range_match else self.word_range
            narration = "太短。" if self.fix_bad else self._narration_for(lo, hi) + self.extra_text
            return {"units": self._script_units(prompt, narration, unsafe=self.fix_unsafe)}
        if task == "media_plan":
            items = [
                {
                    "item_id": "i1",
                    "goal_ref": "g1",
                    "knowledge_function": "compare" if self.weird_enums else "comparison",
                    "temporal_dependency": False,
                    "spatial_dependency": False,
                    "comparison_dependency": True,
                    "persistence_need": True,
                    "learner_interaction_need": False,
                    "recommended_medium": "picture" if self.weird_enums else "diagram",
                    "rationale": "事实与判断需要静态对比",
                }
            ]
            if self.animation_item:
                items.append(
                    {
                        "item_id": "i2",
                        "goal_ref": "g1",
                        "knowledge_function": "state_change",
                        "temporal_dependency": True,
                        "spatial_dependency": False,
                        "comparison_dependency": False,
                        "persistence_need": True,
                        "learner_interaction_need": False,
                        "recommended_medium": "animation",
                        "rationale": "记录从事实到判断的变化过程",
                    }
                )
            return {"items": items}
        if task in ("diagram_svg", "diagram_svg_fix"):
            return {
                "diagrams": [
                    {
                        "diagram_id": "d1",
                        "item_id": "i1",
                        "diagram_type": "comparison",
                        "title": "事实与判断对比",
                        "alt_text": "左右两栏对比事实描述与个人解释",
                        "semantics": {
                            "nodes": [
                                {"id": "n1", "label": "直接观察", "kind": "concept"},
                                {"id": "n2", "label": "个人解释", "kind": "concept"},
                            ],
                            "edges": [{"from": "n1", "to": "n2", "label": "区分"}],
                        },
                        "svg": (
                            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 960 540'>"
                            "<rect x='40' y='40' width='400' height='200' fill='#eef'/>"
                            "<text x='60' y='90'>直接观察</text><text x='520' y='90'>个人解释</text></svg>"
                        ),
                    }
                ]
            }
        if task == "animation_gate":
            base = {
                "item_id": "i2",
                "criteria": {
                    "knowledge_function": "状态转移",
                    "temporal_necessity": True,
                    "static_alternative": False,
                    "cognitive_load": "低",
                    "narration_synchrony": "每步画面变化配一句讲解",
                    "persistence_need": True,
                    "generation_feasibility": "高",
                    "teaching_value": "展示逐步变化的取舍",
                },
                "rationale": "知识随时间变化，静态图无法表达过程",
                "static_alternative_desc": "",
            }
            if self.animation_gate_bad:
                base["criteria"]["temporal_necessity"] = False
                base["decision"] = "ANIMATION"
                base["rationale"] = "模型误判为需要动画"
            elif self.animation_rejected:
                base["decision"] = "STATIC"
                base["criteria"]["static_alternative"] = True
                base["criteria"]["narration_synchrony"] = "静态图 + 标注"
                base["rationale"] = "一张静态图能更清楚表达对比"
                base["static_alternative_desc"] = "用对比表替代动画"
            else:
                base["decision"] = "ANIMATION"
            return {"decisions": [base]}
        if task == "storyboard":
            return {
                "shots": [
                    {
                        "shot_id": "s1",
                        "item_id": "i2",
                        "learning_goal": "理解记录中的事实与判断转变",
                        "narration": "先记录看到的行为。",
                        "visual_state_start": "只有行为描述",
                        "visual_change": "加入个人解释图层",
                        "visual_state_end": "两栏对比并列",
                        "labels": ["事实", "判断"],
                        "on_screen_text": "先事实，后判断",
                        "duration": "8" if self.weird_enums else 8,
                        "knowledge_function": "state_change",
                        "cognitive_load_note": "分两步呈现",
                        "continuity_from": "start",
                        "continuity_to": "s2",
                    },
                    {
                        "shot_id": "s2",
                        "item_id": "i2",
                        "learning_goal": "能把判断改写为事实描述",
                        "narration": "再标注可能的解释。",
                        "visual_state_start": "两栏对比",
                        "visual_change": "高亮判断词",
                        "visual_state_end": "终态：对比表",
                        "labels": ["终态"],
                        "on_screen_text": "判断需要证据",
                        "duration": 6,
                        "knowledge_function": "state_change",
                        "cognitive_load_note": "保持低密度",
                        "continuity_from": "s1",
                        "continuity_to": "end",
                    },
                ],
                "video_prompt": (
                    "Two-column comparison animation: factual observation vs personal interpretation, "
                    "step-by-step reveal with synchronized captions, calm palette, no text overflow."
                ),
                "static_terminal_state": "左右两栏对比表，供学生反复查看",
            }
        if task == "load_review":
            pairing = {
                "goal_ref": "g1",
                "verbal": "事实与判断的区别",
                "visual": "两栏对比图",
                "knowledge_function": "comparison",
                "diagram_id": "d404" if self.load_bad_diagram else "d1",
                "pairing_ok": True,
                "note": "",
            }
            if self.load_null_fields:
                pairing = {
                    "goal_ref": "g1",
                    "verbal": None,
                    "visual": "两栏对比图",
                    "knowledge_function": None,
                    "diagram_id": None,
                    "pairing_ok": None,
                    "note": None,
                }
            return {
                "section_id": section,
                "cognitive_load": {
                    "level": "HIGH" if self.load_high else "MEDIUM",
                    "reasons": ["元素交互性中等"] if not self.load_high else ["元素交互性偏高，对比项过多"],
                    "uncertainties": None if self.load_null_fields else ["信息量估计基于文本长度"],
                    "improvements": ["保持分段并使用信号标注"],
                },
                "dual_coding": {"pairings": [pairing]},
            }
        if task == "lesson_plan":
            return {
                "section_id": section,
                "title": "测试节",
                "objectives": [{"goal_ref": "g1", "text": "能区分事实与判断并改写"}],
                "key_points": ["观察与解释的边界"],
                "difficult_points": ["把判断改写成可观察事实"],
                "preparation": ["对比表", "学习单"],
                "process": [
                    {
                        "stage": "导入",
                        "minutes": 5,
                        "teacher_activity": "出示虚构案例",
                        "student_activity": "口述观察到的行为",
                        "intent": "引出事实与判断的区别",
                    },
                    {
                        "stage": "练习",
                        "minutes": 10,
                        "teacher_activity": "巡视指导",
                        "student_activity": "完成改写练习",
                        "intent": "巩固改写技能",
                    },
                ],
                "board_design": "两栏对比表：直接观察 / 个人解释",
                "homework": ["完成学习单任务三"],
            }
        if task == "worksheet":
            return {
                "section_id": section,
                "title": "观察记录学习单",
                "instructions": "按任务顺序完成，答案写在横线处。",
                "tasks": [
                    {
                        "task_id": "t1",
                        "kind": "record_table",
                        "prompt": "记录一次课堂观察（虚构即可）",
                        "fields": ["时间", "情境", "行为", "待核验"],
                        "answer": "（示例）14:05 小组任务 低头沉默 是否听清问题",
                        "answer_notes": "事实可观察，推断须标注",
                    },
                    {
                        "task_id": "t2",
                        "kind": "rewrite",
                        "prompt": "把“他不愿合作”改写为事实描述",
                        "answer": "他在两次询问后未回应",
                        "answer_notes": "去掉动机推断",
                    },
                ],
                "reflection_questions": ["你最容易把哪类判断写成事实？"],
                "student_version_note": "学生版不含答案",
            }
        if task == "slide_plan":
            return {
                "rows": [
                    {
                        "slide": 1,
                        "title": "观察记录：事实与判断",
                        "narrative_section": "开场",
                        "communication_task": "明确本课目标",
                        "source_asset": "",
                        "asset_geometry": "",
                        "core_message": "先事实，后判断",
                        "layout_archetype": "cover",
                        "density": "low",
                        "asset_handling": "",
                        "risk": "",
                        "section_id": "sec1",
                        "points": [],
                        "claim_refs": [],
                        "notes": "开场说明本课目标。",
                    },
                    {
                        "slide": 2,
                        "title": "直接观察 vs 个人解释",
                        "narrative_section": "sec1",
                        "communication_task": "区分两类信息",
                        "source_asset": "diagram:d1",
                        "asset_geometry": "wide",
                        "core_message": "两类信息边界清晰",
                        "layout_archetype": "dashboard" if self.weird_enums else "diagram",
                        "density": "dense" if self.weird_enums else "medium",
                        "asset_handling": "keep",
                        "risk": "无",
                        "section_id": "sec1",
                        "points": ["直接观察：动作、原话、次数", "个人解释：赋予的意义"],
                        "diagram_id": "d1",
                        "claim_refs": [],
                        "notes": "先呈现对比图，再逐栏讲解。",
                    },
                    {
                        "slide": 3,
                        "title": "记录四要素",
                        "narrative_section": "sec1",
                        "communication_task": "记住书写顺序",
                        "source_asset": "",
                        "asset_geometry": "",
                        "core_message": "时间→情境→行为→待核验",
                        "layout_archetype": "table",
                        "density": "medium",
                        "asset_handling": "",
                        "risk": "",
                        "section_id": "sec1",
                        "points": [],
                        "table": {
                            "headers": ["要素", "示例"],
                            "rows": [["时间", "14:05"], ["情境", "小组任务"]],
                        },
                        "claim_refs": ["clm_deadbeef00@v1"],
                        "notes": "按顺序讲解四要素。",
                    },
                    {
                        "slide": 4,
                        "title": "小结",
                        "narrative_section": "收束",
                        "communication_task": "回顾要点",
                        "source_asset": "",
                        "asset_geometry": "",
                        "core_message": "记录只呈现本次观察",
                        "layout_archetype": "closing",
                        "density": "low",
                        "asset_handling": "",
                        "risk": "",
                        "section_id": "sec1",
                        "points": ["删标签、删因果、护隐私"],
                        "claim_refs": [],
                        "notes": "收束提醒隐私要求。",
                    },
                ]
            }
        raise AssertionError(f"unexpected task: {task}")


class FakeResearch:
    def __init__(
        self,
        available: bool = True,
        abstract: bool = True,
        fulltext_url: str | None = None,
        fulltext_text: str = "全文支持：观察记录应区分事实与判断，这是本研究的方法学建议。",
    ):
        self.available = available
        self.abstract = abstract
        self.fulltext_url = fulltext_url
        self.fulltext_text = fulltext_text
        self.queries: list[str] = []
        self.fulltext_calls: list[str] = []

    def sources(self) -> list[str]:
        return ["crossref"]

    def availability(self):
        return {
            "available": self.available,
            "reasons": [] if self.available else ["test: research disabled"],
            "id": "fake-research",
            "allowed_sources": ["crossref"],
        }

    def search(self, query, rows=5):
        self.queries.append(query)
        abstract = "观察记录应区分事实与判断。摘要提供了描述性支持。" if self.abstract else ""
        items = [
            {
                "title": "观察记录中的事实与判断",
                "doi": "10.1234/test",
                "abstract": abstract,
                "publish_date": "2020",
                "container": "Test Journal",
                "type": "journal-article",
                "content_level": "abstract" if abstract else "metadata",
                "fulltext_url": self.fulltext_url,
                "database": "crossref",
            }
        ]
        return providers.ResearchResult(items=items, per_source={"crossref": len(items)}, errors={})

    def fetch_fulltext(self, url, *, max_bytes=None):
        self.fulltext_calls.append(url)
        return self.fulltext_text


class MissingLLM(FakeLLM):
    def availability(self):
        return {"available": False, "reasons": ["test: LLM 未配置"], "id": "missing-llm"}

    def generate_json(self, **kwargs):
        raise AssertionError("provider must not be called when unavailable")


def run_build(engine: Engine, request: str, *, template_path=None, material_paths=(), environment="production"):
    plan = engine.current_plan()
    material_paths = list(material_paths)
    explicit_skills = pipeline.parse_explicit_skills(request)
    run_id = engine.store.create_run(
        environment=environment,
        request=request,
        budgets=config.RULES.get("budgets", {}),
        inputs={
            "template_path": str(template_path) if template_path else None,
            "material_paths": [str(p) for p in material_paths],
            "explicit_skills": explicit_skills,
        },
    )
    changeset_id = engine.store.create_changeset(
        run_id, f"build: {request[:60]}", engine.store.current_baseline()
    )
    for step in plan["steps"]:
        engine.store.add_step(run_id, step["step_id"], step["title"])
    ctx = engine._new_context(
        run_id=run_id,
        changeset_id=changeset_id,
        request=request,
        template_path=template_path,
        material_paths=list(material_paths),
        environment=environment,
        explicit_skills=explicit_skills,
    )
    engine._run_steps(ctx, run_id)
    return run_id, changeset_id


@pytest.fixture
def registry_env(tmp_path, monkeypatch):
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    (registry_dir / "skills.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config, "REGISTRY_DIR", registry_dir)
    monkeypatch.setattr(config, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(config, "QUARANTINE_DIR", tmp_path / "skills" / "quarantine")
    monkeypatch.setattr(config, "UPSTREAM_DIR", tmp_path / "skills" / "upstream")
    monkeypatch.setattr(config, "PATCHED_DIR", tmp_path / "skills" / "patched")
    monkeypatch.setattr(config, "PATCHES_DIR", tmp_path / "patches")
    return tmp_path


@pytest.fixture
def no_pptx(monkeypatch):
    rules = dict(config.RULES)
    rules["m4"] = {**rules.get("m4", {}), "pptx": False}
    monkeypatch.setattr(config, "RULES", rules)
    return True


@pytest.fixture
def engine(tmp_path, monkeypatch):
    from pebs import pptx_foundry, render

    monkeypatch.setattr(render, "find_renderer", lambda: "")
    monkeypatch.setattr(pptx_foundry, "available", lambda: False)
    monkeypatch.setattr(pptx_foundry, "delivery_check", lambda *args, **kwargs: None)
    eng = Engine("testproj", base_dir=tmp_path / "proj")
    eng.llm = FakeLLM()
    eng.research = FakeResearch()
    yield eng
    eng.close()


@pytest.fixture
def render_engine(engine, monkeypatch):
    from pebs import pptx_foundry, render

    if not _REAL_FIND_RENDERER():
        pytest.skip("no LibreOffice/PowerPoint renderer on this host")
    monkeypatch.setattr(render, "find_renderer", _REAL_FIND_RENDERER)
    monkeypatch.setattr(pptx_foundry, "available", _REAL_PPTX_FOUNDRY_AVAILABLE)
    monkeypatch.setattr(pptx_foundry, "delivery_check", _REAL_PPTX_FOUNDRY_DELIVERY_CHECK)
    return engine


REQUEST_2 = "任务1 观察记录，任务2 事实与判断。每节 10–9999 字，每节至少 1 个案例。"
REQUEST_1 = "任务1 观察记录。每节 10–9999 字，每节至少 1 个案例。"
