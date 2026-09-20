from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import config, gates, media, pii, preconditions, project_rules, router, schemas
from .evidence import EvidenceStore
from .hooks import Hooks, HookFailure
from .permissions import PermissionManager, PermissionDenied
from .providers import ProviderError, ProviderUnavailable, merge_research_items as _merge_research_items
from .store import BudgetExceeded, ConflictError, Store, content_hash, file_hash, now_iso
from .runtime.step_context import current_step as _current_step
from .template_parse import ParseError, check_import_limits, extract_text, parse_template

SYSTEM = (
    "你是心理学教育课程生产系统中的严格助手。只输出 JSON，不输出解释或 Markdown 代码块之外的内容。"
    "绝不编造研究结论、引用、来源或统计数据。不确定的内容必须标记为待核验。"
)

RESULT_MAP = {
    "direct": "SUPPORTED",
    "indirect": "QUALIFY_REQUIRED",
    "contextual": "QUALIFY_REQUIRED",
    "contradictory": "DISPUTED",
    "insufficient": "UNSUPPORTED",
}


class StepBlocked(Exception):
    pass


class StepFailed(Exception):
    pass


class CancelledRun(Exception):
    pass


class _ThreadSafeOutputs(dict):
    """输出映射：迭代返回快照，允许并行 DAG 节点同时 emit。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._lock = threading.RLock()

    def __setitem__(self, key: str, value: str) -> None:
        with self._lock:
            super().__setitem__(key, value)

    def __delitem__(self, key: str) -> None:
        with self._lock:
            super().__delitem__(key)

    def __iter__(self):
        with self._lock:
            return iter(list(super().keys()))

    def keys(self) -> list[str]:
        with self._lock:
            return list(super().keys())

    def values(self) -> list[str]:
        with self._lock:
            return list(super().values())

    def items(self) -> list[tuple[str, str]]:
        with self._lock:
            return list(super().items())

    def copy(self) -> dict[str, str]:
        with self._lock:
            return dict(super().items())


@dataclass
class PipelineContext:
    store: Store
    evidence: EvidenceStore
    hooks: Hooks
    permissions: PermissionManager
    llm: Any
    research: Any
    project_id: str
    run_id: str
    changeset_id: str
    request: str
    environment: str = "production"
    template_path: Path | None = None
    material_paths: list[Path] = field(default_factory=list)
    outputs: dict[str, str] = field(default_factory=_ThreadSafeOutputs)
    section_filter: list[str] | None = None
    explicit_skills: list[str] = field(default_factory=list)

    def rev(self, artifact_id: str) -> str | None:
        return self.outputs.get(artifact_id) or self.store.accepted_rev_id(artifact_id)

    def content(self, artifact_id: str) -> Any | None:
        rev = self.outputs.get(artifact_id)
        if rev:
            return self.store.get_revision(rev)["content"]
        return self.store.accepted_content(artifact_id)

    def artifact_ids_of_type(self, artifact_type: str) -> list[str]:
        ids: set[str] = set()
        for artifact_id, revision_id in self.outputs.items():
            try:
                revision = self.store.get_revision(revision_id)
            except StoreError:
                continue
            if revision["artifact_type"] == artifact_type:
                ids.add(artifact_id)
        for item in self.store.list_artifacts():
            if item["artifact_type"] == artifact_type and item.get("accepted_rev"):
                ids.add(item["artifact_id"])
        return sorted(ids)

    def content_by_type(self, artifact_type: str) -> Any | None:
        for artifact_id in self.artifact_ids_of_type(artifact_type):
            content = self.content(artifact_id)
            if content is not None:
                return content
        return None

    def emit(
        self,
        artifact_id: str,
        artifact_type: str,
        content: Any,
        produced_by: str,
        deps: list[str] | None = None,
    ) -> dict[str, Any]:
        info = self.store.add_revision(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            content=content,
            produced_by=produced_by,
            run_id=self.run_id,
            rules_version=config.RULES_VERSION,
            deps=deps or [],
            fixture=self.environment == "test_fixture",
        )
        self.store.add_changeset_item(self.changeset_id, info["revision_id"], artifact_id)
        self.hooks.after_artifact_write(info["revision_id"])
        self.outputs[artifact_id] = info["revision_id"]
        return info

    def sections(self) -> list[dict[str, Any]]:
        requirements = self.content("requirements") or {}
        sections = requirements.get("sections", [])
        if self.section_filter:
            sections = [s for s in sections if s["section_id"] in self.section_filter]
        return sections


def _check_cancel(ctx: PipelineContext) -> None:
    if ctx.store.get_run(ctx.run_id)["status"] == "cancelled":
        raise CancelledRun("run cancelled")


def _llm_json(ctx: PipelineContext, *, task: str, prompt: str, system: str = SYSTEM) -> dict[str, Any]:
    _check_cancel(ctx)
    status = ctx.llm.availability()
    if not status["available"]:
        raise StepBlocked("LLM Provider 不可用：" + "；".join(status["reasons"]))
    ctx.store.check_budget(ctx.run_id, model_calls=1)
    try:
        data = ctx.llm.generate_json(task=task, system=system, prompt=prompt)
    except ProviderUnavailable as exc:
        raise StepBlocked(str(exc)) from exc
    except ProviderError as exc:
        raise StepFailed(f"{task}: {exc}") from exc
    ctx.store.bump_calls(ctx.run_id, 1, step_id=_current_step())
    data.pop("_usage", None)
    return data


def _skill(ctx: PipelineContext, name: str, schema_name: str | None = None, output: Any = None) -> None:
    try:
        ctx.hooks.before_skill(name, input_schema=schema_name, inputs=output if schema_name else None)
    except (PermissionDenied, HookFailure) as exc:
        raise StepBlocked(str(exc)) from exc


def parse_explicit_skills(request: str) -> list[str]:
    from .registry import parse_explicit_skills as _registry_parse

    return _registry_parse(request)


def _materials_excerpt(ctx: PipelineContext, limit: int = 6000) -> str:
    materials = ctx.content("materials") or {}
    parts = []
    remaining = limit
    for entry in materials.get("files", []):
        if entry.get("sensitive"):
            continue
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        chunk = text[:remaining]
        parts.append(f"【材料：{Path(entry['path']).name}】\n{chunk}")
        remaining -= len(chunk)
        if remaining <= 0:
            break
    return "\n\n".join(parts)


def _template_spec(ctx: PipelineContext) -> dict[str, Any]:
    return ctx.content("template_spec") or {"kind": "none", "sha256": "", "columns": []}


def _strip_claim_prefix(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^[【\[（(]\s*(待核验|待核实|待验证)\s*[】\]）)]\s*", "", cleaned)
    cleaned = re.sub(r"^(待核验|待核实|待验证)[：:]\s*", "", cleaned)
    return cleaned.strip()


def _coerce(value: Any, allowed: list[str], default: str) -> str:
    text = str(value or "").strip()
    return text if text in allowed else default


ASSESSMENT_KINDS = ["hinge_question", "formative", "reflection_prompt"]
MEDIA_FUNCTIONS = [
    "structure",
    "comparison",
    "sequence",
    "causality",
    "spatial_relation",
    "state_change",
    "hierarchy",
    "example",
    "counterexample",
]
MEDIA_KINDS = ["text", "diagram", "animation"]
LAYOUT_ARCHETYPES = ["cover", "section_title", "bullets", "diagram", "table", "closing"]
DENSITIES = ["low", "medium", "high"]


def count_words(units: list[dict[str, Any]]) -> int:
    text = "".join(u.get("text", "") for u in units if u.get("kind") in ("narration", "case"))
    return sum(1 for ch in text if not ch.isspace())


def _word_count_block(ctx: PipelineContext, section_id: str, units: list[dict[str, Any]]) -> dict[str, Any]:
    requirements = ctx.content("requirements") or {}
    section = next((s for s in requirements.get("sections", []) if s["section_id"] == section_id), {})
    rules = requirements.get("word_rules", {})
    wmin = section.get("word_min") or rules.get("min") or 0
    wmax = section.get("word_max") or rules.get("max") or 0
    count = count_words(units)
    return {
        "method": config.RULES["word_counting"]["method"],
        "count": count,
        "min": wmin,
        "max": wmax,
        "in_range": bool(wmin and wmax and wmin <= count <= wmax),
        "scope_note": "统计教师讲解正文（含正文中讲述的案例），不计标题、画面指令、引用索引与独立备注",
    }


# --------------------------------------------------------------------------- steps


def step_parse_inputs(ctx: PipelineContext) -> dict[str, Any]:
    _check_cancel(ctx)
    _skill(ctx, "template-parser")
    notes: list[str] = []
    # Spec 83.2: the batch limits are checked before any parsing or extraction
    # work, and an over-limit batch is rejected rather than truncated.
    try:
        check_import_limits(ctx.material_paths)
    except ParseError as exc:
        raise StepFailed(str(exc)) from exc
    except OSError as exc:
        raise StepFailed(f"输入文件不可读：{exc}") from exc
    template_spec: dict[str, Any]
    if ctx.template_path and ctx.template_path.exists():
        try:
            template_spec = parse_template(ctx.template_path)
        except ParseError as exc:
            raise StepFailed(str(exc)) from exc
        notes.extend(template_spec.get("parse_warnings", []))
    else:
        template_spec = {
            "kind": "none",
            "sha256": "",
            "columns": [],
            "section_headings": [],
            "terminology_rules": [],
            "parse_warnings": ["未提供模板，按无模板模式生成"],
        }
    ctx.emit("template_spec", "template_spec", template_spec, "template-parser")

    files: list[dict[str, Any]] = []
    blocked: list[str] = []
    for path in ctx.material_paths:
        try:
            entry = extract_text(path)
        except ParseError as exc:
            raise StepFailed(str(exc)) from exc
        hits = pii.scan(str(entry.get("text", "")))
        entry["sensitive"] = bool(hits)
        entry["pii_layer"] = pii.LAYER_L1 if hits else "none"
        if hits:
            entry["pii_types"] = sorted({hit["type"] for hit in hits})
            entry["pii_reasons"] = [pii.PII_TYPES_ZH.get(hit["type"], hit["type"]) for hit in hits]
            blocked.append(f"{path.name}：{pii.summarize(hits)}")
        else:
            review = pii.semantic_review(
                ctx.llm,
                pii.mask_text(str(entry.get("text", ""))),
                context=f"项目：{ctx.project_id}",
            )
            if review and review.get("risk") in ("HIGH", "MEDIUM"):
                entry["sensitive"] = True
                entry["pii_layer"] = pii.LAYER_L2
                entry["pii_types"] = ["reidentification"]
                entry["pii_reasons"] = review.get("reasons") or ["语义层判定存在可重识别风险"]
                entry["manual_review_required"] = True
                blocked.append(
                    f"{path.name}：语义隐私复核 {review['risk']}（{'；'.join(entry['pii_reasons'][:2])}）"
                )
            elif review and review.get("risk") == "LOW":
                entry["pii_review"] = "LOW"
        files.append(entry)
        if entry.get("warnings"):
            notes.extend(f"{path.name}: {w}" for w in entry["warnings"])
        if entry.get("text") and not entry["sensitive"]:
            ctx.evidence.add_source(
                source_type="user_material",
                title=path.name,
                identifiers={"path": str(path), "sha256": entry["sha256"]},
                content_level=entry.get("content_level", "full_text"),
                snapshot_text=entry["text"],
                retrieval_note="用户上传材料",
            )
    if blocked:
        notes.append("以下材料含可识别学生资料，已在外部发送前排除（请脱敏后重新上传）：" + "；".join(blocked))
    # M6 §60：输入预算记账；超限按 on_exceed 处理（默认 reject，禁止静默截断）
    from . import input_budget

    try:
        budget_report = input_budget.enforce(
            input_budget.measure(materials=files, template_spec=template_spec)
        )
    except input_budget.InputBudgetExceeded as exc:
        raise StepFailed(f"输入超出预算：{exc}；请精简材料/模板后重试（系统不会静默截断）") from exc
    if budget_report["decision"] == "summarize":
        notes.append("输入超出预算：已按规则标记 summarize（需在后续步骤显式摘要，未静默截断）")
    ctx.emit("materials", "materials", {"files": files, "budget_report": budget_report}, "template-parser")
    from . import registry as skill_registry

    explicit_map = skill_registry.explicit_skill_map()
    invocations = []
    for name in ctx.explicit_skills:
        canonical = skill_registry.resolve_alias(name) or name
        invocations.append(
            {"skill": canonical, "requested_as": name, "steps": explicit_map.get(name, explicit_map.get(canonical, [])), "source": "user_explicit"}
        )
    ctx.emit(
        "skill_invocations",
        "skill_invocations",
        {"requested": ctx.explicit_skills, "resolved": invocations},
        "router",
    )
    if ctx.explicit_skills:
        notes.append("显式调用：" + "、".join(f"/{name}" for name in ctx.explicit_skills))
    return {"notes": notes}


def _apply_project_rules(
    ctx: PipelineContext, requirements: dict[str, Any], template_spec: dict[str, Any]
) -> list[str]:
    notes: list[str] = []
    rules = project_rules.load_rules(ctx.store.base_dir)
    if rules["terminology"]:
        requirements["terminology"] = sorted(
            set(requirements.get("terminology", [])) | set(rules["terminology"])
        )
        for term in rules["terminology"]:
            requirements["items"].append(
                {
                    "req_id": f"req_term_{term}",
                    "text": f"项目规则：称谓统一使用“{term}”",
                    "source": "user_explicit",
                    "scope": "global",
                    "status": "confirmed",
                }
            )
        notes.append(f"项目规则术语：{'、'.join(rules['terminology'])}")
    req_min = requirements["word_rules"].get("min") or None
    req_max = requirements["word_rules"].get("max") or None
    rule_min, rule_max = rules.get("word_min"), rules.get("word_max")
    tpl_min, tpl_max = template_spec.get("word_min"), template_spec.get("word_max")
    chosen: tuple[int | None, int | None] = (req_min, req_max)
    if req_min and req_max:
        if rule_min and rule_max and (rule_min, rule_max) != (req_min, req_max):
            requirements["items"].append(
                {
                    "req_id": "req_wordcount_rule_revision",
                    "text": f"项目规则字数 {rule_min}–{rule_max} 已按本次用户明确修订改为 {req_min}–{req_max}",
                    "source": "user_explicit",
                    "scope": "per_section",
                    "status": "confirmed",
                }
            )
            notes.append("用户请求已修订项目规则字数范围")
        if tpl_min and tpl_max and (tpl_min, tpl_max) != (req_min, req_max):
            requirements["items"].append(
                {
                    "req_id": "req_conflict_template_words",
                    "text": f"模板字数 {tpl_min}–{tpl_max} 与本次请求字数 {req_min}–{req_max} 冲突",
                    "source": "template_extracted",
                    "scope": "per_section",
                    "status": "conflicted",
                    "conflict": "模板要求与用户明确要求不一致，需用户解决后重跑",
                }
            )
            notes.append("字数冲突：模板 vs 请求，等待解决")
    else:
        if rule_min and rule_max:
            chosen = (rule_min, rule_max)
            requirements["items"].append(
                {
                    "req_id": "req_wordcount_rules",
                    "text": f"项目规则字数 {rule_min}–{rule_max}",
                    "source": "user_explicit",
                    "scope": "per_section",
                    "status": "confirmed",
                }
            )
        elif tpl_min and tpl_max:
            chosen = (tpl_min, tpl_max)
            requirements["items"].append(
                {
                    "req_id": "req_wordcount_template",
                    "text": f"模板字数 {tpl_min}–{tpl_max}",
                    "source": "template_extracted",
                    "scope": "per_section",
                    "status": "confirmed",
                }
            )
    if chosen[0] and chosen[1]:
        requirements["word_rules"]["min"], requirements["word_rules"]["max"] = chosen
        for section in requirements["sections"]:
            section["word_min"], section["word_max"] = chosen
    if rules.get("case_per_section"):
        count = int(rules["case_per_section"])
        for section in requirements["sections"]:
            section["required_case_count"] = count
            if "case" not in section["required_components"]:
                section["required_components"].append("case")
        requirements["items"].append(
            {
                "req_id": "req_case_rules",
                "text": f"项目规则：每节至少 {count} 个案例",
                "source": "user_explicit",
                "scope": "per_section",
                "status": "confirmed",
            }
        )
    return notes


def step_requirements(ctx: PipelineContext) -> dict[str, Any]:
    _check_cancel(ctx)
    _skill(ctx, "requirements-builder")
    request = ctx.request
    template_spec = _template_spec(ctx)
    requirements = router.requirements_from_request(request, template_spec)
    requirements["project_id"] = ctx.project_id
    if template_spec.get("kind") != "none":
        requirements["template_ref"] = content_hash(template_spec)
        terminology = set(requirements.get("terminology", []))
        terminology.update(template_spec.get("terminology_rules", []))
        requirements["terminology"] = sorted(t for t in terminology if t)
    notes = _apply_project_rules(ctx, requirements, template_spec)
    # M6 §60：章节数同样受输入预算约束（超限显式失败，不静默裁剪）
    from . import input_budget as budget_mod

    try:
        budget_mod.enforce(
            budget_mod.measure(
                materials=(ctx.content("materials") or {}).get("files", []),
                template_spec=template_spec,
                sections=requirements.get("sections", []),
            )
        )
    except budget_mod.InputBudgetExceeded as exc:
        raise StepFailed(f"输入超出预算：{exc}；请减少章节或拆分任务（系统不会静默裁剪）") from exc
    try:
        schemas.validate(requirements, "requirements")
    except schemas.SchemaError as exc:
        raise StepFailed(f"requirements schema: {exc}") from exc
    deps = [r for r in [ctx.rev("template_spec")] if r]
    ctx.emit("requirements", "requirements", requirements, "requirements-builder", deps=deps)
    notes.append(f"识别 {len(requirements['sections'])} 节")
    return {"notes": notes}


def _design_prompt(ctx: PipelineContext, section: dict[str, Any]) -> str:
    requirements = ctx.content("requirements") or {}
    hints = router.detect_knowledge_hints(section.get("title", ""), ctx.request)
    return f"""任务：为一节课程设计学习目标与理解难点（Backwards Design）。
