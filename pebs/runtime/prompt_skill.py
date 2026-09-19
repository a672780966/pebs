from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import context as context_mod
from . import skill_loader
from .result import validate_result
from .skill_loader import SkillRuntimeBlocked


def _validate_with_policies(data: Any, *, skill_record: dict[str, Any], artifact_type: str | None, inline_schema: dict[str, Any] | None) -> list[str]:
    from .. import policies

    errors = validate_result(data, artifact_type=artifact_type, inline_schema=inline_schema)
    errors.extend(policies.apply_output_policies(skill_record, data))
    return errors


class SkillExecutionFailed(Exception):
    pass


SYSTEM = "你是被 PEBS 调用的外部教育 Skill。严格按给定输出 Schema 只输出 JSON，不编造研究结论或引用。"


def _condense_schema(schema: dict[str, Any], *, max_chars: int = 3500) -> str:
    """把 canonical JSON Schema 压缩成"必须满足的字段"摘要，供外部 Skill 提示使用。

    M6 生产修正：此前 prompt 只给出 schema 名称，真实模型因此产出缺少必需字段的 JSON
    （例如 media_plan 的 knowledge_function / temporal_dependency），两次校验失败即 FAILED。
    """
    def describe(node: dict[str, Any]) -> Any:
        if not isinstance(node, dict):
            return {}
        info: dict[str, Any] = {}
        if "type" in node:
            info["type"] = node["type"]
        if "enum" in node:
            info["enum"] = node["enum"]
        if node.get("required"):
            info["required"] = node["required"]
        properties = node.get("properties")
        if isinstance(properties, dict):
            info["properties"] = {key: describe(value) for key, value in properties.items()}
        items = node.get("items")
        if isinstance(items, dict):
            info["items"] = describe(items)
        return info

    condensed = describe(schema)
    text = json.dumps(condensed, ensure_ascii=False)
    return text[:max_chars]


def canonical_schema_text(artifact_type: str | None) -> str:
    if not artifact_type:
        return ""
    from .. import config, registry

    schema_name = registry.ARTIFACT_SCHEMAS.get(artifact_type)
    if not schema_name:
        return ""
    path = Path(config.SCHEMA_DIR) / f"{schema_name}.schema.json"
    if not path.exists():
        return ""
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return _condense_schema(schema)


