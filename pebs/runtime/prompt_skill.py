from __future__ import annotations

import json
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


class PromptSkillExecutor:
    def __init__(self, llm: Any, *, loader=skill_loader.load):
        self.llm = llm
        self.loader = loader

    def execute(self, ctx: Any, node: dict[str, Any], *, skill_record: dict[str, Any]) -> dict[str, Any]:
        name = skill_record.get("name")
        loaded = self.loader(name)
        instructions = skill_loader.instruction_text(loaded)
        schema_name, artifact_type = skill_loader.schema_for(skill_record)
        artifacts: dict[str, Any] = {}
        for artifact_type_name in skill_loader.declared_artifact_types(skill_record):
            ids = ctx.artifact_ids_of_type(artifact_type_name) if hasattr(ctx, "artifact_ids_of_type") else []
            contents = {artifact_id: ctx.content(artifact_id) for artifact_id in ids}
            contents = {key: value for key, value in contents.items() if value is not None}
            if not contents:
                continue
            artifacts[artifact_type_name] = contents if len(contents) > 1 else next(iter(contents.values()))
        skill_context = context_mod.build_context(
            task=node.get("reason") or f"执行外部 Skill：{name}",
            skill_record=skill_record,
            artifacts=artifacts,
            project_rules=getattr(ctx, "project_rules", "") or "",
            constraints=node.get("constraints") or {},
            output_schema=loaded.output_schema,
            extra_allowed=["materials"] if skill_record.get("filesystem") == "project_inputs_read" else [],
        )
        node["_context_report"] = context_mod.context_report(skill_context)
        prompt = (
            f"Skill 指令：\n{instructions}\n\n"
            f"任务与最小上下文（只包含该 Skill 被允许消费的产物）：\n"
            f"{json.dumps({k: v for k, v in skill_context.items() if not k.startswith('_')}, ensure_ascii=False)[:12000]}\n\n"
            f"输出要求：JSON 对象；artifact 类型={artifact_type}；canonical schema={schema_name or '无'}"
        )
        availability = self.llm.availability() if hasattr(self.llm, "availability") else {"available": False}
        if not availability.get("available"):
            from ..pipeline import StepBlocked

            raise StepBlocked("LLM Provider 不可用：" + "；".join(availability.get("reasons", [])))
        data = self.llm.generate_json(task=f"external_skill:{name}", system=SYSTEM, prompt=prompt)
        data = _with_section_defaults(ctx, node, artifact_type, data)
        errors = _validate_with_policies(data, skill_record=skill_record, artifact_type=artifact_type, inline_schema=loaded.output_schema)
        if errors:
            repair_prompt = (
                prompt
                + "\n\n上一次输出未通过校验，请修正后重新输出完整 JSON：\n- "
                + "\n- ".join(errors[:6])
            )
            data = self.llm.generate_json(task=f"external_skill_repair:{name}", system=SYSTEM, prompt=repair_prompt)
            data = _with_section_defaults(ctx, node, artifact_type, data)
            errors = _validate_with_policies(data, skill_record=skill_record, artifact_type=artifact_type, inline_schema=loaded.output_schema)
            if errors:
                raise SkillExecutionFailed(
                    f"外部 Skill 输出两次均未通过 Schema 校验：{'；'.join(errors[:3])}"
                )
        return data


def _with_section_defaults(ctx: Any, node: dict[str, Any], artifact_type: str | None, data: dict[str, Any]) -> dict[str, Any]:
    if artifact_type in ("teaching_plan", "lesson_plan", "assessment", "worksheet", "case", "learning_design", "script"):
        if not data.get("section_id"):
            data["section_id"] = node.get("section_id") or (ctx.sections()[0]["section_id"] if ctx.sections() else "")
        if artifact_type in ("lesson_plan", "worksheet") and not data.get("title"):
            section_id = data.get("section_id")
            match = next((section for section in ctx.sections() if section["section_id"] == section_id), None)
            data["title"] = (match or {}).get("title", "")
    return data


def execute_prompt_skill(ctx: Any, node: dict[str, Any], skill_record: dict[str, Any], llm: Any) -> dict[str, Any]:
    executor = PromptSkillExecutor(llm)
    return executor.execute(ctx, node, skill_record=skill_record)