知识类型候选：{config.ROUTER['knowledge_types']}
本节的启发式知识类型线索：{hints or ['无']}
课程要求：{requirements.get('course')}；输出语言：{requirements.get('language')}
本节：{section['section_id']} {section['title']}
用户原始需求：{ctx.request}
参考材料（截断）：{_materials_excerpt(ctx, 2500) or '无'}

输出 JSON：
{{
  "section_id": "{section['section_id']}",
  "title": "{section['title']}",
  "goals": [{{"goal_id": "g1", "text": "...", "knowledge_type": "concept", "cognitive_demand": "..."}}],
  "prior_knowledge": ["..."],
  "difficulties": [{{"text": "...", "basis": "model_hypothesis"}}],
  "transfer_goal": "...",
  "assessment_evidence": ["能完成……"],
  "sequence": [{{"unit_id": "u1", "title": "...", "goal_ref": "g1", "strategy_refs": []}}]
}}
difficulties.basis 只能取 evidence_supported / source_derived / instructor_provided / model_hypothesis；模型推测必须用 model_hypothesis。"""


def step_learning_design(ctx: PipelineContext) -> dict[str, Any]:
    notes = []
    for section in ctx.sections():
        _check_cancel(ctx)
        data = _llm_json(ctx, task="learning_design", prompt=_design_prompt(ctx, section))
        data["section_id"] = section["section_id"]
        data.setdefault("title", section["title"])
        try:
            schemas.validate(data, "learning_design")
        except schemas.SchemaError as exc:
            raise StepFailed(f"learning_design schema: {exc}") from exc
        ctx.emit(
            f"learning_design:{section['section_id']}",
            "learning_design",
            data,
            "learning-designer",
            deps=[r for r in [ctx.rev("requirements")] if r],
        )
        notes.append(f"{section['section_id']}: {len(data.get('goals', []))} 个目标")
    return {"notes": notes}


def step_claims(ctx: PipelineContext) -> dict[str, Any]:
    _check_cancel(ctx)
    designs = [ctx.content(f"learning_design:{s['section_id']}") for s in ctx.sections()]
    # M6：审阅类任务（audit_only）的被审对象是已有讲稿/论文，Claim 必须从**被审产物**提取；
    # 只看学习设计会让模型因为"没有课程内容"而返回空列表。
    existing_scripts = {
        s["section_id"]: ctx.content(f"script:{s['section_id']}") for s in ctx.sections()
    }
    existing_scripts = {key: value for key, value in existing_scripts.items() if value}
    audit_scope = ""
    if existing_scripts:
        excerpts = []
        for section_id, content in existing_scripts.items():
            units = content.get("units") or []
            text = "\n".join(str(unit.get("text", "")) for unit in units)[:4000]
            excerpts.append(f"[{section_id}]\n{text}")
        audit_scope = (
            "\n待审阅的已有内容（审阅任务的事实性 Claim 必须来自这里）：\n" + "\n".join(excerpts)
        )
    prompt = f"""任务：提取本节课程中必须核验的事实性 Claim（将进入讲解、案例、评价的事实陈述）。
判定标准：Claim 必须是可被研究文献支持或反驳的实证性陈述——群体规律、心理机制、干预/教学法效果、相关或因果结论、数据。
以下内容不是 Claim，禁止提取：教学安排与课堂组织方式、写作与记录规范建议、价值倡导、定义性说明、虚构案例情节、开放反思问题。
每条 Claim 必须给出来源人群（population）与使用位置（usage）。
每节最多 3 条；若本节没有实证性陈述，返回空列表。
claim_type 取 descriptive/correlational/predictive/causal/mechanistic/theoretical/speculative 之一。
课程要求：{ctx.request}
材料（截断）：{_materials_excerpt(ctx, 3000) or '无'}
学习设计：{designs}{audit_scope}
输出 JSON：{{"claims": [{{"text": "...", "claim_type": "descriptive", "population": "...", "usage": "讲解/案例/评价"}}]}}"""
    data = _llm_json(ctx, task="claims", prompt=prompt)
    claims: list[dict[str, Any]] = []
    for item in data.get("claims", [])[:12]:
        text = _strip_claim_prefix(str(item.get("text", "")))
        if not text:
            continue
        from .evidence import CLAIM_TYPES

        record = ctx.evidence.add_claim(
            text,
            _coerce(item.get("claim_type"), CLAIM_TYPES, "descriptive"),
            population=str(item.get("population", "")),
            usage=str(item.get("usage", "")),
        )
        claims.append({**record, "text": text, "claim_type": item.get("claim_type", "descriptive")})
    content = {"claims": claims, "unavailable": []}
    deps = [r for r in [ctx.rev(f"learning_design:{s['section_id']}") for s in ctx.sections()] if r]
    if not claims:
        # Frozen contract: 0 factual Claims fails here, at extraction, with an actionable
        # diagnostic - never downstream at PCK, and never as an empty evidence contract.
        raise StepFailed(
            "Claim 提取结果为空：模型未返回可核验的实证性 Claim。"
            "请检查请求是否包含可核验的心理学事实，或补充材料后重试"
            "（系统不会用空证据继续生产）。"
        )
    ctx.emit("claims", "claims_set", content, "claim-extractor", deps=deps)
    return {"notes": [f"登记 {len(claims)} 条待核验 Claim"]}


def _assessment_prompt(claim: dict[str, Any], source: dict[str, Any], text: str) -> str:
    level_note = "仅摘要/片段可用，未核验全文" if source["content_level"] != "full_text" else "全文可用"
    return f"""任务：判断 Claim 是否被给定来源文本支持。
quote 必须逐字来自来源文本，不得改写、拼接或跨段摘录；找不到可引用句时 found=false。
support 取 direct/indirect/contextual/contradictory/insufficient。
Claim：{claim['text']}
来源类型：{source['source_type']}（{level_note}）
来源标题：{source['title']}
来源文本（截断）：
\"\"\"{text[:5000]}\"\"\"
输出 JSON：{{"found": true, "quote": "...", "quote_location": "...", "support": "direct", "design_note": "...", "scope": "...", "limitations": "...", "uncertainty": "...", "human_review": false}}
human_review 仅在“直接支持但存在争议、或来源之间互相冲突”时设为 true；支持关系为 indirect/contextual/insufficient 时设为 false（系统会走限定改写流程）。"""


def _research_queries(ctx: PipelineContext, claim: dict[str, Any]) -> list[str]:
    prompt = f"""任务：为下面的教育/心理学 Claim 生成 1–2 条学术数据库（Crossref/OpenAlex）英文检索查询。
要求：每条 6–12 个学术关键词，空格分隔，不加引号与布尔运算符。
若 Claim 是实践规范/教学惯例，第二条查询加 practices / guidelines / recommendations / teacher training 之类词；
若 Claim 是实证结论，第二条查询加 review / meta-analysis / longitudinal 之类词。
只输出 JSON：{{"queries": ["query1", "query2"]}}
Claim：{claim['text']}"""
    try:
        data = _llm_json(ctx, task="research_query", prompt=prompt)
    except (StepBlocked, StepFailed):
        return [claim["text"]]
    queries = data.get("queries")
    if isinstance(queries, str):
        queries = [queries]
    if not isinstance(queries, list):
        queries = []
    if data.get("query"):
        queries.append(str(data["query"]))
    cleaned = [str(q).strip() for q in queries if str(q).strip()]
    return cleaned[:2] or [claim["text"]]


def _assess_claim(
    ctx: PipelineContext,
    claim: dict[str, Any],
    source_rev: dict[str, Any],
    text: str,
    notes: list[str],
) -> None:
    source = ctx.evidence.get_source(source_rev["source_id"], source_rev["version"])
    prompt = _assessment_prompt(claim, source, text)
    try:
        data = _llm_json(ctx, task="evidence_review", prompt=prompt)
    except StepFailed as exc:
        notes.append(f"评估失败（{claim['claim_id']}）：{exc}")
        return
    if not data.get("found"):
        notes.append(f"{claim['claim_id']}：在《{source['title']}》中未找到可引用证据")
        return
    quote = str(data.get("quote", "")).strip()
    if not quote or not ctx.evidence.quote_present(source_rev["revision_id"], quote):
        notes.append(f"{claim['claim_id']}：模型引用无法在来源中定位，已拒绝该评估")
        return
    support = str(data.get("support", "insufficient"))
    if support not in RESULT_MAP:
        support = "insufficient"
    if data.get("human_review") and support == "direct":
        result = "HUMAN_REVIEW_REQUIRED"
    else:
        result = RESULT_MAP[support]
    limitations = str(data.get("limitations", ""))
    if source["content_level"] != "full_text":
        prefix = "仅基于摘要/片段核验，未核验全文的方法、结果或机制。"
        limitations = (prefix + limitations).strip()
    ctx.evidence.add_assessment(
        claim_id=claim["claim_id"],
        claim_version=claim["version"],
        source_id=source["source_id"],
        source_version=source["version"],
        quote=quote,
        quote_location=str(data.get("quote_location", "")),
        support=support,
        result=result,
        method="llm-quote-grounded-assessment",
        method_version=config.EVIDENCE_METHOD_VERSION,
        design_note=str(data.get("design_note", "")),
        scope=str(data.get("scope", "")),
        limitations=limitations,
        uncertainty=str(data.get("uncertainty", "")),
    )
    notes.append(f"{claim['claim_id']} → {result}（{source['title']}）")


def _qualify_claim(ctx: PipelineContext, claim: dict[str, Any], limitations: str) -> dict[str, Any] | None:
    # The claims artifact carries no population/usage, so the authoritative scope of the
    # claim being rewritten has to come from the evidence store: otherwise the new
    # revision loses its declared scope and every scope-checking consumer blocks.
    try:
        stored = ctx.evidence.get_claim(claim["claim_id"], claim["version"])
    except KeyError:
        stored = {}
    prompt = f"""任务：下面的 Claim 未获现有证据直接支持。请按证据能够支持的范围改写它：
