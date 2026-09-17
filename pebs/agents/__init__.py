from __future__ import annotations

from typing import Any

from .base import (
    AgentBrief,
    AgentContract,
    AgentContractError,
    IsolationViolation,
    RestrictedContext,
    Subagent,
)
from .kinds import AGENT_NAMES, CURRICULUM, MEDIA, PEDAGOGY, QA, RESEARCH


class ResearchAgent(Subagent):
    name = RESEARCH
    kinds = RESEARCH
    domain = "research"
    description = "只生产 Evidence：按 claims 检索、核验并产出 evidence_index（仅摘要来源必须标注限制）"
    default_inputs = ("claims_set", "materials", "project_rules")
    default_produces = ("evidence_index",)


class CurriculumAgent(Subagent):
    name = CURRICULUM
    kinds = CURRICULUM
    domain = "curriculum"
    description = "只生产课程结构与要求：template_spec / requirements / learning_design"
    default_inputs = ("template_spec", "materials", "learning_design", "requirements")
    default_produces = ("requirements", "learning_design", "template_spec")


class PedagogyAgent(Subagent):
    name = PEDAGOGY
    kinds = PEDAGOGY
    domain = "pedagogy"
    description = "消费 Learning Design 与已支持证据，产出教学计划 / 教案 / 案例 / 脚本"
    default_inputs = ("learning_design", "evidence_index", "claims_set", "requirements", "teaching_plan")
    default_produces = ("teaching_plan", "lesson_plan", "case", "assessment", "worksheet", "script")


class MediaAgent(Subagent):
    name = MEDIA
    kinds = MEDIA
    domain = "media"
    description = "只决定 text / diagram / animation 与媒体计划，不允许生成视频或音频"
    default_inputs = ("teaching_plan", "script", "media_plan", "storyboard")
    default_produces = ("media_plan", "diagrams", "load_review", "animation_decisions", "storyboard")


class QAReviewAgent(Subagent):
    name = QA
    kinds = QA
    domain = "qa"
    description = "只能 flag / explain / propose correction：运行门禁、证据索引、预览与导出清单"
    default_inputs = ("script", "requirements", "evidence_index", "gate_result", "presentation_plan")
    default_produces = ("gate_result", "evidence_assets", "slide_plan", "pptx_deck", "preview", "export_manifest")


AGENT_CLASSES: tuple[type[Subagent], ...] = (
    ResearchAgent,
    CurriculumAgent,
    PedagogyAgent,
    MediaAgent,
    QAReviewAgent,
)

_AGENT_BY_NAME = {agent.name: agent for agent in AGENT_CLASSES}
_AGENT_BY_DOMAIN = {agent.domain: agent for agent in AGENT_CLASSES}
_DOMAIN_ALIASES = {
    "education": CURRICULUM,
    "psychology": RESEARCH,
    "presentation": QA,
}


def default_agents(llm: Any = None) -> dict[str, Subagent]:
    return {agent.name: agent(llm) for agent in AGENT_CLASSES}


def for_skill(record: dict[str, Any], llm: Any = None) -> Subagent:
    """按 Registry 契约中的 agent 字段选择 Subagent（Registry 是唯一事实源）。"""
    declared = str(record.get("agent") or "")
    agent_class = _AGENT_BY_NAME.get(declared)
    if agent_class is None:
        domain = str(record.get("domain") or "")
        agent_class = _AGENT_BY_DOMAIN.get(domain) or _AGENT_BY_NAME.get(
            _DOMAIN_ALIASES.get(domain, ""), CurriculumAgent
        )
    return agent_class(llm)


__all__ = [
    "AGENT_CLASSES",
    "AGENT_NAMES",
    "AgentBrief",
    "AgentContract",
    "AgentContractError",
    "CurriculumAgent",
    "IsolationViolation",
    "MediaAgent",
    "PedagogyAgent",
    "QAReviewAgent",
    "ResearchAgent",
    "RestrictedContext",
    "Subagent",
    "default_agents",
    "for_skill",
]
