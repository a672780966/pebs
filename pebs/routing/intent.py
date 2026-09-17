from __future__ import annotations

import re
from typing import Any

from .. import router as legacy_router

OUTPUT_KEYWORDS: dict[str, list[str]] = {
    "script": ["讲稿", "脚本", "录课", "讲解稿", "授课稿"],
    "lesson_plan": ["教案", "教学方案", "课时计划"],
    "worksheet": ["学习单", "练习单", "worksheet"],
    "case": ["案例", "个案"],
    "assessment": ["评价", "测验", "题目", "课堂提问", "形成性评价"],
    "pptx": ["ppt", "幻灯片", "演示文稿"],
    "diagram": ["图示", "流程图", "概念图", "示意图"],
    "storyboard": ["分镜", "故事板"],
}

DELIVERY_HINTS: list[tuple[str, list[str]]] = [
    ("live_class", ["现场课", "线下课", "课堂", "90分钟", "面授", "一节课"]),
    ("asynchronous_video", ["录课", "在线课程", "网课", "视频课"]),
    ("workshop", ["工作坊", "研修", "培训工作坊"]),
    ("document_only", ["只要文档", "仅文档", "文档即可", "不需要上课", "只出文档"]),
]

NO_ANIMATION_PATTERNS = [r"不(要|需要|含|用)?动画", r"无动画", r"不需要\s*动画", r"不要\s*动画"]
NO_PPT_PATTERNS = [r"不(要|需要|用)?\s*ppt", r"不需要\s*ppt", r"不含\s*ppt", r"不要\s*幻灯片"]
NO_SCRIPT_PATTERNS = [r"不需要\s*(录课)?\s*脚本", r"不要\s*(录课)?\s*脚本", r"不含\s*脚本", r"不用\s*(录课)?\s*脚本"]
NEEDS_PPT_PATTERNS = [r"(需要|生成|做|产出|输出)\s*ppt", r"幻灯片", r"演示文稿"]
CASE_PATTERN = re.compile(r"至少\s*(\d+)\s*个案例|包含案例|每个?案例|有案例")
INTERACTION_PATTERN = re.compile(r"互动|课堂活动|讨论|提问环节")
AUDIT_PATTERN = re.compile(r"审核|审查|复核|查错|理论错误|事实错误|检查.{0,6}(错误|问题)")
PRODUCTION_PATTERN = re.compile(r"写|生成|制作|设计|做一节|产出一节|开发")
DISALLOWED_PATTERNS = [r"禁用词[:：]\s*([^\n。；]+)", r"不要出现[:：]?\s*([^\n。；]{2,20})", r"避免使用[:：]?\s*([^\n。；]{2,20})"]
QUOTE_PATTERN = re.compile(r"[「“\"]([^」”\"]{1,20})[」”\"]")


def _first_match(patterns: list[str], text: str) -> bool:
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def extract_deterministic(
    request: str,
    *,
    template_spec: dict[str, Any] | None = None,
    materials: list[str] | None = None,
    explicit_skills: list[str] | None = None,
) -> dict[str, Any]:
    text = request or ""
    lowered = text.lower()
    word_min, word_max = legacy_router.parse_word_range(text)
    sections = legacy_router.parse_section_titles(text)

    requested: list[str] = []
    for output, keywords in OUTPUT_KEYWORDS.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            requested.append(output)

    needs_ppt = _first_match(NEEDS_PPT_PATTERNS, text)
    no_ppt = _first_match(NO_PPT_PATTERNS, text)
    if no_ppt:
        needs_ppt = False
    no_animation = _first_match(NO_ANIMATION_PATTERNS, text)
    if needs_ppt and not no_ppt and "pptx" not in requested:
        requested.append("pptx")
    if no_ppt:
        requested = [item for item in requested if item != "pptx"]
        no_animation = True
    no_script = _first_match(NO_SCRIPT_PATTERNS, text)
    if no_script:
        requested = [item for item in requested if item != "script"]

    required_components: list[str] = []
    if CASE_PATTERN.search(text):
        required_components.append("case")
    if INTERACTION_PATTERN.search(text):
        required_components.append("interaction")
    if "animation" in text and not no_animation:
        required_components.append("animation")
    if "diagram" in requested:
        required_components.append("diagram")
    if no_script:
        required_components = [item for item in required_components if item != "animation"]
        no_animation = True

    disallowed: list[str] = []
    for pattern in DISALLOWED_PATTERNS:
        for match in re.finditer(pattern, text):
            value = match.group(1).strip()
            if value:
                disallowed.append(value)

    terminology = [value for value in QUOTE_PATTERN.findall(text) if len(value) <= 12]
    if template_spec:
        terminology.extend(template_spec.get("terminology_rules", []))
    terminology = sorted(set(terminology))

    delivery_mode = "document_only"
    for mode, hints in DELIVERY_HINTS:
        if any(hint.lower() in lowered for hint in hints):
            delivery_mode = mode
            break

    language = "zh-CN" if re.search(r"[\u4e00-\u9fff]", text) else "en"
    audit_only = bool(AUDIT_PATTERN.search(text)) and not PRODUCTION_PATTERN.search(text)

    return {
        "word_min": word_min,
        "word_max": word_max,
        "sections": sections,
        "requested_outputs": sorted(set(requested)),
        "required_components": sorted(set(required_components)),
        "disallowed": disallowed,
        "terminology": terminology,
        "no_animation": bool(no_animation),
        "no_ppt": bool(no_ppt),
        "no_script": bool(no_script),
        "needs_ppt": bool(needs_ppt),
        "delivery_mode": delivery_mode,
        "language": language,
        "explicit_skills": sorted(set(explicit_skills or [])),
        "template_present": bool(template_spec and template_spec.get("kind") not in (None, "none")),
        "material_count": len(materials or []),
        "audit_only": audit_only,
    }
