from __future__ import annotations

from typing import Any

SYSTEM = (
    "你是课程任务的语义分析器。只输出 JSON；不要编造心理学事实；"
    "对不确定的信息写入 uncertainties，并给出 0–1 的 confidence。"
)

KNOWLEDGE_TYPES = [
    "concept",
    "distinction",
    "principle",
    "procedure",
    "skill",
    "observation",
    "case_analysis",
    "reflection",
    "attitude",
    "critical_thinking",
    "research_literacy",
    "transfer",
]


def prompt(request: str, deterministic: dict[str, Any], context: dict[str, Any]) -> str:
    return f"""任务：对下面的课程需求做语义分类（只判断“怎么处理”，不判断事实真假）。
用户需求：{request}
确定性提取结果（权威，不得推翻）：{deterministic}
已有产物：{context.get('existing_artifacts', [])}
项目规则：{context.get('project_rules', '')}
知识类型候选：{KNOWLEDGE_TYPES}
delivery_mode 候选：asynchronous_video / live_class / workshop / blended / document_only
research_need 候选：NONE / VERIFY / LITERATURE / DEEP
media_need 候选：NONE / STATIC / DIAGRAM / ANIMATION_CANDIDATE
输出 JSON：
{{"task_intent": "...", "primary_outputs": ["..."], "secondary_outputs": ["..."],
  "delivery_mode": "live_class", "learner_profile": {{"level": "...", "discipline": "...", "prior_knowledge": "..."}},
  "knowledge_types": ["concept"], "research_need": "VERIFY", "media_need": "DIAGRAM",
  "assessment_need": true, "requested_outputs": ["..."],
  "risk_flags": ["..."], "confidence": 0.8, "uncertainties": ["..."]}}"""


def classify(llm: Any, request: str, deterministic: dict[str, Any], context: dict[str, Any]) -> dict[str, Any] | None:
    availability = llm.availability() if hasattr(llm, "availability") else {"available": False}
    if not availability.get("available"):
        return None
    try:
        data = llm.generate_json(task="semantic_route", system=SYSTEM, prompt=prompt(request, deterministic, context))
    except Exception:  # noqa: BLE001 - provider failures fall back to deterministic route
        return None
    if not isinstance(data, dict):
        return None
    for key in ("confidence", "knowledge_types", "requested_outputs"):
        if key not in data:
            return None
    # provider 的用量元数据不是路由结果的一部分（会随 router_result 落成产物）
    data.pop("_usage", None)
    return data