- 降低强度（相关而非因果、可能而非必然）、限定人群或情境、或收窄结论范围；
- 不改变事实方向，不引入新事实，不添加引用。
只输出 JSON：{{"text": "改写后的 Claim", "population": "...", "note": "改写了什么"}}
原 Claim：{claim['text']}
证据局限：{limitations}"""
    try:
        data = _llm_json(ctx, task="claim_qualify", prompt=prompt)
    except (StepBlocked, StepFailed):
        return None
    new_text = _strip_claim_prefix(str(data.get("text", "")))
    if not new_text or new_text == claim["text"]:
        return None
    record = ctx.evidence.add_claim(
        new_text,
        str(claim.get("claim_type", "descriptive")),
        population=str(data.get("population") or stored.get("population") or claim.get("population", "")),
        usage=str(stored.get("usage") or claim.get("usage", "")),
        claim_id=claim["claim_id"],
    )
    record["text"] = new_text
    return record


def _evidence_rank(item: dict[str, Any]) -> int:
    """M6 生产修正：content_level 由 Provider 声明，但摘要可能为空。

    空摘要的"abstract"级来源无法支撑引文定位，排序时按 metadata 处理，
    避免把 3 个核验名额浪费在无法引用来源上（不降低门禁，只提升检索质量）。
    """
    level = str(item.get("content_level") or "metadata")
    has_text = bool(str(item.get("abstract") or "").strip()) or level in ("full_text", "user_excerpt")
    if not has_text:
        return 0
    return {"full_text": 2, "user_excerpt": 2, "abstract": 1}.get(level, 0)


def step_evidence(ctx: PipelineContext) -> dict[str, Any]:
    _check_cancel(ctx)
    notes: list[str] = []
    claims_doc = ctx.content("claims") or {}
    claims = claims_doc.get("claims", [])
    unavailable: list[str] = []
    research_status = ctx.research.availability()
    llm_status = ctx.llm.availability()
    if not llm_status["available"]:
        unavailable.append("LLM Provider 不可用：" + "；".join(llm_status["reasons"]))
    if not research_status["available"]:
        unavailable.append("研究 Provider 不可用：" + "；".join(research_status["reasons"]))

    materials = (ctx.content("materials") or {}).get("files", [])
    material_sources = [s for s in ctx.evidence.sources() if s["source_type"] == "user_material"]
    force_review = "evidence-review" in ctx.explicit_skills

    for claim in claims:
        if llm_status["available"]:
            for source in material_sources:
                if not force_review and ctx.evidence.claim_status(claim["claim_id"], claim["version"]) == "SUPPORTED":
                    continue
                _assess_claim(ctx, claim, source, ctx.evidence.source_text(source["revision_id"]) or "", notes)
    if materials:
        notes.append(f"已用 {len(material_sources)} 份用户材料进行核验")
    if force_review:
        notes.append("显式调用 evidence-review：对全部 Claim 重新核验")

    research_cfg = config.PROVIDERS.get("research", {})
    source_names = ctx.research.sources() if hasattr(ctx.research, "sources") else ["default"]
    assess_limit = int(research_cfg.get("assess_sources_per_claim", 3))
    fetch_enabled = bool(research_cfg.get("fetch_open_fulltext", True)) and hasattr(
        ctx.research, "fetch_fulltext"
    )
    fetch_limit = int(research_cfg.get("fulltext_per_claim", 1))
    fetch_max_bytes = int(research_cfg.get("fulltext_max_mib", 5)) * 1024 * 1024

    pending = [
        c
        for c in claims
        if force_review or ctx.evidence.claim_status(c["claim_id"], c["version"]) != "SUPPORTED"
    ]
    if pending and research_status["available"] and llm_status["available"]:
        for claim in pending:
            _check_cancel(ctx)
            # M6 §31：执行层预算感知——剩余研究预算不足时降级（少查来源/跳过全文/跳过核验），
            # 而不是把整个运行拖到 BudgetExceeded。
            remaining = (
                ctx.store.budget_remaining(ctx.run_id)["research_requests"]
                if hasattr(ctx.store, "budget_remaining")
                else 10 ** 6
            )
            full_cost = len(source_names) + (2 * fetch_limit if fetch_enabled else 0)
            queries = _research_queries(ctx, claim)
            if remaining <= 0:
                notes.append(
                    f"{claim['claim_id']}：研究预算已用尽，跳过文献核验；该 Claim 将保持未支持并从证据契约排除"
                )
                continue
            claim_fetch_enabled = fetch_enabled
            claim_source_limit = len(queries)
            if remaining < full_cost:
                claim_fetch_enabled = False
                claim_source_limit = 1
                notes.append(
                    f"{claim['claim_id']}：剩余研究预算 {remaining} < 完整核验成本 {full_cost}；降级为单来源核验（跳过全文抓取）"
                )
            per_claim_requests = claim_source_limit * max(len(source_names), 1) + (2 * fetch_limit if claim_fetch_enabled else 0)
            try:
                ctx.store.check_budget(ctx.run_id, research=per_claim_requests)
            except BudgetExceeded:
                notes.append(f"{claim['claim_id']}：预算不足（需要 {per_claim_requests}），跳过文献核验并保持未支持")
                continue
            merged: list[dict[str, Any]] = []
            per_source: dict[str, int] = {}
            errors: dict[str, str] = {}
            for query in queries[:claim_source_limit]:
                try:
                    outcome = ctx.research.search(query, rows=5)
                except (ProviderUnavailable, ProviderError) as exc:
                    errors["search"] = str(exc)
                    break
                ctx.store.bump_research(ctx.run_id, max(1, len(outcome.per_source)))
                for name, count in outcome.per_source.items():
                    per_source[name] = per_source.get(name, 0) + count
                errors.update(outcome.errors)
                merged = _merge_research_items(merged, outcome.items)
                if any(item.get("content_level") in ("abstract", "full_text") for item in outcome.items):
                    break
            ranked = sorted(merged, key=_evidence_rank, reverse=True)
            usable = [item for item in ranked if _evidence_rank(item) > 0]
            if not usable and ranked:
                notes.append(
                    f"{claim['claim_id']}：{len(ranked)} 个来源都没有可引用摘要/全文；"
                    "标题级来源不能支撑引文定位，该 Claim 将保持未支持（等待人工或补充材料）"
                )
            included: list[str] = []
            fetched = 0
            for item in (usable or ranked)[:assess_limit]:
                text = str(item.get("abstract") or "").strip() or str(item.get("title") or "")
                level = item.get("content_level", "metadata")
                if claim_fetch_enabled and fetched < fetch_limit and level != "full_text":
                    pdf_url = item.get("fulltext_url")
                    if not pdf_url and item.get("doi") and hasattr(ctx.research, "find_fulltext"):
                        pdf_url = ctx.research.find_fulltext(str(item["doi"]))
                        ctx.store.bump_research(ctx.run_id, 1)
                        if pdf_url:
                            notes.append(f"{claim['claim_id']}：Unpaywall 定位到开放获取全文")
                    if pdf_url:
                        try:
                            text = ctx.research.fetch_fulltext(pdf_url, max_bytes=fetch_max_bytes)
                            level = "full_text"
                            fetched += 1
                            ctx.store.bump_research(ctx.run_id, 1)
                            notes.append(f"{claim['claim_id']}：已获取开放获取全文（{item.get('database', '')}）")
                        except (ProviderError, ProviderUnavailable) as exc:
                            notes.append(f"{claim['claim_id']}：全文获取失败（{exc}）")
                source = ctx.evidence.add_source(
                    source_type="journal_article",
                    title=item.get("title") or "(无标题)",
                    identifiers={
                        "doi": item.get("doi"),
                        "container": item.get("container"),
                        "database": item.get("database"),
                    },
                    publish_date=item.get("publish_date"),
                    content_level=level if text.strip() else "metadata",
                    snapshot_text=text,
                    retrieval_note=f"检索来源：{item.get('database', 'unknown')}",
                )
                if item.get("doi"):
                    included.append(str(item["doi"]))
                if not text.strip():
                    notes.append(f"{source['source_id']}：仅有元数据，无法核验")
                    continue
                _assess_claim(ctx, claim, source, text, notes)
            ctx.store.add_search_log(
                {
                    "database": "+".join(source_names) or "unknown",
                    "query": " ｜ ".join(queries),
                    "filters": {"claim": claim["text"], "queries": queries, "per_source": per_source},
                    "date": now_iso(),
                    "results_count": len(merged),
                    "included": included,
                    "excluded": [str(i.get("title", "")) for i in ranked[assess_limit:]],
                    "reason": f"按内容层级排序取前 {assess_limit} 条进入核验",
                    "outcome": "error" if errors and not merged else "ok",
                    "note": "；".join(f"{k}: {v}" for k, v in errors.items()) if errors else "",
                },
                run_id=ctx.run_id,
            )
            if errors and not merged:
                notes.append(f"{claim['claim_id']} 检索失败：{'；'.join(errors.values())}")
            if ctx.evidence.claim_status(claim["claim_id"], claim["version"]) == "SUPPORTED":
                continue
    elif pending:
        notes.append("存在未获支持的 Claim，且研究 Provider 或 LLM 不可用，未能补充核验")

    qualified: list[str] = []
    if llm_status["available"]:
        for claim in claims:
            status = ctx.evidence.claim_status(claim["claim_id"], claim["version"])
            if status != "QUALIFY_REQUIRED":
                continue
            relevant = [
                a
                for a in ctx.evidence.assessments(claim["claim_id"], claim["version"])
                if a["result"] == "QUALIFY_REQUIRED"
            ]
            if not relevant:
                continue
            ctx.store.check_budget(ctx.run_id, model_calls=2)
            new_claim = _qualify_claim(ctx, claim, relevant[0]["limitations"] or "")
            if not new_claim:
                continue
            qualified.append(new_claim["revision_id"])
            notes.append(
                f"{claim['claim_id']}：按证据范围限定改写为 v{new_claim['version']} 并重新核验"
            )
            source_rev = relevant[0]["source_rev"]
            try:
                source_id, source_version = source_rev.rsplit("@v", 1)
                source_version_int = int(source_version)
            except ValueError:
                continue
            text = ctx.evidence.source_text(source_rev) or ""
            if text.strip():
                _assess_claim(
                    ctx,
                    {
                        "claim_id": new_claim["claim_id"],
                        "version": new_claim["version"],
                        "text": new_claim["text"],
                    },
                    {"source_id": source_id, "version": source_version_int, "revision_id": source_rev},
                    text,
                    notes,
                )

    current_claims: list[dict[str, Any]] = []
    updated = False
    for claim in claims:
        latest = ctx.evidence.get_claim(claim["claim_id"])
        current_claims.append(
            {
                "claim_id": latest["claim_id"],
                "version": latest["version"],
                "text": latest["text"],
                "claim_type": latest["claim_type"],
            }
        )
        if latest["version"] != claim["version"]:
            updated = True
    if updated:
        ctx.emit(
            "claims",
            "claims_set",
            {"claims": current_claims, "unavailable": []},
            "claim-extractor",
            deps=[r for r in [ctx.rev("claims")] if r],
        )
        notes.append("已生成限定改写后的 Claim 新版本并重新核验")
    statuses = [
        {
            "claim_id": claim["claim_id"],
            "version": claim["version"],
            "status": ctx.evidence.claim_status(claim["claim_id"], claim["version"]),
        }
        for claim in current_claims
    ]
    # evidence_index is the evidence contract PCK may consume. Consumability is the
    # frozen E/1 contract read from its single owner: only PCK_REQUIRED_STATUS enters
    # `claims`; every other status is registered in `excluded_claims` - never hidden,
    # never deleted, never disguised as supported - and stays auditable.
    from . import preconditions as precondition_mod

    required_status = precondition_mod.PCK_REQUIRED_STATUS
    consumable = [item for item in statuses if item["status"] == required_status]
    excluded = [
        {
            "claim_id": item["claim_id"],
            "version": item["version"],
            "status": item["status"],
            "reason": (
                f"状态 {item['status']} 不满足冻结的 PCK 证据契约（只允许 {required_status}）；"
                "已从证据契约排除，等待人工复核或补充材料"
            ),
        }
        for item in statuses
        if item["status"] != required_status
    ]
    if excluded:
        notes.append(
            f"证据契约排除 {len(excluded)} 条不可消费 Claim（"
            + "、".join(sorted({item['status'] for item in excluded}))
            + "）；Claim 与核验记录仍保留在 claims/assessments 中"
        )
    index = {
        "claims": consumable,
        "excluded_claims": excluded,
        "declared_no_empirical_claims": bool(claims_doc.get("no_empirical_claims")) and not consumable,
        "declared_no_consumable_claims": bool(not consumable and (statuses or excluded)),
        "assessments": [
            {
                "assessment_id": a["assessment_id"],
                "claim_rev": a["claim_rev"],
                "source_rev": a["source_rev"],
                "result": a["result"],
                "quote_location": a["quote_location"],
            }
            for a in ctx.evidence.assessments()
        ],
        "unavailable": unavailable,
    }
    deps = [r for r in [ctx.rev("claims")] if r]
    ctx.emit("evidence_index", "evidence_index", index, "evidence-reviewer", deps=deps)
    return {"notes": notes, "unavailable": unavailable}


def _plan_prompt(ctx: PipelineContext, section: dict[str, Any]) -> str:
    design = ctx.content(f"learning_design:{section['section_id']}") or {}
    evidence_doc = ctx.content("evidence_index") or {}
    supported = []
    pending = []
    claims_doc = ctx.content("claims") or {}
    for claim in claims_doc.get("claims", []):
        if ctx.evidence.is_supported(f"{claim['claim_id']}@v{claim['version']}"):
            supported.append(claim)
        else:
            pending.append(claim)
    strategy_map = {g["goal_id"]: router.allowed_strategies(g.get("knowledge_type", "concept")) for g in design.get("goals", [])}
    return f"""任务：为每个学习目标选择教学策略并给出 PCK 教学说明，另给出 UDL 障碍与替代路径。
