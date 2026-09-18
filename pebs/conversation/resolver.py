from __future__ import annotations

import re
from typing import Any

KIND_HINTS: list[tuple[str, list[str]]] = [
    ("case", ["案例", "个案"]),
    ("script", ["脚本", "讲稿", "讲解"]),
    ("storyboard", ["动画", "分镜"]),
    ("diagrams", ["图示", "流程图", "概念图"]),
    ("pptx_deck", ["ppt", "幻灯片"]),
    ("lesson_plan", ["教案", "活动", "教学环节"]),
    ("assessment", ["评价", "题目", "提问"]),
    ("worksheet", ["学习单", "练习"]),
]

ORDINAL_CN = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _section_ordinals(message: str) -> list[int]:
    found: list[int] = []
    for match in re.finditer(r"第\s*([0-9]+|[一二两三四五六七八九十])\s*(?:节|课)", message):
        raw = match.group(1)
        found.append(int(raw) if raw.isdigit() else ORDINAL_CN.get(raw, 0))
    for match in re.finditer(r"(?:^|[^0-9])([0-9]+)\s*节", message):
        found.append(int(match.group(1)))
    return sorted({value for value in found if value})


def _activity_ordinals(message: str) -> list[int]:
    found: list[int] = []
    for match in re.finditer(r"第\s*([0-9]+|[一二两三四五六七八九十])\s*(?:个)?活动", message):
        raw = match.group(1)
        found.append(int(raw) if raw.isdigit() else ORDINAL_CN.get(raw, 0))
    for match in re.finditer(r"活动\s*([0-9]+)", message):
        found.append(int(match.group(1)))
    return sorted({value for value in found if value})


def _slide_numbers(message: str) -> list[int]:
    return sorted({int(match.group(1)) for match in re.finditer(r"第\s*(\d+)\s*页", message)})


def _rank_label(message: str, labels: list[str]) -> str | None:
    if not labels:
        return None
    if re.search(r"最后(一)?个|末(一)?个", message):
        return labels[-1]
    if re.search(r"第一?个|首个", message):
        return labels[0]
    return None


def _numbered_refs(message: str) -> list[str]:
    """M6 §34：编号小节引用（8.1 / 8.2 …），用于四节课程的自然语言定位。"""
    return sorted({match.group(1) for match in re.finditer(r"(?<![\d.])(\d{1,2}\.\d{1,2})(?![\d.])", message)})


def _match_section_by_label(message: str, sections: list[dict[str, Any]]) -> str | None:
    for label in _numbered_refs(message):
        for section in sections:
            title = str(section.get("title") or "")
            if title.startswith(label):
                return section["section_id"]
    return None


def _match_section_by_title(message: str, sections: list[dict[str, Any]], min_length: int = 3) -> str | None:
    best: tuple[int, str] | None = None
    for section in sections:
        title = str(section.get("title") or "")
        if len(title) >= min_length and title in message:
            if best is None or len(title) > best[0]:
                best = (len(title), section["section_id"])
    return best[1] if best else None


def _match_section_by_text(message: str, script_units: list[dict[str, Any]], min_length: int = 4) -> str | None:
    from difflib import SequenceMatcher

    best: tuple[int, str] | None = None
    for unit in script_units:
        text = str(unit.get("text", ""))
        section_id = unit.get("section_id")
        if not text or not section_id:
            continue
        match = SequenceMatcher(None, message, text).find_longest_match(0, len(message), 0, len(text))
        if match.size >= min_length and (best is None or match.size > best[0]):
            best = (match.size, section_id)
    return best[1] if best else None


