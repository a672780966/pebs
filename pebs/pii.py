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

PII_TYPES_ZH = {
    "id_card": "身份证号",
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