策略只能从每个目标对应的候选集合中选择：{strategy_map}
不得发明心理学事实；所有事实只能来自已核验 Claim 列表。
学习设计：{design}
已核验 Claim：{supported}
待核验 Claim（不得作为事实使用）：{pending}
输出 JSON：
{{
  "section_id": "{section['section_id']}",
  "strategies": [{{"goal_ref": "g1", "knowledge_type": "concept", "strategy": "explicit-instruction", "rationale": "..."}}],
  "pck_notes": ["..."],
  "udl": {{"barriers": ["..."], "options": [{{"barrier": "...", "option": "...", "same_goal_ref": "g1", "core_demand_preserved": true, "representation": "...", "action_expression": "...", "engagement": "..."}}], "support_review_flags": []}}
}}
UDL 替代路径必须保持同一目标与核心认知要求；不得把更简单的任务伪装成更无障碍的任务。
如存在无法仅靠通用课程设计解决的障碍，只能写入 support_review_flags，不得直接建议转介。"""


def _normalize_plan(ctx: PipelineContext, section: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    design = ctx.content(f"learning_design:{section['section_id']}") or {}
    for strategy in data.get("strategies", []):
        goal = next((g for g in design.get("goals", []) if g["goal_id"] == strategy.get("goal_ref")), None)
        if goal:
            strategy["knowledge_type"] = goal.get("knowledge_type", strategy.get("knowledge_type", ""))
            strategy["allowed_set"] = router.allowed_strategies(goal.get("knowledge_type", "concept"))
    return data


def _plan_violations(ctx: PipelineContext, section: dict[str, Any], data: dict[str, Any]) -> list[str]:
    violations = []
    for strategy in data.get("strategies", []):
        allowed = strategy.get("allowed_set") or []
        if allowed and strategy.get("strategy") not in allowed:
            violations.append(
                f"目标 {strategy.get('goal_ref')}：策略 {strategy.get('strategy')} 不在候选集合 {allowed}"
            )
    return violations


def step_teaching_plan(ctx: PipelineContext) -> dict[str, Any]:
    notes = []
    # Fail-closed execution precondition, declared in the registry and evaluated
    # through the shared checker so both the static and dynamic runtime enforce it.
    from . import registry as _registry

    declared = (_registry.get("pck-developer") or {}).get("preconditions") or []
    blocked = preconditions.block_reason(ctx, {"preconditions": declared})
    if blocked:
        raise StepBlocked(blocked)
    for section in ctx.sections():
        _check_cancel(ctx)
        _skill(ctx, "pck-developer")
        data = _llm_json(ctx, task="teaching_plan", prompt=_plan_prompt(ctx, section))
        data["section_id"] = section["section_id"]
        data = _normalize_plan(ctx, section, data)
        violations = _plan_violations(ctx, section, data)
        if violations:
            retry_prompt = (
                _plan_prompt(ctx, section)
                + "\n\n上一次输出存在策略越界，必须修正：\n"
                + "\n".join(violations)
                + "\n请重新输出完整 JSON；strategies 只能使用对应目标 allowed_set 中的策略。"
            )
            data = _llm_json(ctx, task="teaching_plan_fix", prompt=retry_prompt)
            data["section_id"] = section["section_id"]
            data = _normalize_plan(ctx, section, data)
            remaining = _plan_violations(ctx, section, data)
            notes.append(
                f"{section['section_id']}: 策略越界已重生成（{len(violations)} 处）"
                + (f"，仍有 {len(remaining)} 处待人工处理" if remaining else "")
            )
        try:
            schemas.validate(data, "teaching_plan")
        except schemas.SchemaError as exc:
            raise StepFailed(f"teaching_plan schema: {exc}") from exc
        deps = [r for r in [ctx.rev(f"learning_design:{section['section_id']}"), ctx.rev("evidence_index")] if r]
        ctx.emit(f"teaching_plan:{section['section_id']}", "teaching_plan", data, "pck-developer", deps=deps)
        notes.append(f"{section['section_id']}: {len(data.get('strategies', []))} 条策略")
    return {"notes": notes}


def _case_prompt(ctx: PipelineContext, section: dict[str, Any]) -> str:
    design = ctx.content(f"learning_design:{section['section_id']}") or {}
    plan = ctx.content(f"teaching_plan:{section['section_id']}") or {}
    return f"""任务：为本节设计 1 个教学案例（可明确标注为虚构），用于解释学习难点。
学习设计：{design}
教学策略：{plan.get('strategies', [])}
材料（截断）：{_materials_excerpt(ctx, 2000) or '无'}
约束：
- 案例默认虚构（kind=fictional），不要伪装成真实研究事实；
- 如案例包含新的事实性陈述（研究结论、数据、机制），放入 new_factual_claims，这些内容不能作为正式事实；
- claim_refs 只能引用已核验 Claim（可为空）。
输出 JSON：{{"case_id": "case1", "section_id": "{section['section_id']}", "title": "...", "kind": "fictional", "text": "...", "difficulty": "...", "linked_goal": "g1", "claim_refs": [], "new_factual_claims": []}}"""


def step_cases(ctx: PipelineContext) -> dict[str, Any]:
    notes = []
    registered: list[str] = []
    for section in ctx.sections():
        _check_cancel(ctx)
        _skill(ctx, "case-designer")
        data = _llm_json(ctx, task="case", prompt=_case_prompt(ctx, section))
        data["section_id"] = section["section_id"]
        new_claims = []
        for text in data.get("new_factual_claims", []) or []:
            record = ctx.evidence.add_claim(str(text), "descriptive", usage="案例")
            new_claims.append(f"{record['revision_id']}")
        if new_claims:
            data["claim_refs"] = sorted(set(list(data.get("claim_refs", [])) + new_claims))
            data["new_factual_claims"] = []
            registered.extend(new_claims)
            notes.append(f"{section['section_id']}: 案例新增 {len(new_claims)} 条事实已登记为 Claim，交由补充核验")
        try:
            schemas.validate(data, "case")
        except schemas.SchemaError as exc:
            raise StepFailed(f"case schema: {exc}") from exc
        deps = [r for r in [ctx.rev(f"teaching_plan:{section['section_id']}")] if r]
        ctx.emit(f"case:{section['section_id']}:1", "case", data, "case-designer", deps=deps)
    if registered:
        claims_doc = ctx.content("claims") or {"claims": []}
        merged = {claim["claim_id"]: claim for claim in claims_doc.get("claims", [])}
        for ref in registered:
            claim_id = ref.split("@v", 1)[0]
            latest = ctx.evidence.get_claim(claim_id)
            merged[claim_id] = {
                "claim_id": claim_id,
                "version": latest["version"],
                "text": latest["text"],
                "claim_type": latest["claim_type"],
            }
        ctx.emit(
            "claims",
            "claims_set",
            {"claims": list(merged.values()), "unavailable": claims_doc.get("unavailable", [])},
            "case-designer",
            deps=[r for r in [ctx.rev("claims")] if r],
        )
        notes.append("案例新增事实已登记并交由补充核验步骤")
    return {"notes": notes}


def _assessment_prompt_for(ctx: PipelineContext, section: dict[str, Any]) -> str:
    design = ctx.content(f"learning_design:{section['section_id']}") or {}
    return f"""任务：为本节生成形成性评价：至少 1 个 hinge question（含干扰项与解析）与 1 个反思/迁移问题。
学习目标：{[g['goal_id'] + ':' + g['text'] for g in design.get('goals', [])]}
题目与答案、干扰项、解析必须一致；涉及计算必须独立重算。
输出 JSON：{{"section_id": "{section['section_id']}", "items": [
  {{"assessment_id": "a1", "kind": "hinge_question", "question": "...", "options": ["A...", "B...", "C...", "D..."], "answer": "B", "distractors": ["..."], "rationale": "...", "target_goal": "g1", "claim_refs": [], "student_viewable": true}},
  {{"assessment_id": "a2", "kind": "reflection_prompt", "question": "...", "answer": "开放", "rationale": "...", "target_goal": "g1", "student_viewable": true}}
]}}"""


def step_assessments(ctx: PipelineContext) -> dict[str, Any]:
    notes = []
    for section in ctx.sections():
        _check_cancel(ctx)
        _skill(ctx, "assessment-designer")
        data = _llm_json(ctx, task="assessment", prompt=_assessment_prompt_for(ctx, section))
        data["section_id"] = section["section_id"]
        for item in data.get("items", []) or []:
            item["kind"] = _coerce(item.get("kind"), ASSESSMENT_KINDS, "formative")
            if item.get("options") is None:
                item.pop("options", None)
            if item.get("distractors") is None:
                item.pop("distractors", None)
        try:
            schemas.validate(data, "assessment")
        except schemas.SchemaError as exc:
            raise StepFailed(f"assessment schema: {exc}") from exc
        deps = [r for r in [ctx.rev(f"learning_design:{section['section_id']}")] if r]
        ctx.emit(f"assessment:{section['section_id']}", "assessment", data, "assessment-designer", deps=deps)
        notes.append(f"{section['section_id']}: {len(data.get('items', []))} 题")
    return {"notes": notes}


def _script_prompt(ctx: PipelineContext, section: dict[str, Any]) -> str:
    design = ctx.content(f"learning_design:{section['section_id']}") or {}
    plan = ctx.content(f"teaching_plan:{section['section_id']}") or {}
    case = ctx.content(f"case:{section['section_id']}:1") or {}
    requirements = ctx.content("requirements") or {}
    claims_doc = ctx.content("claims") or {}
    supported, pending = [], []
    for claim in claims_doc.get("claims", []):
        ref = f"{claim['claim_id']}@v{claim['version']}"
        entry = {"ref": ref, "text": claim["text"]}
        (supported if ctx.evidence.is_supported(ref) else pending).append(entry)
    spec = _template_spec(ctx)
    columns = [c["name"] for c in spec.get("columns", [])]
    wmin = section.get("word_min") or requirements.get("word_rules", {}).get("min")
    wmax = section.get("word_max") or requirements.get("word_rules", {}).get("max")
    return f"""任务：生成一节在线课程脚本（教师讲解 + 画面提示 + 案例展开 + 互动），中文。
本节：{section['section_id']} {section['title']}
学习目标与设计：{design}
教学策略：{plan.get('strategies', [])}
可用案例：{case.get('text', '')}
模板栏目：{columns or '无模板'}
字数要求：{wmin}–{wmax} 字（仅统计教师讲解正文与正文中讲述的案例）
术语要求：{requirements.get('terminology', [])}
已核验 Claim（可作为事实，引用时写入 claim_refs，格式 id@vN）：{supported}
待核验 Claim（禁止作为事实陈述；如需提及，必须使用 placeholder=true 并写“【待核验】”）：{pending}
硬约束：
- 不得引入任何不在已核验列表中的新事实性结论；
- 案例说明标注为虚构；
- 讲解正文满足字数要求；
- 画面提示必须写 visual_function（知识功能）。
输出 JSON：{{"units": [
  {{"unit_id": "u1", "kind": "title", "text": "{section['title']}"}},
  {{"unit_id": "u2", "kind": "narration", "text": "...", "claim_refs": []}},
  {{"unit_id": "u3", "kind": "visual", "text": "画面提示", "visual_function": "structure"}},
  {{"unit_id": "u4", "kind": "case", "text": "案例正文（虚构）", "case_ref": "case1"}},
  {{"unit_id": "u5", "kind": "interaction", "text": "课堂互动/提问"}}
]}}"""


def _finalize_script(ctx: PipelineContext, section: dict[str, Any], units: list[dict[str, Any]]) -> dict[str, Any]:
    spec = _template_spec(ctx)
    case = ctx.content(f"case:{section['section_id']}:1") or {}
    if case.get("text") and not any(u.get("kind") == "case" for u in units):
        units.append(
            {
                "unit_id": f"{section['section_id']}-case",
                "kind": "case",
                "text": case["text"],
                "case_ref": case.get("case_id", "case1"),
                "claim_refs": list(case.get("claim_refs", [])),
            }
        )
    if not any(u.get("kind") == "title" for u in units):
        units.insert(0, {"unit_id": f"{section['section_id']}-title", "kind": "title", "text": section["title"]})
    for idx, unit in enumerate(units):
        unit.setdefault("unit_id", f"{section['section_id']}-u{idx}")
        refs = [r for r in unit.get("claim_refs", []) if r]
        if any(not ctx.evidence.is_supported(r) for r in refs):
            unit["placeholder"] = True
    if any(u.get("placeholder") for u in units):
        pending_refs = sorted(
            {r for u in units for r in u.get("claim_refs", []) if not ctx.evidence.is_supported(r)}
        )
        units.append(
            {
                "unit_id": f"{section['section_id']}-pending",
                "kind": "note",
                "text": "【待核验】" + "；".join(pending_refs),
            }
        )
    script: dict[str, Any] = {
        "section_id": section["section_id"],
        "title": section["title"],
        "template_ref": content_hash(spec) if spec.get("kind") != "none" else None,
        "units": units,
        "word_count": _word_count_block(ctx, section["section_id"], units),
    }
    if script["template_ref"] is None:
        script.pop("template_ref")
    try:
        schemas.validate(script, "script")
    except schemas.SchemaError as exc:
        raise StepFailed(f"script schema: {exc}") from exc
    return script


def _script_deps(ctx: PipelineContext, section: dict[str, Any]) -> list[str]:
    return [
        r
        for r in [
            ctx.rev(f"learning_design:{section['section_id']}"),
            ctx.rev(f"teaching_plan:{section['section_id']}"),
            ctx.rev(f"case:{section['section_id']}:1"),
        ]
        if r
    ]


def step_scripts(ctx: PipelineContext) -> dict[str, Any]:
    notes = []
    for section in ctx.sections():
        _check_cancel(ctx)
        _skill(ctx, "script-writer")
        data = _llm_json(ctx, task="script", prompt=_script_prompt(ctx, section))
        units = data.get("units") or []
        for unit in units:
            if unit.get("placeholder") and not unit.get("claim_refs"):
                text = str(unit.get("text", "")).strip()
                if text:
                    record = ctx.evidence.add_claim(text[:160], "descriptive", usage="脚本待核验")
                    unit["claim_refs"] = [record["revision_id"]]
                    notes.append(f"{section['section_id']}: 待核验占位已登记为 {record['revision_id']}")
        script = _finalize_script(ctx, section, units)
        ctx.emit(f"script:{section['section_id']}", "script", script, "script-writer", deps=_script_deps(ctx, section))
        notes.append(f"{section['section_id']}: {script['word_count']['count']} 字")
    return {"notes": notes}


AUTO_FIX_GATES = ("G1", "G4", "G7")


def _fix_prompt(section: dict[str, Any], script: dict[str, Any], failed: list[dict[str, Any]], requirements: dict[str, Any]) -> str:
    issues = []
    for result in failed:
        for issue in result["issues"]:
            issues.append(f"[{result['gate_id']}] {issue['location']}: {issue['reason']}；建议：{issue.get('next_step', '')}")
    wc = script.get("word_count", {})
    count = wc.get("count", 0)
    lo, hi = wc.get("min") or 0, wc.get("max") or 0
    narration_chars = sum(
        len(u.get("text", "")) for u in script.get("units", []) if u.get("kind") == "narration"
    )
    case_chars = sum(len(u.get("text", "")) for u in script.get("units", []) if u.get("kind") == "case")
    breakdown = f"讲解 {narration_chars} 字，案例 {case_chars} 字，合计 {count} 字"
    if lo and hi:
        target = (lo + hi) // 2
        if count > hi:
            guidance = (
                f"当前 {breakdown}，超出上限 {count - hi} 字；至少删减 {count - hi} 字，目标 {target} 字；"
                "只做删减与合并，不要新增内容；优先压缩案例与讲解中的冗余修饰，保留术语、案例结构与关键步骤；"
                "输出前请按“讲解+案例的非空白字符数”逐字复算，确保落在范围内"
            )
        elif count < lo:
            guidance = (
                f"当前 {breakdown}，不足下限 {lo - count} 字；至少补足 {lo - count} 字，目标 {target} 字；"
                "补充课堂互动示例或观察细节，不得引入未核验事实"
            )
        else:
            guidance = f"当前 {breakdown}，已在范围内，保持字数"
    else:
        guidance = "未指定字数范围"
    return f"""任务：按质检问题修订课程脚本，输出修订后的完整 units 数组。
