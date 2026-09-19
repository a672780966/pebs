from __future__ import annotations

import re
from typing import Any

INTENT_PRIORITY: list[tuple[str, list[str]]] = [
    ("remove", [r"删掉|删除|去掉|移除"]),
    ("shorten", [r"缩短|精简|压缩|太长了|太长"]),
    ("expand", [r"扩写|补充细节|写详细|展开|增加内容"]),
    ("restyle", [r"风格|语气|文风|更口语|更正式"]),
    ("regenerate", [r"重新生成|重做|再生成|重写一版"]),
    ("verify", [r"核对|检查|核验|审核|有没有错误|查错"]),
    ("replace", [r"换成|替换|改用|换一个|换掉"]),
    ("revise", [r"修改|调整|润色|优化|改一下|改改"]),
]

PRESERVE_PATTERNS = [r"不要(改|动|变)", r"不要修改", r"保持(不变|原样)", r"别动", r"无需修改"]

CN_DIGITS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

INTENT_SYSTEM = (
    "你是课程修改指令解析器。只输出 JSON；意图枚举：replace / revise / shorten / expand / restyle / remove / regenerate / verify。"
    "只解析用户要求，不要擅自扩大修改范围。"
)


def _ordinals(text: str) -> list[int]:
    numbers: list[int] = []
    for match in re.finditer(r"第\s*([0-9]+|[一二两三四五六七八九十])\s*(?:节|课|个|页|章|部分)", text):
        raw = match.group(1)
        value = int(raw) if raw.isdigit() else CN_DIGITS.get(raw)
        if value:
            numbers.append(value)
    for match in re.finditer(r"(?:^|[^0-9])([0-9]+)\s*(?:节|课)\b", text):
        numbers.append(int(match.group(1)))
    return numbers


def _sentence_at(text: str, index: int) -> str:
    start = 0
    for match in re.finditer(r"[，。；;,.!?！？\n]", text):
        if match.start() >= index:
            break
        start = match.end()
    end = len(text)
    for match in re.finditer(r"[，。；;,.!?！？\n]", text[start:]):
        end = start + match.start()
        break
    return text[start:end]


def deterministic_intent(message: str) -> tuple[str | None, list[int], list[str]]:
    text = message or ""
    intent = None
    for name, patterns in INTENT_PRIORITY:
        if any(re.search(pattern, text) for pattern in patterns):
            intent = name
            break
    preserve: list[str] = []
    preserve_sections: list[int] = []
    for pattern in PRESERVE_PATTERNS:
        for match in re.finditer(pattern, text):
            clause = _sentence_at(text, match.start()).strip()
            preserve_sections.extend(_ordinals(clause))
            preserve.append(clause)
    if preserve_sections:
        preserve.extend([f"section_{index}" for index in sorted(set(preserve_sections))])
    return intent, sorted(set(preserve_sections)), preserve


def interpret(message: str, *, llm: Any = None, sections: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    intent, preserve_sections, preserve_clauses = deterministic_intent(message)
    result: dict[str, Any] = {
        "intent": intent or "revise",
        "targets": {"section_ids": [], "artifact_ids": [], "slide_ids": [], "activity_index": None},
        "preserve": sorted(set(preserve_clauses)),
        "preserve_sections": preserve_sections,
        "constraints": {},
        "reason": message,
        "expected_scope": "unknown",
        "confidence": 0.6 if intent else 0.35,
        "source": "deterministic",
    }
    availability = llm.availability() if hasattr(llm, "availability") else {"available": False}
    if not availability.get("available"):
        return result
    prompt = (
        "任务：把用户的课程修改要求解析成结构化编辑意图。\n"
        f"用户消息：{message}\n"
        f"现有章节：{[section.get('title') for section in (sections or [])]}\n"
        f"确定性解析（权威，不得推翻）：intent={intent}，preserve_sections={preserve_sections}\n"
        '输出 JSON：{"intent": "replace", "section_ids": ["sec1"], "slide_numbers": [7], "artifact_kinds": ["case"], '
        '"activity_index": 2, "preserve": ["..."], "reason": "...", "expected_scope": "section", "confidence": 0.8}'
    )
    try:
        data = llm.generate_json(task="conversation_intent", system=INTENT_SYSTEM, prompt=prompt)
    except Exception:  # noqa: BLE001 - parsing failures fall back to deterministic result
        return result
    if not isinstance(data, dict):
        return result
    data.pop("_usage", None)  # 用量元数据会随 patch_plan 落成产物，不属于编辑意图
    llm_intent = str(data.get("intent") or "").strip()
    if intent is None and llm_intent in {name for name, _ in INTENT_PRIORITY}:
        result["intent"] = llm_intent
    if llm_intent in {name for name, _ in INTENT_PRIORITY}:
        result["llm_intent"] = llm_intent
    result["targets"]["section_ids"] = [str(item) for item in data.get("section_ids", []) if str(item)]
    result["targets"]["artifact_ids"] = [str(item) for item in data.get("artifact_kinds", []) if str(item)]
    slides = [int(item) for item in data.get("slide_numbers", []) if str(item).isdigit()]
    result["targets"]["slide_ids"] = slides
    activity = data.get("activity_index")
    if isinstance(activity, int):
        result["targets"]["activity_index"] = activity
    result["preserve"] = sorted(set(result["preserve"]) | {str(item) for item in data.get("preserve", []) if str(item)})
    result["expected_scope"] = str(data.get("expected_scope") or "section")
    try:
        result["confidence"] = min(max(float(data.get("confidence", 0.8)), 0.0), 1.0)
    except (TypeError, ValueError):
        result["confidence"] = 0.7
    result["source"] = "hybrid"
    return result