class PromptSkillExecutor:
    def __init__(self, llm: Any, *, loader=skill_loader.load, store: Any = None):
        self.llm = llm
        self.loader = loader
        # 预算核算由受信任的 runtime 持有 store（RestrictedContext 不允许 Skill 触碰 store）
        self.store = store

    def execute(self, ctx: Any, node: dict[str, Any], *, skill_record: dict[str, Any]) -> dict[str, Any]:
        """执行外部 Prompt Skill。

        M6 修正：分节产物（artifact_ids 含 {section_id}）必须**分节调用**并逐节校验；
        此前一次性调用再把同一 payload 复制到每一节，导致各节内容完全相同（§17 A/B 发现）。
        """
        name = skill_record.get("name")
        loaded = self.loader(name)
        instructions = skill_loader.instruction_text(loaded)
        schema_name, artifact_type = skill_loader.schema_for(skill_record)
        template = str(((skill_record.get("handler") or {}).get("artifact_ids") or {}).get(artifact_type) or "")
        sections = ctx.sections() if hasattr(ctx, "sections") else []
        if artifact_type and "{section_id}" in template and len(sections) > 1:
            payloads: dict[str, Any] = {}
            for section in sections:
                payloads[section["section_id"]] = self._execute_one(
                    ctx,
                    node,
                    skill_record=skill_record,
                    loaded=loaded,
                    instructions=instructions,
                    schema_name=schema_name,
                    artifact_type=artifact_type,
                    section=section,
                )
            return {"_sections": payloads, "_section_scoped": True}
        return self._execute_one(
            ctx,
            node,
            skill_record=skill_record,
            loaded=loaded,
            instructions=instructions,
            schema_name=schema_name,
            artifact_type=artifact_type,
            section=sections[0] if sections else None,
        )

    def _execute_one(
        self,
        ctx: Any,
        node: dict[str, Any],
        *,
        skill_record: dict[str, Any],
        loaded: Any,
        instructions: str,
        schema_name: str | None,
        artifact_type: str | None,
        section: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        name = skill_record.get("name")
        artifacts: dict[str, Any] = {}
        for artifact_type_name in skill_loader.declared_artifact_types(skill_record):
            ids = ctx.artifact_ids_of_type(artifact_type_name) if hasattr(ctx, "artifact_ids_of_type") else []
            contents = {artifact_id: ctx.content(artifact_id) for artifact_id in ids}
            contents = {key: value for key, value in contents.items() if value is not None}
            if not contents:
                continue
            artifacts[artifact_type_name] = contents if len(contents) > 1 else next(iter(contents.values()))
        constraints = dict(node.get("constraints") or {})
        if section:
            constraints["section_id"] = section["section_id"]
            constraints["section_title"] = section.get("title", "")
        skill_context = context_mod.build_context(
            task=node.get("reason") or f"执行外部 Skill：{name}",
            skill_record=skill_record,
            artifacts=artifacts,
            project_rules=getattr(ctx, "project_rules", "") or "",
            constraints=constraints,
            output_schema=loaded.output_schema,
            extra_allowed=["materials"] if skill_record.get("filesystem") == "project_inputs_read" else [],
        )
        node["_context_report"] = context_mod.context_report(skill_context)
        schema_text = canonical_schema_text(artifact_type)
        schema_block = (
            "\nPEBS canonical schema（必须满足的字段；缺字段会直接判定失败）：\n" + schema_text + "\n"
            if schema_text
            else ""
        )
        section_line = (
            f"\n本节：{section['section_id']} {section.get('title', '')}（只处理本节；不要复用其它节的内容）\n"
            if section
            else ""
        )
        prompt = (
            f"Skill 指令：\n{instructions}\n\n"
            f"任务与最小上下文（只包含该 Skill 被允许消费的产物）：\n"
            f"{json.dumps({k: v for k, v in skill_context.items() if not k.startswith('_')}, ensure_ascii=False)[:12000]}\n"
            f"{section_line}\n"
            f"输出要求：JSON 对象；artifact 类型={artifact_type}；canonical schema={schema_name or '无'}"
            f"{schema_block}"
        )
        availability = self.llm.availability() if hasattr(self.llm, "availability") else {"available": False}
        if not availability.get("available"):
            from ..pipeline import StepBlocked

            raise StepBlocked("LLM Provider 不可用：" + "；".join(availability.get("reasons", [])))
        data = self._generate(ctx, task=f"external_skill:{name}", prompt=prompt)
        scoped_node = dict(node)
        if section:
            scoped_node["section_id"] = section["section_id"]
        data = _with_section_defaults(ctx, scoped_node, artifact_type, data)
        errors = _validate_with_policies(data, skill_record=skill_record, artifact_type=artifact_type, inline_schema=loaded.output_schema)
        if errors:
            repair_prompt = (
                prompt
                + "\n\n上一次输出未通过校验，请修正后重新输出完整 JSON：\n- "
                + "\n- ".join(errors[:6])
            )
            data = self._generate(ctx, task=f"external_skill_repair:{name}", prompt=repair_prompt)
            data = _with_section_defaults(ctx, scoped_node, artifact_type, data)
            errors = _validate_with_policies(data, skill_record=skill_record, artifact_type=artifact_type, inline_schema=loaded.output_schema)
            if errors:
                raise SkillExecutionFailed(
                    f"外部 Skill 输出两次均未通过 Schema 校验：{'；'.join(errors[:3])}"
                )
            # §35：Schema Repair Rate 必须可观测——修复过一次才算，且要能写进 trace。
            # 记在 node 上（不是 executor 实例）以免并行节点互相污染。
            node["_schema_repairs"] = int(node.get("_schema_repairs", 0) or 0) + 1
        return data

    def _generate(self, ctx: Any, *, task: str, prompt: str) -> dict[str, Any]:
        """外部 Skill 的每次模型调用都必须计入预算（M6 §31/§35 成本核算）。"""
        store = self.store
        run_id = str(getattr(ctx, "run_id", "") or "")
        if store is not None and run_id and hasattr(store, "check_budget"):
            from ..store import BudgetExceeded

            try:
                store.check_budget(run_id, model_calls=1)
            except BudgetExceeded as exc:
                from .. import pipeline

                raise pipeline.StepBlocked(f"预算耗尽：{exc}") from exc
            store.bump_calls(run_id, 1)
        data = self.llm.generate_json(task=task, system=SYSTEM, prompt=prompt)
        # provider 会把用量元数据塞进返回体；内置路径在 pipeline 里已剔除，
        # 外部 Skill 路径若不剔除，`_usage` 就会被 emit 成教学产物的一部分。
        if isinstance(data, dict):
            data.pop("_usage", None)
        return data


def _with_section_defaults(ctx: Any, node: dict[str, Any], artifact_type: str | None, data: dict[str, Any]) -> dict[str, Any]:
    section_scoped = (
        "teaching_plan",
        "lesson_plan",
        "assessment",
        "worksheet",
        "case",
        "learning_design",
        "script",
        "media_plan",
        "load_review",
        "diagrams",
        "storyboard",
        "evidence_assets",
    )
    if artifact_type in section_scoped:
        if not data.get("section_id"):
            data["section_id"] = node.get("section_id") or (ctx.sections()[0]["section_id"] if ctx.sections() else "")
        if artifact_type in ("lesson_plan", "worksheet") and not data.get("title"):
            section_id = data.get("section_id")
            match = next((section for section in ctx.sections() if section["section_id"] == section_id), None)
            data["title"] = (match or {}).get("title", "")
    return data


def execute_prompt_skill(ctx: Any, node: dict[str, Any], skill_record: dict[str, Any], llm: Any) -> dict[str, Any]:
    store = None
    try:  # RestrictedContext 会拦截 store；只有真实 PipelineContext 才用于预算核算
        store = getattr(ctx, "store", None)
    except Exception:  # noqa: BLE001 - 受限上下文下不做核算，仍可执行
        store = None
    executor = PromptSkillExecutor(llm, store=store)
    return executor.execute(ctx, node, skill_record=skill_record)