本节：{section['section_id']} {section['title']}
质检问题：
{chr(10).join(issues)}
原脚本：{script}
硬约束：
- 不得引入未核验的新事实性结论；
- 术语要求：{requirements.get('terminology', [])}；
- 字数要求：{lo}–{hi} 字（仅统计讲解与案例单元的非空白字符，含标点、数字和字母）；
- 字数修订目标：{guidance}；
- 画面提示必须写 visual_function；保留案例单元。
输出 JSON：{{"units": [{{"unit_id": "...", "kind": "title|narration|visual|case|interaction", "text": "...", "claim_refs": [], "visual_function": ""}}]}}"""


def fix_script(
    ctx: PipelineContext,
    section: dict[str, Any],
    script: dict[str, Any],
    failed: list[dict[str, Any]],
) -> dict[str, Any]:
    _check_cancel(ctx)
    _skill(ctx, "script-writer")
    requirements = ctx.content("requirements") or {}
    data = _llm_json(ctx, task="script_fix", prompt=_fix_prompt(section, script, failed, requirements))
    revised = _finalize_script(ctx, section, data.get("units") or script.get("units") or [])
    ctx.emit(f"script:{section['section_id']}", "script", revised, "script-writer", deps=_script_deps(ctx, section))
    return revised


def _media_plan_prompt(ctx: PipelineContext, section: dict[str, Any]) -> str:
    design = ctx.content(f"learning_design:{section['section_id']}") or {}
    script = ctx.content(f"script:{section['section_id']}") or {}
    visuals = [u.get("text", "") for u in script.get("units", []) if u.get("kind") == "visual"]
    return f"""任务：为这一节课程做媒体选型（Media Router），对每个知识点判断适合的媒体形式。
学习目标：{design.get('goals', [])}
脚本画面提示：{visuals}
规则：
- 静态对比、结构、层级、部分-整体 → diagram；
- 时间变化/动态过程/逐步累积/状态转移/因果链展开/错误与正确过程对比 → 才可能 animation；
- 其余 → text。
每个知识点输出：item_id、goal_ref、knowledge_function（structure/comparison/sequence/causality/spatial_relation/state_change/hierarchy/example/counterexample）、
temporal_dependency、spatial_dependency、comparison_dependency、persistence_need、learner_interaction_need、recommended_medium（text/diagram/animation）、rationale。
输出 JSON：{{"items": [{{"item_id": "i1", "goal_ref": "g1", "knowledge_function": "comparison", "temporal_dependency": false, "spatial_dependency": false, "comparison_dependency": true, "persistence_need": true, "learner_interaction_need": false, "recommended_medium": "diagram", "rationale": "..."}}]}}"""


def _enforce_medium(item: dict[str, Any]) -> dict[str, Any]:
    item["recommended_medium"] = _coerce(item.get("recommended_medium"), MEDIA_KINDS, "text")
    item["knowledge_function"] = _coerce(item.get("knowledge_function"), MEDIA_FUNCTIONS, "structure")
    if not isinstance(item.get("rationale"), str):
        item["rationale"] = str(item.get("rationale") or "")
    item["temporal_dependency"] = bool(item.get("temporal_dependency"))
    item["spatial_dependency"] = bool(item.get("spatial_dependency"))
    item["comparison_dependency"] = bool(item.get("comparison_dependency"))
    item["persistence_need"] = bool(item.get("persistence_need"))
    item["learner_interaction_need"] = bool(item.get("learner_interaction_need"))
    if item.get("recommended_medium") == "animation" and not item.get("temporal_dependency"):
        fallback = "diagram" if (item.get("comparison_dependency") or item.get("spatial_dependency")) else "text"
        item["recommended_medium"] = fallback
        item["rationale"] = (
            str(item.get("rationale", "")).rstrip("；") + "；[系统校正] temporal_dependency=false，动画降级为 " + fallback
        ).lstrip("；")
    return item


def _lesson_plan_prompt(ctx: PipelineContext, section: dict[str, Any]) -> str:
    design = ctx.content(f"learning_design:{section['section_id']}") or {}
    plan = ctx.content(f"teaching_plan:{section['section_id']}") or {}
    return f"""任务：为这一节写教案（lesson plan）。
学习设计：{design}
教学策略：{plan.get('strategies', [])}
要求：
- objectives 对应学习目标（goal_ref 使用设计中的 goal_id，text 用可观察动词）；
- key_points / difficult_points 来自设计与难点；
- process 为课堂教学过程：每个环节包含 stage、minutes（>0）、teacher_activity、student_activity、intent（教学意图）；
- preparation 为教学准备；board_design 为板书/画面设计；homework 为课后任务；
- 不得引入未获核验的事实性结论。
输出 JSON：{{"section_id": "{section['section_id']}", "title": "...", "objectives": [{{"goal_ref": "g1", "text": "..."}}], "key_points": ["..."], "difficult_points": ["..."], "preparation": ["..."], "process": [{{"stage": "导入", "minutes": 5, "teacher_activity": "...", "student_activity": "...", "intent": "..."}}], "board_design": "...", "homework": ["..."]}}"""


def step_lesson_plans(ctx: PipelineContext) -> dict[str, Any]:
    notes = []
    for section in ctx.sections():
        _check_cancel(ctx)
        _skill(ctx, "pck-developer")
        data = _llm_json(ctx, task="lesson_plan", prompt=_lesson_plan_prompt(ctx, section))
        data["section_id"] = section["section_id"]
        if not data.get("title"):
            data["title"] = section.get("title", "")
        try:
            schemas.validate(data, "lesson_plan")
        except schemas.SchemaError as exc:
            raise StepFailed(f"lesson_plan schema: {exc}") from exc
        deps = [r for r in [ctx.rev(f"teaching_plan:{section['section_id']}")] if r]
        ctx.emit(f"lesson_plan:{section['section_id']}", "lesson_plan", data, "lesson-designer", deps=deps)
        notes.append(f"{section['section_id']}: {len(data.get('process', []))} 个教学环节")
    return {"notes": notes}


def _worksheet_prompt(ctx: PipelineContext, section: dict[str, Any]) -> str:
    design = ctx.content(f"learning_design:{section['section_id']}") or {}
    assessment = ctx.content(f"assessment:{section['section_id']}") or {}
    case = ctx.content(f"case:{section['section_id']}:1") or {}
    return f"""任务：为这一节设计学习单（worksheet），学生按单完成课堂任务。
学习目标：{[goal['text'] for goal in design.get('goals', [])]}
已有评价题（可改写为学习单任务，不要重复原题）：{[item.get('question') for item in assessment.get('items', [])]}
可用案例：{case.get('text', '')}
要求：
- tasks 覆盖 3–5 个任务，kind 取 record_table/sorting/rewrite/reflection/practice；prompt 面向学生、指令清晰；
- record_table 用 fields 给出表格列；每个任务给 answer 与 answer_notes（供教师版使用；学生版会移除答案）；
- reflection_questions 为开放反思问题；
- 不得引入未获核验的事实性结论。
输出 JSON：{{"section_id": "{section['section_id']}", "title": "...", "instructions": "...", "tasks": [{{"task_id": "t1", "kind": "sorting", "prompt": "...", "fields": [], "answer": "...", "answer_notes": "..."}}], "reflection_questions": ["..."], "student_version_note": "学生版不含答案"}}"""


def step_worksheets(ctx: PipelineContext) -> dict[str, Any]:
    notes = []
    for section in ctx.sections():
        _check_cancel(ctx)
        _skill(ctx, "assessment-designer")
        data = _llm_json(ctx, task="worksheet", prompt=_worksheet_prompt(ctx, section))
        data["section_id"] = section["section_id"]
        if not data.get("title"):
            data["title"] = section.get("title", "")
        if not data.get("student_version_note"):
            data["student_version_note"] = "学生版不含答案"
        try:
            schemas.validate(data, "worksheet")
        except schemas.SchemaError as exc:
            raise StepFailed(f"worksheet schema: {exc}") from exc
        deps = [r for r in [ctx.rev(f"assessment:{section['section_id']}")] if r]
        ctx.emit(f"worksheet:{section['section_id']}", "worksheet", data, "worksheet-designer", deps=deps)
        notes.append(f"{section['section_id']}: {len(data.get('tasks', []))} 个学习任务")
    return {"notes": notes}


def step_media_plan(ctx: PipelineContext) -> dict[str, Any]:
    notes = []
    for section in ctx.sections():
        _check_cancel(ctx)
        _skill(ctx, "pck-developer")
        data = _llm_json(ctx, task="media_plan", prompt=_media_plan_prompt(ctx, section))
        items = [_enforce_medium(dict(item)) for item in data.get("items", [])]
        content = {"section_id": section["section_id"], "items": items}
        try:
            schemas.validate(content, "media_plan")
        except schemas.SchemaError as exc:
            raise StepFailed(f"media_plan schema: {exc}") from exc
        deps = [r for r in [ctx.rev(f"script:{section['section_id']}")] if r]
        ctx.emit(f"media_plan:{section['section_id']}", "media_plan", content, "media-router", deps=deps)
        kinds = [item["recommended_medium"] for item in items]
        notes.append(f"{section['section_id']}: {len(items)} 个知识点（{kinds.count('diagram')} 图示 / {kinds.count('animation')} 动画候选）")
    return {"notes": notes}


def _diagram_prompt(ctx: PipelineContext, section: dict[str, Any], items: list[dict[str, Any]]) -> str:
    return f"""任务：为以下知识点生成教学图示（SVG），视觉必须承担知识功能（不是装饰）。
知识点：{items}
要求：
- 每个知识点输出一个图：diagram_id、item_id、diagram_type（concept_relationship/comparison/sequence/causality/timeline/hierarchy/state/part_whole/evidence_map/case_flow/observation_flow）、title、alt_text；
- semantics：{{"nodes": [{{"id","label","kind"}}], "edges": [{{"from","to","label"}}]}}，节点 id 必须齐全；
- svg：完整 <svg> 标记，必须含 viewBox，只用 <rect>/<line>/<path>/<text>/<circle> 等基础图形；
- 禁止 <script>、事件属性（on*）、外部链接/图片、<foreignObject>；文字用 <text> 直接标注；
- 画布建议 960×540，配色克制，中文标签简洁。
输出 JSON：{{"diagrams": [{{"diagram_id": "d1", "item_id": "i1", "diagram_type": "comparison", "title": "...", "alt_text": "...", "semantics": {{...}}, "svg": "<svg viewBox=...>...</svg>"}}]}}"""


def step_diagrams(ctx: PipelineContext) -> dict[str, Any]:
    notes = []
    for section in ctx.sections():
        _check_cancel(ctx)
        plan = ctx.content(f"media_plan:{section['section_id']}") or {}
        items = [item for item in plan.get("items", []) if item.get("recommended_medium") == "diagram"]
        diagrams: list[dict[str, Any]] = []
        if items:
            prompt = _diagram_prompt(ctx, section, items)
            data = _llm_json(ctx, task="diagram_svg", prompt=prompt)
            raw = data.get("diagrams") or []
            problems = {str(d.get("diagram_id")): media.validate_svg(str(d.get("svg", ""))) for d in raw}
            if any(problems.values()) or not raw:
                feedback = "\n".join(
                    f"- {key}: {'；'.join(value)}" for key, value in problems.items() if value
                ) or "- 未输出任何 diagram"
                retry = prompt + f"\n\n上一次输出未通过校验，请修正并输出完整 JSON：\n{feedback}"
                data = _llm_json(ctx, task="diagram_svg_fix", prompt=retry)
                raw = data.get("diagrams") or []
            for entry in raw:
                svg = str(entry.get("svg", ""))
                issues = media.validate_svg(svg)
                if issues:
                    notes.append(f"{section['section_id']}/{entry.get('diagram_id')}：SVG 校验未通过（{'；'.join(issues)}），已跳过")
                    continue
                path = media.write_media_file(
                    ctx.store.base_dir,
                    "diagrams",
                    f"{section['section_id']}-{entry.get('diagram_id')}.svg",
                    svg,
                )
                diagrams.append(
                    {
                        "diagram_id": str(entry.get("diagram_id")),
                        "item_id": str(entry.get("item_id")),
                        "diagram_type": entry.get("diagram_type"),
                        "title": str(entry.get("title", "")),
                        "semantics": entry.get("semantics") or {"nodes": [], "edges": []},
                        "svg_path": str(path),
                        "svg_sha256": media.svg_sha256(svg),
                        "alt_text": str(entry.get("alt_text", "")),
                    }
                )
        content = {"section_id": section["section_id"], "diagrams": diagrams}
        try:
            schemas.validate(content, "diagrams")
        except schemas.SchemaError as exc:
            raise StepFailed(f"diagrams schema: {exc}") from exc
        deps = [r for r in [ctx.rev(f"media_plan:{section['section_id']}")] if r]
        ctx.emit(f"diagrams:{section['section_id']}", "diagrams", content, "diagram-designer", deps=deps)
        notes.append(f"{section['section_id']}: {len(diagrams)} 张 SVG 图示")
    return {"notes": notes}


def _animation_gate_prompt(section: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    return f"""任务：对以下动画候选逐项执行 Educational Animation Gate（教育动画门禁），并给出决策。
候选：{candidates}
判据（criteria）：
- knowledge_function：该动画承担的认知功能；
- temporal_necessity：知识本身是否随时间变化/动态过程/状态转移/因果展开；
- static_alternative：一张静态图是否同样清楚或更清楚（true 表示静态已足够，应拒绝动画）；
- cognitive_load：动画是否增加无关负荷；
- narration_synchrony：画面变化与讲解的同步设计；
- persistence_need：学生是否需要静态终态反复查看；
- generation_feasibility：生成可行性；
- teaching_value：教学价值（不是"更好看"）。
决策只能取 ANIMATION / STATIC / TEXT；若静态替代足够，必须 STATIC（REJECT ANIMATION）。
输出 JSON：{{"decisions": [{{"item_id": "i1", "decision": "STATIC", "criteria": {{"knowledge_function": "...", "temporal_necessity": false, "static_alternative": true, "cognitive_load": "...", "narration_synchrony": "...", "persistence_need": true, "generation_feasibility": "...", "teaching_value": "..."}}, "rationale": "...", "static_alternative_desc": "..."}}]}}"""


def _enforce_animation_decision(decision: dict[str, Any]) -> dict[str, Any]:
    criteria = decision.get("criteria") or {}
    enforced: list[str] = []
    if decision.get("decision") == "ANIMATION":
        if not criteria.get("temporal_necessity", False):
            decision["decision"] = "STATIC"
            enforced.append("temporal_necessity=false → 静态替代")
        elif criteria.get("static_alternative", False):
            decision["decision"] = "STATIC"
            enforced.append("静态替代已足够 → REJECT ANIMATION")
        elif not str(criteria.get("narration_synchrony", "")).strip():
            decision["decision"] = "STATIC"
            enforced.append("缺少讲解同步设计 → 静态替代")
    if enforced:
        decision["enforced"] = "；".join(enforced)
    return decision


def _storyboard_prompt(section: dict[str, Any], approved: list[dict[str, Any]], script: dict[str, Any]) -> str:
    narration = [u.get("text", "") for u in script.get("units", []) if u.get("kind") in ("narration", "case")]
    return f"""任务：为已通过 Animation Gate 的动画候选生成教学分镜（Educational Storyboard）与视频生成提示词。
