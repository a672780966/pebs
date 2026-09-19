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
        re.compile(
            r"(?:学生|同学|幼儿|小朋友|儿童|家长)\s*[：:]?\s*([\u4e00-\u9fff]{2,3}?)"
            r"(?=[，。；、！？：\s）)】\]]|(?:在|说|把|被|是|有|没|不|很|总|经常|喜欢|完成|参加|"
            r"回答|举手|今天|昨天|明天|上午|下午|最近)|$)"
        ),
    ),
    ("name_label", re.compile(r"(?:姓名|名字|联系人|监护人)\s*[：:]\s*([\u4e00-\u9fff]{2,3})")),
    ("address", re.compile(r"[\u4e00-\u9fff]{2,8}(?:街道|小区|号楼|单元|门牌)")),
]

LAYER_L1 = "L1_deterministic"
LAYER_L2 = "L2_semantic_reidentification"
LAYER_L3 = "L3_manual_review"

# M6 §35 Gate False Positive 修正：中文里的常见虚词与通用名词不能被当作学生姓名。
_NAME_PARTICLES = set("的了是在和与对把被这那有不没更最也都还只就才又很非常个种些吗呢啊吧")
_NAME_STOPWORDS = {
    "判断", "记录", "观察", "行为", "表现", "心理", "发展", "学习", "问题", "案例", "情况", "年龄",
    "特点", "差异", "需要", "可能", "理解", "认知", "态度", "情绪", "数据", "统计", "群体", "个体",
    "特征", "能力", "水平", "方法", "策略", "内容", "目标", "结果", "过程", "结构", "关系", "影响",
    "作用", "意义", "价值", "社会", "家庭", "教师", "学校", "课程", "教学", "教育", "健康", "成长",
    "支持", "材料", "反馈", "评价", "活动", "环节", "阶段", "现象", "观点", "理论", "研究", "样本",
    # M6 对抗性安全审查（§49）"这个总独处的学生可能是什么心理疾病？" 这类请求里，
    # "可能/应该/也许" 等情态副词会被误当作姓名，导致整条合法审查请求被拒。
    "应该", "也许", "大概", "或许", "往往", "经常", "总是", "一直", "特别", "非常", "有点",
    "为什么", "怎么样", "怎么办", "是否", "能否", "可以", "不能", "不会", "不是", "没有",
    "一定", "必须", "肯定", "当然", "显然", "其实", "确实", "根本", "简直", "尤其", "甚至",
}
# 明确的情态/功能词首字：出现这些字开头的 2–3 字串不是姓名的概率极高
_NAME_PREFIX_BLOCK = set("可应也或往经总特非是若有没怎能怎如为当即并且但而则")


_NAME_SUFFIX_BLOCK = set(
    "标签式化性度率量力感观型类种者员家师界域期点线面层级项条款例案据料品件物事情况态势象征记录表达方式样"
)


def _looks_like_name(value: str) -> bool:
    if not value or len(value) < 2:
        return False
    if any(char in _NAME_PARTICLES for char in value):
        return False
    if value in _NAME_STOPWORDS:
        return False
    if value[0] in _NAME_PREFIX_BLOCK:
        return False
    if value[-1] in _NAME_SUFFIX_BLOCK:
        return False
    return True

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
            if kind in ("named_student", "name_label") and not _looks_like_name(str(captured)):
                continue
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
        def _replace(match: re.Match[str]) -> str:
            captured = next((group for group in match.groups() if group), match.group(0))
            if kind in ("named_student", "name_label") and not _looks_like_name(str(captured)):
                return match.group(0)
            return _mask_value(str(captured))

        masked = pattern.sub(_replace, masked)
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
