from __future__ import annotations

import re
from typing import Any

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("id_card", re.compile(r"\b\d{17}[\dXx]\b")),
    ("phone", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("student_id", re.compile(r"(?:学号|学籍号|考号)\s*[：:]?\s*([A-Za-z0-9\-]{4,20})")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")),
    (
        "named_student",
        re.compile(r"(?:学生|同学|幼儿|小朋友|家长)\s*[：:]?\s*([\u4e00-\u9fff]{2,3})(?=[，。；、\s）)】]|$)"),
    ),
    ("name_label", re.compile(r"(?:姓名|名字|联系人|监护人)\s*[：:]\s*([\u4e00-\u9fff]{2,3})")),
    ("address", re.compile(r"[\u4e00-\u9fff]{2,8}(?:街道|小区|号楼|单元|门牌)")),
]

LAYER_L1 = "L1_deterministic"
LAYER_L2 = "L2_semantic_reidentification"
LAYER_L3 = "L3_manual_review"

PII_TYPES_ZH = {    "id_card": "身份证号",
    "phone": "手机号",
    "student_id": "学号",
    "email": "邮箱",
    "named_student": "具名学生/幼儿",
    "name_label": "姓名标签",
    "address": "住址信息",
}


def scan(text: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    if not text:
        return hits
    for kind, pattern in PATTERNS:
        for match in pattern.finditer(text):
            captured = next((group for group in match.groups() if group), match.group(0))
            hits.append(
                {
                    "type": kind,
                    "label": PII_TYPES_ZH.get(kind, kind),
                    "masked": _mask_value(str(captured)),
                    "span": [match.start(), match.end()],
                }
            )
    return hits


def _mask_value(value: str) -> str:
    if len(value) <= 2:
        return "█" * len(value)
    return value[0] + "█" * (len(value) - 2) + value[-1]


def mask_text(text: str) -> str:
    masked = text
    for kind, pattern in PATTERNS:
        masked = pattern.sub(lambda match: _mask_value(next((g for g in match.groups() if g), match.group(0))), masked)
    return masked


def is_sensitive(text: str, *, threshold: int = 1) -> bool:
    return len(scan(text)) >= threshold


def summarize(hits: list[dict[str, Any]]) -> str:
    labels: list[str] = []
    for hit in hits:
        label = f"{hit['label']}（{hit['masked']}）"
        if label not in labels:
            labels.append(label)
    return "、".join(labels[:6])


SEMANTIC_SYSTEM = (
    "你是隐私复核器，只输出 JSON。判断文本是否存在可重识别风险："
    "小样本班级+地点+特殊经历、罕见个人属性组合、能指向具体学生的真实线索。"
    "不判断内容对错，只判断隐私风险。"
)


def semantic_review_prompt(text: str, *, context: str = "") -> str:
    return f"""任务：对下面的课程材料做可重识别风险复核（L2 语义层）。
材料（截断）：{text[:6000]}
补充背景：{context or '无'}
输出 JSON：{{"risk": "LOW|MEDIUM|HIGH", "reidentifiable": true, "reasons": ["..."], "suggestions": ["..."]}}"""


def semantic_review(llm: Any, text: str, *, context: str = "") -> dict[str, Any] | None:
    availability = llm.availability() if hasattr(llm, "availability") else {"available": False}
    if not availability.get("available"):
        return None
    try:
        data = llm.generate_json(task="privacy_review", system=SEMANTIC_SYSTEM, prompt=semantic_review_prompt(text, context=context))
    except Exception:  # noqa: BLE001 - provider failure must not fabricate a privacy verdict
        return None
    if not isinstance(data, dict):
        return None
    risk = str(data.get("risk", "")).upper()
    if risk not in ("LOW", "MEDIUM", "HIGH"):
        return None
    data["risk"] = risk
    data["reidentifiable"] = bool(data.get("reidentifiable", risk != "LOW"))
    data["reasons"] = [str(item) for item in (data.get("reasons") or []) if str(item).strip()]
    data["suggestions"] = [str(item) for item in (data.get("suggestions") or []) if str(item).strip()]
    return data