本节：{section['section_id']} {section['title']}
已批准动画：{approved}
讲解文本：{narration}
要求：
- 每个镜头必须包含：shot_id、item_id、learning_goal、narration（与画面同步的讲解）、visual_state_start、visual_change、visual_state_end、on_screen_text、duration（秒，>0）、knowledge_function、cognitive_load_note、continuity_from、continuity_to、labels；
- 不要求演员表演/服装/电影灯光/情绪镜头；
- static_terminal_state：动画结束后学生需要反复查看的静态终态设计；
- video_prompt：可直接交给外部视频系统的生成提示词（画面与讲解同步、真实证据优先），本系统在渲染前停止。
输出 JSON：{{"shots": [...], "video_prompt": "...", "static_terminal_state": "..."}}"""


def step_storyboard(ctx: PipelineContext) -> dict[str, Any]:
    notes = []
    for section in ctx.sections():
        _check_cancel(ctx)
        plan = ctx.content(f"media_plan:{section['section_id']}") or {}
        candidates = [item for item in plan.get("items", []) if item.get("recommended_medium") == "animation"]
        decisions: list[dict[str, Any]] = []
        if candidates:
            data = _llm_json(ctx, task="animation_gate", prompt=_animation_gate_prompt(section, candidates))
            candidate_ids = {item["item_id"] for item in candidates}
            for decision in data.get("decisions", []):
                if decision.get("item_id") in candidate_ids:
                    decisions.append(_enforce_animation_decision(dict(decision)))
            covered = {d["item_id"] for d in decisions}
            for item in candidates:
                if item["item_id"] not in covered:
                    decisions.append(
                        {
                            "item_id": item["item_id"],
                            "decision": "STATIC",
                            "criteria": {
                                "knowledge_function": item.get("knowledge_function", ""),
                                "temporal_necessity": bool(item.get("temporal_dependency")),
                                "static_alternative": True,
                                "cognitive_load": "未评估",
                                "narration_synchrony": "",
                                "persistence_need": bool(item.get("persistence_need")),
                                "generation_feasibility": "未评估",
                                "teaching_value": "未评估",
                            },
                            "rationale": "模型未对候选给出决策，按静态处理",
                            "static_alternative_desc": "见媒体计划的图示方案",
                            "enforced": "缺失决策 → 静态替代",
                        }
                    )
        decisions_content = {"section_id": section["section_id"], "decisions": decisions}
        try:
            schemas.validate(decisions_content, "animation_decisions")
        except schemas.SchemaError as exc:
            raise StepFailed(f"animation_decisions schema: {exc}") from exc
        deps = [r for r in [ctx.rev(f"media_plan:{section['section_id']}")] if r]
        ctx.emit(
            f"animation_decisions:{section['section_id']}",
            "animation_decisions",
            decisions_content,
            "animation-gate",
            deps=deps,
        )
        approved = [d for d in decisions if d["decision"] == "ANIMATION"]
        storyboard = {
            "section_id": section["section_id"],
            "shots": [],
            "video_prompt": "",
            "static_terminal_state": "",
            "rendered": False,
        }
        if approved:
            script = ctx.content(f"script:{section['section_id']}") or {}
            data = _llm_json(ctx, task="storyboard", prompt=_storyboard_prompt(section, approved, script))
            shots = []
            for index, shot in enumerate(data.get("shots") or [], start=1):
                prepared = dict(shot)
                prepared.setdefault("shot_id", f"s{index}")
                try:
                    prepared["duration"] = float(prepared.get("duration") or 5)
                except (TypeError, ValueError):
                    prepared["duration"] = 5.0
                for key in (
                    "learning_goal",
                    "narration",
                    "visual_state_start",
                    "visual_change",
                    "visual_state_end",
                    "on_screen_text",
                    "knowledge_function",
                    "continuity_from",
                    "cognitive_load_note",
                ):
                    prepared[key] = str(prepared.get(key) or "")
                prepared["labels"] = [str(label) for label in prepared.get("labels") or []]
                prepared.pop("rendered", None)
                shots.append(prepared)
            storyboard["shots"] = shots
            storyboard["video_prompt"] = str(data.get("video_prompt") or "")
            storyboard["static_terminal_state"] = str(data.get("static_terminal_state") or "")
        try:
            schemas.validate(storyboard, "storyboard")
        except schemas.SchemaError as exc:
            raise StepFailed(f"storyboard schema: {exc}") from exc
        json_path = media.write_media_file(
            ctx.store.base_dir,
            "storyboard",
            f"{section['section_id']}.json",
            json.dumps(storyboard, ensure_ascii=False, indent=2),
        )
        media.write_media_file(
            ctx.store.base_dir,
            "storyboard",
            f"{section['section_id']}.md",
            media.storyboard_markdown(storyboard),
        )
        media.write_media_file(
            ctx.store.base_dir,
            "prompts",
            f"{section['section_id']}.txt",
            storyboard.get("video_prompt", ""),
        )
        ctx.emit(
            f"storyboard:{section['section_id']}",
            "storyboard",
            storyboard,
            "storyboard-designer",
            deps=[r for r in [ctx.rev(f"animation_decisions:{section['section_id']}")] if r],
        )
        notes.append(
            f"{section['section_id']}: 动画决策 {len(decisions)} 项（通过 {len(approved)}），分镜 {len(storyboard['shots'])} 镜头，提示词已生成（未渲染）"
        )
    return {"notes": notes}


def _deck_sections(ctx: PipelineContext) -> list[dict[str, Any]]:
    requirements = ctx.content("requirements") or {}
    return requirements.get("sections", [])


def step_evidence_assets(ctx: PipelineContext) -> dict[str, Any]:
    _check_cancel(ctx)
    assets: list[dict[str, Any]] = []
    materials = ctx.content("materials") or {}
    for index, entry in enumerate(materials.get("files", []), start=1):
        assets.append(
            {
                "asset_id": f"mat{index}",
                "source": Path(entry.get("path", "")).name,
                "figure_or_table": "",
                "content_summary": f"用户材料（{entry.get('kind', 'file')}）",
                "clarity": "medium",
                "teaching_relevance": "medium",
                "role": "support",
                "resolution": "n/a",
                "risk": "用户材料引用须标注来源层级，不冒充研究证据",
            }
        )
    for section in _deck_sections(ctx):
        section_id = section["section_id"]
        diagrams_doc = ctx.content(f"diagrams:{section_id}") or {}
        for diagram in diagrams_doc.get("diagrams", []):
            assets.append(
                {
                    "asset_id": diagram["diagram_id"],
                    "source": f"系统生成图示（{section_id}）",
                    "figure_or_table": "diagram",
                    "content_summary": diagram.get("title", ""),
                    "clarity": "high",
                    "teaching_relevance": "high",
                    "role": "primary",
                    "resolution": "vector",
                    "risk": "SVG 已通过安全与结构校验",
                }
            )
    evidence_index = ctx.content("evidence_index") or {}
    for assessment in evidence_index.get("assessments", [])[:10]:
        level = "仅摘要核验" if assessment.get("result") == "SUPPORTED" else f"结果 {assessment.get('result')}"
        assets.append(
            {
                "asset_id": str(assessment.get("assessment_id")),
                "source": str(assessment.get("source_rev")),
                "figure_or_table": "",
                "content_summary": f"证据评估（{assessment.get('result')}）",
                "clarity": "medium",
                "teaching_relevance": "medium",
                "role": "support" if assessment.get("result") == "SUPPORTED" else "unused",
                "resolution": "text",
                "risk": level,
            }
        )
    content = {"assets": assets}
    try:
        schemas.validate(content, "evidence_assets")
    except schemas.SchemaError as exc:
        raise StepFailed(f"evidence_assets schema: {exc}") from exc
    deps = [r for r in [ctx.rev(f"diagrams:{s['section_id']}") for s in _deck_sections(ctx)] if r]
    ctx.emit("evidence_assets", "evidence_assets", content, "evidence-indexer", deps=deps)
    return {"notes": [f"资产索引 {len(assets)} 项"]}


def _slide_plan_prompt(ctx: PipelineContext) -> str:
    requirements = ctx.content("requirements") or {}
    evidence = ctx.content("evidence_assets") or {"assets": []}
    sections_payload = []
    for section in _deck_sections(ctx):
        section_id = section["section_id"]
        design = ctx.content(f"learning_design:{section_id}") or {}
        script = ctx.content(f"script:{section_id}") or {}
        media = ctx.content(f"media_plan:{section_id}") or {}
        sections_payload.append(
            {
                "section_id": section_id,
                "title": section.get("title"),
                "goals": [goal.get("text") for goal in design.get("goals", [])],
                "narration": " ".join(
                    unit.get("text", "") for unit in script.get("units", []) if unit.get("kind") == "narration"
                )[:600],
                "media_items": [
                    {"item_id": item.get("item_id"), "medium": item.get("recommended_medium"), "function": item.get("knowledge_function")}
                    for item in media.get("items", [])
                ],
                "diagrams": [
                    {"diagram_id": diagram.get("diagram_id"), "title": diagram.get("title")}
                    for diagram in (ctx.content(f"diagrams:{section_id}") or {}).get("diagrams", [])
                ],
            }
        )
    return f"""任务：为这套课程生成幻灯片沟通计划（Production Planning Table）。必须先消费教学产物、证据资产与媒体决策，不得从原始材料直接跳到 PPT。