def resolve(
    message: str,
    intent: dict[str, Any],
    *,
    sections: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    slides: list[dict[str, Any]] | None = None,
    script_units: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved: dict[str, Any] = {
        "section_ids": [],
        "artifact_ids": [],
        "slide_ids": [],
        "match_reasons": [],
        "unmapped": [],
    }
    ordinals = _section_ordinals(message)
    preserve_sections = {int(index) for index in (intent.get("preserve_sections") or [])}
    target_ordinals = [index for index in ordinals if index not in preserve_sections]
    section_ids: list[str] = []
    for index in target_ordinals:
        if 1 <= index <= len(sections):
            section_ids.append(sections[index - 1]["section_id"])
            resolved["match_reasons"].append(f"第{index}节 → {sections[index - 1]['section_id']}")
        else:
            resolved["unmapped"].append(f"第{index}节")
    for candidate in intent.get("targets", {}).get("section_ids", []):
        if candidate in {section["section_id"] for section in sections}:
            section_ids.append(candidate)

    if not section_ids:
        labelled = _match_section_by_label(message, sections)
        if labelled:
            section_ids.append(labelled)
            resolved["match_reasons"].append(f"编号小节匹配 → {labelled}")
    if not section_ids:
        titled = _match_section_by_title(message, sections)
        if titled:
            section_ids.append(titled)
            resolved["match_reasons"].append(f"章节标题匹配 → {titled}")
    if not section_ids and script_units:
        matched_section = _match_section_by_text(message, script_units)
        if matched_section:
            section_ids.append(matched_section)
            resolved["match_reasons"].append(f"文本匹配 → {matched_section}")
    if not section_ids and not ordinals and len(sections) == 1:
        section_ids = [sections[0]["section_id"]]
        resolved["match_reasons"].append("单章节项目默认目标")

    resolved["section_ids"] = sorted(set(section_ids))

    kinds: list[str] = []
    for kind, hints in KIND_HINTS:
        if any(hint in message.lower() for hint in hints):
            kinds.append(kind)
    for kind in intent.get("targets", {}).get("artifact_ids", []):
        if kind and kind not in kinds:
            kinds.append(kind)
    resolved["artifact_kinds"] = kinds
    activity_ordinals = _activity_ordinals(message)
    llm_activity = intent.get("targets", {}).get("activity_index")
    if isinstance(llm_activity, int) and llm_activity not in activity_ordinals:
        activity_ordinals.append(llm_activity)
    resolved["activity_index"] = activity_ordinals or None

    if ordinals and not resolved["section_ids"]:
        resolved["match_reasons"].append("序数越界，未定位到章节；不猜测其它章节")
        return resolved

    scope_sections = resolved["section_ids"] or [section["section_id"] for section in sections]
    if resolved["activity_index"] and not resolved["section_ids"] and "lesson_plan" in kinds and sections:
        scope_sections = [sections[0]["section_id"]]
        resolved["match_reasons"].append("活动序数 → 默认定位第 1 节教案")
    candidates: list[tuple[str, str]] = []
    for artifact in artifacts:
        if not artifact.get("accepted_rev"):
            continue
        artifact_id = artifact["artifact_id"]
        artifact_type = artifact["artifact_type"]
        if artifact_type not in kinds:
            continue
        if ":" in artifact_id:
            if any(section_id in artifact_id.split(":")[1:] for section_id in scope_sections):
                candidates.append((artifact_id, artifact_type))
        else:
            candidates.append((artifact_id, artifact_type))
    labels = [artifact_id for artifact_id, _ in candidates]
    ranked = _rank_label(message, labels)
    artifact_ids = [ranked] if ranked else [artifact_id for artifact_id, _ in candidates]
    resolved["artifact_ids"] = sorted(set(artifact_ids))

    slide_numbers = _slide_numbers(message)
    for number in intent.get("targets", {}).get("slide_ids", []):
        if isinstance(number, int):
            slide_numbers.append(number)
    valid_slides = {int(slide.get("slide", 0)) for slide in (slides or [])}
    resolved["slide_ids"] = sorted({number for number in slide_numbers if number in valid_slides})
    for number in slide_numbers:
        if number not in valid_slides:
            resolved["unmapped"].append(f"第{number}页")

    if not resolved["artifact_ids"] and resolved["slide_ids"]:
        resolved["artifact_ids"].append("slide_plan")
        resolved["match_reasons"].append("幻灯片页码 → slide_plan")
    if not resolved["artifact_ids"] and resolved["section_ids"] and not kinds:
        resolved["artifact_ids"].extend(
            [f"script:{section_id}" for section_id in resolved["section_ids"]]
        )
        resolved["match_reasons"].append("仅指定章节 → 默认定位该节脚本")
    return resolved