课程：{requirements.get('course')}
证据资产索引：{evidence.get('assets', [])[:20]}
各节教学产物与媒体决策：{sections_payload}
要求：
- 每行一页，包含全部字段：slide、title、narrative_section、communication_task、source_asset、asset_geometry、core_message、layout_archetype（cover/section_title/bullets/diagram/table/closing）、density（low/medium/high）、asset_handling、risk；
- 第 1 页 layout_archetype=cover；最后一页 closing；每节先 section_title，再 2–4 页内容页；
- 图示页使用 layout_archetype=diagram 并填写 diagram_id（只能引用给定图示）；表格页填 table.headers/table.rows；
- points 为页面要点（每页 ≤6 条，单条 ≤40 字）；notes 为讲课备注（取自讲解）；
- 可核验事实性内容在 claim_refs 中填写 Claim 引用（格式 id@vN），禁止编造引用；
- 页面文字禁止出现内部术语（claim、artifact、Gate、Skill、Provider、DAG、QA、run_ 等）。
输出 JSON：{{"rows": [{{"slide": 1, "title": "...", "narrative_section": "...", "communication_task": "...", "source_asset": "", "asset_geometry": "", "core_message": "...", "layout_archetype": "bullets", "density": "medium", "asset_handling": "", "risk": "", "section_id": "sec1", "points": ["..."], "claim_refs": [], "notes": "..."}}]}}"""


def _enforce_slide_plan(ctx: PipelineContext, data: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    rows = sorted(data.get("rows", []), key=lambda row: int(row.get("slide", 0)))
    valid_diagrams = {
        diagram["diagram_id"]
        for section in _deck_sections(ctx)
        for diagram in (ctx.content(f"diagrams:{section['section_id']}") or {}).get("diagrams", [])
    }
    valid_sections = {section["section_id"] for section in _deck_sections(ctx)}
    for index, row in enumerate(rows, start=1):
        row["slide"] = index
        row["layout_archetype"] = _coerce(row.get("layout_archetype"), LAYOUT_ARCHETYPES, "bullets")
        row["density"] = _coerce(row.get("density"), DENSITIES, "medium")
        for key in ("title", "narrative_section", "communication_task", "core_message", "risk"):
            if not isinstance(row.get(key), str):
                row[key] = str(row.get(key) or "")
        if row.get("layout_archetype") == "diagram" and row.get("diagram_id") not in valid_diagrams:
            row["layout_archetype"] = "bullets"
            row["asset_handling"] = (str(row.get("asset_handling", "")) + "；图示缺失，已降级为要点页").lstrip("；")
            notes.append(f"slide{index}: diagram_id 无效，降级为要点页")
        if row.get("section_id") and row["section_id"] not in valid_sections:
            row["section_id"] = ""
        for ref in list(row.get("claim_refs", [])):
            if "@v" not in str(ref) or not ctx.evidence.is_supported(str(ref)):
                row["claim_refs"] = [r for r in row.get("claim_refs", []) if r != ref]
                notes.append(f"slide{index}: 移除未获支持的引用 {ref}")
    data["rows"] = rows
    return notes


def step_slide_plan(ctx: PipelineContext) -> dict[str, Any]:
    _check_cancel(ctx)
    data = _llm_json(ctx, task="slide_plan", prompt=_slide_plan_prompt(ctx))
    notes = _enforce_slide_plan(ctx, data)
    try:
        schemas.validate(data, "slide_plan")
    except schemas.SchemaError as exc:
        raise StepFailed(f"slide_plan schema: {exc}") from exc
    deps = [
        r
        for r in [ctx.rev("evidence_assets")]
        + [ctx.rev(f"script:{s['section_id']}") for s in _deck_sections(ctx)]
        + [ctx.rev(f"diagrams:{s['section_id']}") for s in _deck_sections(ctx)]
        if r
    ]
    ctx.emit("slide_plan", "slide_plan", data, "presentation-planner", deps=deps)
    return {"notes": [f"规划 {len(data.get('rows', []))} 页"] + notes}


def _citation_label(ctx: PipelineContext, claim_ref: str) -> str:
    claim_id, _, version_text = claim_ref.partition("@v")
    try:
        version = int(version_text)
    except ValueError:
        return claim_id
    for assessment in ctx.evidence.assessments(claim_id, version):
        if assessment.get("result") != "SUPPORTED":
            continue
        source_rev = assessment.get("source_rev", "")
        source_id, _, source_version = source_rev.partition("@v")
        try:
            source = ctx.evidence.get_source(source_id, int(source_version))
        except (KeyError, ValueError):
            continue
        title = str(source.get("title", "")).strip()
        if title:
            return title[:18]
    return claim_id


def step_pptx(ctx: PipelineContext) -> dict[str, Any]:
    from . import pptx_builder, pptx_foundry, render

    _check_cancel(ctx)
    requirements = ctx.content("requirements") or {}
    course = str(requirements.get("course", "课程"))
    plan = ctx.content("slide_plan") or {"rows": []}
    diagrams_by_id: dict[str, dict[str, Any]] = {}
    for section in _deck_sections(ctx):
        for diagram in (ctx.content(f"diagrams:{section['section_id']}") or {}).get("diagrams", []):
            diagrams_by_id[diagram["diagram_id"]] = diagram
    deck_rows: list[dict[str, Any]] = []
    for row in plan.get("rows", []):
        prepared = dict(row)
        diagram = diagrams_by_id.get(str(row.get("diagram_id", "")))
        if diagram:
            prepared["diagram_semantics"] = diagram.get("semantics") or {}
        prepared["citation_labels"] = [
            _citation_label(ctx, ref) for ref in row.get("claim_refs", [])
        ]
        deck_rows.append(prepared)
    output_path = Path(ctx.store.base_dir) / "media" / "pptx" / f"{course[:20]}.pptx"
    template_path = (
        ctx.template_path
        if ctx.template_path and str(ctx.template_path).lower().endswith(".pptx")
        else None
    )
    built = pptx_builder.build_deck(
        course=course, plan_rows=deck_rows, output_path=output_path, template_path=template_path
    )
    inspection = pptx_builder.inspect_deck(output_path)
    renderer = render.find_renderer()
    thumbnails: list[str] = []
    render_error = ""
    if renderer:
        try:
            rendered = render.render_pptx_to_png(
                output_path, Path(ctx.store.base_dir) / "media" / "pptx" / "thumbs"
            )
            thumbnails = rendered["thumbnails"]
        except RuntimeError as exc:
            render_error = str(exc)
    delivery = pptx_foundry.delivery_check(output_path) if pptx_foundry.available() else None
    issues: list[dict[str, str]] = []
    checks: list[dict[str, str]] = []
    jargon_hits = inspection["jargon_hits"]
    overflow = inspection["overflow_suspects"]
    checks.append({"check": "开箱可解析", "status": "PASS", "detail": f"{inspection['slide_count']} 页"})
    checks.append(
        {
            "check": "原生可编辑对象",
            "status": "PASS" if built["stats"]["tables"] + built["stats"]["shapes"] > 0 else "FAIL",
            "detail": f"形状 {built['stats']['shapes']}，表格 {built['stats']['tables']}，连接线 {built['stats']['connectors']}",
        }
    )
    checks.append(
        {
            "check": "内部术语",
            "status": "FAIL" if jargon_hits else "PASS",
            "detail": "; ".join(f"{hit['location']}:{hit['token']}" for hit in jargon_hits[:6]),
        }
    )
    checks.append(
        {
            "check": "溢出启发式检查",
            "status": "PASS" if (not overflow or thumbnails) else "NEEDS_REVIEW",
            "detail": "; ".join(f"{item['location']}（{item['chars']} 字 / {item['area_in2']} in²）" for item in overflow[:6])
            + ("；已渲染缩略图供人工复核" if overflow and thumbnails else ""),
        }
    )
    checks.append(
        {
            "check": "真实渲染",
            "status": "PASS" if thumbnails else "NEEDS_REVIEW",
            "detail": (
                f"{renderer}，{len(thumbnails)} 张缩略图"
                if thumbnails
                else (render_error or (renderer or "未检测到 PowerPoint/LibreOffice"))
            ),
        }
    )
    if delivery is not None:
        delivery_status = str(delivery.get("status", "error"))
        checks.append(
            {
                "check": "ppt-foundry 交付检查",
                "status": "PASS" if delivery_status == "passed" else ("FAIL" if delivery_status == "failed" else "NEEDS_REVIEW"),
                "detail": str(pptx_foundry.provenance().get("pinned_version") or "未 pin"),
            }
        )
    for hit in jargon_hits:
        issues.append(
            {
                "location": hit["location"],
                "reason": f"页面出现内部术语：{hit['token']}",
                "next_step": "改写为教学语言",
            }
        )
    for item in overflow:
        if not thumbnails:
            issues.append(
                {
                    "location": item["location"],
                    "reason": f"文本量可能溢出（{item['chars']} 字 / 框面积 {item['area_in2']} in²）",
                    "next_step": "精简文字或拆分页面后重跑",
                }
            )
    if not thumbnails:
        issues.append(
            {
                "location": "renderer",
                "reason": render_error or "无可用渲染器，无法完成渲染级 QA（83.4）",
                "next_step": "安装 LibreOffice 或 PowerPoint 后重跑（或接受草稿）",
            }
        )
    if delivery is not None and str(delivery.get("status")) == "failed":
        issues.append(
            {
                "location": "delivery_check",
                "reason": "ppt-foundry 交付检查未通过",
                "next_step": "查看 pptx_delivery_check 报告并修复",
            }
        )
    status = "FAIL" if (jargon_hits or (delivery is not None and str(delivery.get("status")) == "failed")) else (
        "NEEDS_REVIEW" if (not thumbnails or (overflow and not thumbnails)) else "PASS"
    )
    content = {
        "path": built["path"],
        "sha256": file_hash(output_path),
        "engine": "python-pptx（原生形状/表格/备注）" + (" + 用户模板" if built.get("template_used") else ""),
        "renderer": renderer,
        "template_used": built.get("template_used", ""),
        "thumbnails": thumbnails,
        "delivery_check": delivery or {},
        "families": sorted({str(slide.get("family", "")) for slide in built["slides"]}),
        "stats": built["stats"],
        "slides": built["slides"],
        "qa": {
            "status": status,
            "checks": checks,
            "issues": issues,
            "overflow_suspects": overflow,
            "jargon_hits": jargon_hits,
        },
    }
    try:
        schemas.validate(content, "pptx_deck")
    except schemas.SchemaError as exc:
        raise StepFailed(f"pptx_deck schema: {exc}") from exc
    deps = [
        r
        for r in [ctx.rev("slide_plan")]
        + [ctx.rev(f"diagrams:{s['section_id']}") for s in _deck_sections(ctx)]
        + [ctx.rev(f"storyboard:{s['section_id']}") for s in _deck_sections(ctx)]
        if r
    ]
    ctx.emit("pptx_deck", "pptx_deck", content, "presentation-composer", deps=deps)
    notes = [f"{built['stats']['slides']} 页，QA={status}，渲染器={renderer or '无'}，缩略图={len(thumbnails)}"]
    if built.get("template_used"):
        notes.append("已套用用户 PPTX 模板")
    if delivery is not None:
        notes.append(f"ppt-foundry 交付检查={delivery.get('status')}")
    return {"notes": notes}


def _load_review_prompt(ctx: PipelineContext, section: dict[str, Any]) -> str:
    design = ctx.content(f"learning_design:{section['section_id']}") or {}
    script = ctx.content(f"script:{section['section_id']}") or {}
    media = ctx.content(f"media_plan:{section['section_id']}") or {}
    diagrams = (ctx.content(f"diagrams:{section['section_id']}") or {}).get("diagrams", [])
    diagram_summaries = [
        {"diagram_id": diagram.get("diagram_id"), "title": diagram.get("title")} for diagram in diagrams
    ]
    narration_chars = sum(
        len(unit.get("text", "")) for unit in script.get("units", []) if unit.get("kind") in ("narration", "case")
    )
    return f"""任务：对本节做两项检查——认知负荷分析（Cognitive Load）与双重编码配对（Dual Coding）。
学习目标：{design.get('goals', [])}
媒体选型：{media.get('items', [])}
已生成图示：{diagram_summaries}
讲解正文字数：{narration_chars}
认知负荷分析要求：
- level 取 LOW/MEDIUM/HIGH；说明原因（元素交互性、分散注意、冗余、分段与信号设计）；
- 不得给出伪精确评分（不要用"认知负荷=7.8"这类数字）；
- 不确定处写入 uncertainties；给出 improvements 建议。
双重编码要求：
- 为每个学习目标给出 verbal（讲解要点）与 visual（视觉呈现），visual 必须承担知识功能；
- 若使用已生成图示，填写 diagram_id，并让 visual 描述与该图一致；knowledge_function 取 structure/comparison/sequence/causality/spatial_relation/state_change/hierarchy/example/counterexample；
- pairing_ok 表示"视觉确实承担了知识功能"。
输出 JSON：{{"section_id": "{section['section_id']}", "cognitive_load": {{"level": "MEDIUM", "reasons": ["..."], "uncertainties": ["..."], "improvements": ["..."]}}, "dual_coding": {{"pairings": [{{"goal_ref": "g1", "verbal": "...", "visual": "...", "knowledge_function": "comparison", "diagram_id": "d1", "pairing_ok": true, "note": ""}}]}}}}"""


def step_load_review(ctx: PipelineContext) -> dict[str, Any]:
    notes = []
    for section in ctx.sections():
        _check_cancel(ctx)
        data = _llm_json(ctx, task="load_review", prompt=_load_review_prompt(ctx, section))
        data["section_id"] = section["section_id"]
        load = data.get("cognitive_load") or {}
        for key in ("reasons", "uncertainties", "improvements"):
            if not isinstance(load.get(key), list):
                load[key] = []
        data["cognitive_load"] = load
        dual = data.get("dual_coding") or {}
        valid_diagrams = {
            diagram["diagram_id"]
            for diagram in (ctx.content(f"diagrams:{section['section_id']}") or {}).get("diagrams", [])
        }
        pairings: list[dict[str, Any]] = []
        for pairing in dual.get("pairings", []) or []:
            prepared = dict(pairing)
            diagram_id = str(prepared.get("diagram_id") or "")
            if diagram_id and diagram_id not in valid_diagrams:
                prepared["note"] = (str(prepared.get("note") or "") + "；图示 id 无效，已清除").lstrip("；")
                diagram_id = ""
            prepared["diagram_id"] = diagram_id
            prepared["note"] = str(prepared.get("note") or "")
            prepared["verbal"] = str(prepared.get("verbal") or "")
            prepared["visual"] = str(prepared.get("visual") or "")
            prepared["knowledge_function"] = str(prepared.get("knowledge_function") or "structure")
            prepared["pairing_ok"] = bool(prepared.get("pairing_ok"))
            pairings.append(prepared)
        dual["pairings"] = pairings
        data["dual_coding"] = dual
        try:
            schemas.validate(data, "load_review")
        except schemas.SchemaError as exc:
            raise StepFailed(f"load_review schema: {exc}") from exc
        deps = [
            r
            for r in [
                ctx.rev(f"script:{section['section_id']}"),
                ctx.rev(f"media_plan:{section['section_id']}"),
                ctx.rev(f"diagrams:{section['section_id']}"),
            ]
            if r
        ]
        ctx.emit(f"load_review:{section['section_id']}", "load_review", data, "load-reviewer", deps=deps)
        notes.append(
            f"{section['section_id']}: 认知负荷 {data['cognitive_load']['level']}；双重编码配对 {len(data.get('dual_coding', {}).get('pairings', []))} 组"
        )
    return {"notes": notes}


def _run_overrides(ctx: PipelineContext) -> dict[str, str]:
    """门禁需要看到**本轮 run 产出的全部产物**，而不只是节点契约里声明过的那些。

    `ctx.outputs` 是 Subagent 契约过滤后的视图（`RestrictedContext.outputs`
    只暴露 allowed_inputs | produces）。门禁要读 requirements / teaching_plan /
    learning_design 等大量产物，这些不在 gate-runner 的 requires 里，
    于是 `GateContext.content()` 回退到 `store.accepted_content()`——对本轮
    尚未 accept 的 changeset 恒为 None，检查被静默跳过（Gate False Negative）。
    """
    latest: dict[str, str] = {}
    run_id = getattr(ctx, "run_id", "")
    for artifact in ctx.store.list_artifacts():
        for revision_id in ctx.store.revisions_of(artifact["artifact_id"]):
            try:
                info = ctx.store.get_revision(revision_id)
            except StoreError:
                continue
            if run_id and info.get("produced_by_run") == run_id:
                latest[artifact["artifact_id"]] = revision_id
    latest.update(dict(ctx.outputs))
    return latest


def step_gates(ctx: PipelineContext) -> dict[str, Any]:
    _check_cancel(ctx)
    _skill(ctx, "gate-runner")
    # 只在该步骤开始时扫一次 run 产物：每个 section × 每轮都全量扫会很慢
    _gate_overrides_base = dict(_run_overrides(ctx))
    gate_ctx = gates.GateContext(
        store=ctx.store,
        evidence=ctx.evidence,
        run_id=ctx.run_id,
        environment=ctx.environment,
        overrides=dict(_gate_overrides_base),
    )
    max_rounds = int(config.RULES.get("retries", {}).get("qa_fix_rounds", 2))
    notes: list[str] = []
    for section in ctx.sections():
        artifact_id = f"script:{section['section_id']}"
        if not ctx.rev(artifact_id):
            continue
        rounds = 0
        results: list[dict[str, Any]] = []
        fixable: list[dict[str, Any]] = []
        while True:
            _check_cancel(ctx)
            # 本轮新产出的 revision（含自动修正后的脚本）优先于步骤开始时的快照
            gate_ctx.overrides = {**dict(_gate_overrides_base), **dict(ctx.outputs)}
            results = gates.run_section_gates(gate_ctx, artifact_id)
            fixable = [r for r in results if r["gate_id"] in AUTO_FIX_GATES and r["status"] == "FAIL"]
            if not fixable or rounds >= max_rounds:
                break
            # 自动修正是可选优化，不是交付物：预算不够时应降级（保留 FAIL 待人工/正式导出前处理），
            # 而不是让一个"内容已全部产出、只剩重试"的运行以 BLOCKED 收场。
            try:
                remaining = ctx.store.budget_remaining(ctx.run_id)
            except Exception:  # noqa: BLE001 - 拿不到预算时按原有行为继续
                remaining = None
            if remaining is not None and int(remaining.get("model_calls", 0)) <= 0:
                notes.append(
                    f"{artifact_id}: 剩余模型预算不足，跳过自动修正（保留 {len(fixable)} 个 FAIL 待人工处理）"
                )
                break
            rounds += 1
            try:
                before = (ctx.content(artifact_id) or {}).get("word_count", {}).get("count", 0)
                revised = fix_script(ctx, section, ctx.content(artifact_id), fixable)
                after = revised.get("word_count", {}).get("count", 0)
            except (StepBlocked, StepFailed) as exc:
                notes.append(f"{artifact_id}: 自动修正中止（{exc}）")
                break
            notes.append(f"{artifact_id}: 自动修正第 {rounds} 轮（{before} 字 → {after} 字，{len(fixable)} 个问题）")
        if fixable and rounds >= max_rounds:
            notes.append(f"{artifact_id}: 已达自动修正上限 {max_rounds} 轮，保留问题待人工处理")
        for result in results:
            gate_artifact = gates.gate_artifact_id(result["gate_id"], artifact_id)
            deps = [result["target"]["revision_id"], *result.get("dep_versions", {}).values()]
            ctx.emit(gate_artifact, "gate_result", result, "gate-runner", deps=deps)
            notes.append(f"{artifact_id} {result['gate_id']}={result['status']}")
        gate_ctx.overrides = dict(ctx.outputs)
    return {"notes": notes}


def step_preview(ctx: PipelineContext) -> dict[str, Any]:
    _check_cancel(ctx)
    requirements = ctx.content("requirements") or {}
    all_sections = requirements.get("sections", [])
    gate_ctx = gates.GateContext(
        store=ctx.store, evidence=ctx.evidence, run_id=ctx.run_id, environment=ctx.environment, overrides=dict(ctx.outputs)
    )
    results = gates.latest_gate_results(ctx.store, gate_ctx.overrides)
    lines = [f"# {requirements.get('course', '课程')} 预览（草稿）", ""]
    materials_doc = ctx.content("materials") or {}
    blocked_materials = [entry for entry in materials_doc.get("files", []) if entry.get("sensitive")]
    if blocked_materials:
        lines.append(
            f"*材料警示：{len(blocked_materials)} 个文件含可识别学生资料，已在外部发送前排除（待脱敏后重传）*"
        )
    if ctx.explicit_skills:
        lines.append("*显式调用：" + "、".join(f"/{name}" for name in ctx.explicit_skills) + "*")
    if blocked_materials or ctx.explicit_skills:
        lines.append("")
    for section in all_sections:
        script = ctx.content(f"script:{section['section_id']}") or {}
        wc = script.get("word_count", {})
        artifact_id = f"script:{section['section_id']}"
        section_results = sorted(
            (
                r
                for r in results.values()
                if r.get("run_id") == ctx.run_id and r["target"]["artifact_id"] == artifact_id
            ),
            key=lambda r: r["gate_id"],
        )
        gate_line = "、".join(f"{r['gate_id']}={r['status']}" for r in section_results) or "未运行"
        placeholders = sum(1 for u in script.get("units", []) if u.get("placeholder"))
        lines.append(f"## {section['title']}（{wc.get('count', 0)} 字）")
        lines.append(
            f"*状态：字数 {wc.get('count', 0)}（要求 {wc.get('min', 0)}–{wc.get('max', 0)}，"
            f"{'在范围内' if wc.get('in_range') else '超出范围'}）；待核验占位 {placeholders} 处；门禁：{gate_line}*"
        )
        lines.append("")
        for unit in script.get("units", []):
            kind = unit.get("kind")
            text = unit.get("text", "")
            if kind == "title":
                lines.append(f"### {text}")
            elif kind == "visual":
                lines.append(f"> [画面] {text}（{unit.get('visual_function', '')}）")
            elif kind == "note":
                lines.append(f"> {text}")
            elif kind == "case":
                lines.append(f"**案例**：{text}")
            else:
                prefix = "【待核验】" if unit.get("placeholder") else ""
                lines.append(f"{prefix}{text}")
            lines.append("")
        plan_doc = ctx.content(f"media_plan:{section['section_id']}") or {}
        diagrams_doc = ctx.content(f"diagrams:{section['section_id']}") or {"diagrams": []}
        decisions_doc = ctx.content(f"animation_decisions:{section['section_id']}") or {"decisions": []}
        storyboard_doc = ctx.content(f"storyboard:{section['section_id']}") or {}
        decision_text = (
            "、".join(f"{d.get('item_id')}={d.get('decision')}" for d in decisions_doc.get("decisions", []))
            or "无候选"
        )
        lines.append(
            f"*媒体：图示 {len(diagrams_doc.get('diagrams', []))} 张；动画决策 {decision_text}；"
            f"分镜 {len(storyboard_doc.get('shots', []))} 镜头（未渲染；视频提示词见导出文件）*"
        )
        for diagram in diagrams_doc.get("diagrams", []):
            lines.append(
                f"- 图示《{diagram.get('title', '')}》（{diagram.get('diagram_type', '')}）：{diagram.get('svg_path', '')}"
            )
        lines.append("")
    deck = ctx.content("pptx_deck") or {}
    if deck:
        lines.append(
            f"*PPT：{len(deck.get('slides', []))} 页（QA={deck.get('qa', {}).get('status')}；"
            f"渲染器={deck.get('renderer') or '无'}；原生形状 {deck.get('stats', {}).get('shapes', 0)} 个）*"
        )
        for slide in deck.get("slides", []):
            lines.append(f"- {slide.get('slide_id')}：{slide.get('title', '')}（{slide.get('family', '')}）")
        lines.append("")
    lines.append("## 门禁摘要")
    script_ids = {f"script:{s['section_id']}" for s in all_sections}
    for key, result in sorted(results.items()):
        if result.get("run_id") == ctx.run_id and result["target"]["artifact_id"] in script_ids:
            lines.append(f"- {result['gate_id']} {result['status']} ({result['target']['artifact_id']})")
    content = {"markdown": "\n".join(lines)}
    deps = [r for r in [ctx.rev(f"script:{s['section_id']}") for s in all_sections] if r]
    ctx.emit("preview", "preview", content, "preview-builder", deps=deps)
    return {"notes": ["预览已生成"]}


def step_export(ctx: PipelineContext) -> dict[str, Any]:
    from . import export as export_mod

    _check_cancel(ctx)
    _skill(ctx, "docx-exporter")
    gate_ctx = gates.GateContext(
        store=ctx.store, evidence=ctx.evidence, run_id=ctx.run_id, environment=ctx.environment, overrides=dict(ctx.outputs)
    )
    readiness = gates.export_readiness_with_overrides(gate_ctx)
    mode = "formal" if readiness["ready"] else "draft"
    manifest = export_mod.write_exports(ctx, mode=mode, gate_ctx=gate_ctx)
    export_deps = sorted(
        {
            rev
            for rev in [ctx.rev(f"script:{s['section_id']}") for s in _deck_sections(ctx)]
            + [ctx.rev(f"lesson_plan:{s['section_id']}") for s in _deck_sections(ctx)]
            + [ctx.rev(f"worksheet:{s['section_id']}") for s in _deck_sections(ctx)]
            + [ctx.rev("slide_plan"), ctx.rev("pptx_deck"), ctx.rev("preview")]
            if rev
        }
    )
    info = ctx.emit("export_manifest", "export_manifest", manifest, "docx-exporter", deps=export_deps)
    gate_ctx.overrides["export_manifest"] = info["revision_id"]
    g8 = gates.g8_artifact(gate_ctx, "export_manifest")
    if mode == "formal" and g8["status"] != "PASS":
        manifest = export_mod.write_exports(ctx, mode="draft", gate_ctx=gate_ctx, note="正式导出未通过 G8，已降级为草稿")
        info = ctx.emit("export_manifest", "export_manifest", manifest, "docx-exporter", deps=[info["revision_id"]])
        gate_ctx.overrides["export_manifest"] = info["revision_id"]
        g8 = gates.g8_artifact(gate_ctx, "export_manifest")
        mode = "draft"
    ctx.emit(
        gates.gate_artifact_id("G8", "export_manifest"),
        "gate_result",
        g8,
        "gate-runner",
        deps=[g8["target"]["revision_id"]],
    )
    notes = [f"导出模式：{mode}"]
    if mode == "draft":
        notes.append("未通过全部门禁，已输出草稿（草稿—未通过 QA）")
        notes.extend(readiness["blocking"][:5])
    return {"notes": notes}


def _case_replace_prompt(old_case: dict[str, Any], instruction: str) -> str:
    return f"""任务：按用户修改要求替换一个教学案例，保持教学目标与关联不变。
原案例：{old_case}
用户修改要求：{instruction}
约束：
- 输出同一 case_id 和同一 section_id；
- linked_goal 保持原值；
- 修改说明中若引入新的事实性陈述，必须放入 new_factual_claims，正文不得把未核验内容写成事实；
- 虚构案例保持明确标注。
输出 JSON：{{"case_id": "...", "section_id": "...", "title": "...", "kind": "fictional", "text": "...", "difficulty": "...", "linked_goal": "...", "claim_refs": [], "new_factual_claims": []}}"""


def replace_case(
    ctx: PipelineContext,
    case_artifact_id: str,
    old_case: dict[str, Any],
    instruction: str,
) -> dict[str, Any]:
    _check_cancel(ctx)
    _skill(ctx, "case-designer")
    data = _llm_json(ctx, task="case_replace", prompt=_case_replace_prompt(old_case, instruction))
    data["section_id"] = old_case.get("section_id", data.get("section_id"))
    data.setdefault("case_id", old_case.get("case_id", "case1"))
    data.setdefault("kind", old_case.get("kind", "fictional"))
    data.setdefault("linked_goal", old_case.get("linked_goal", ""))
    new_claims = []
    for text in data.get("new_factual_claims", []) or []:
        record = ctx.evidence.add_claim(str(text), "descriptive", usage="案例")
        new_claims.append(record["revision_id"])
    if new_claims:
        data["claim_refs"] = sorted(set(list(data.get("claim_refs", [])) + new_claims))
    try:
        schemas.validate(data, "case")
    except schemas.SchemaError as exc:
        raise StepFailed(f"case schema: {exc}") from exc
    deps = [r for r in [ctx.rev(f"teaching_plan:{data['section_id']}")] if r]
    return ctx.emit(case_artifact_id, "case", data, "case-designer", deps=deps)


STEPS = {
    "parse_inputs": step_parse_inputs,
    "requirements": step_requirements,
    "learning_design": step_learning_design,
    "claims": step_claims,
    "evidence": step_evidence,
    "teaching_plan": step_teaching_plan,
    "lesson_plans": step_lesson_plans,
    "cases": step_cases,
    "assessments": step_assessments,
    "worksheets": step_worksheets,
    "evidence_topup": step_evidence,
    "scripts": step_scripts,
    "media_plan": step_media_plan,
    "diagrams": step_diagrams,
    "load_review": step_load_review,
    "storyboard": step_storyboard,
    "evidence_assets": step_evidence_assets,
    "slide_plan": step_slide_plan,
    "pptx": step_pptx,
    "gates": step_gates,
    "preview": step_preview,
    "export": step_export,
}


def plan_steps() -> list[dict[str, Any]]:
    spec = [
        ("parse_inputs", "解析模板与材料", []),
        ("requirements", "整理课程要求", ["parse_inputs"]),
        ("learning_design", "设计学习目标与理解难点", ["requirements"]),
        ("claims", "提取待核验心理学结论", ["learning_design"]),
        ("evidence", "核验结论（用户材料/研究来源）", ["claims"]),
        ("teaching_plan", "教学设计（PCK/UDL）", ["evidence"]),
        ("lesson_plans", "写教案", ["teaching_plan"]),
        ("cases", "设计案例", ["lesson_plans"]),
        ("assessments", "设计形成性评价", ["cases"]),
        ("worksheets", "设计学习单", ["assessments"]),
        ("evidence_topup", "补充核验新增事实", ["worksheets"]),
        ("scripts", "生成课程脚本", ["evidence_topup"]),
        ("media_plan", "媒体选型（Media Router）", ["scripts"]),
        ("diagrams", "生成教学图示（SVG）", ["media_plan"]),
        ("load_review", "认知负荷与双重编码检查", ["diagrams"]),
        ("storyboard", "动画决策与教学分镜", ["load_review"]),
        ("evidence_assets", "证据资产索引（Evidence Index）", ["diagrams"]),
        ("slide_plan", "幻灯片沟通计划（Production Planning Table）", ["evidence_assets"]),
        ("pptx", "生成可编辑 PPTX", ["slide_plan"]),
        ("gates", "质量门禁 G1–G7", ["storyboard"]),
        ("preview", "生成预览", ["gates"]),
        ("export", "导出 DOCX/Markdown/PPTX", ["preview"]),
    ]
    if not config.RULES.get("m4", {}).get("pptx", True):
        spec = [step for step in spec if step[0] not in ("evidence_assets", "slide_plan", "pptx")]
    return [
        {
            "step_id": step_id,
            "title": title,
            "kind": "export" if step_id == "export" else ("gate" if step_id == "gates" else "user_visible"),
            "depends_on": deps,
            "required": True,
            "locked": False,
            "disabled": False,
            "status": "PENDING",
        }
        for step_id, title, deps in spec
    ]
