from __future__ import annotations

import re
from typing import Any

from . import config

TASK_KEYWORDS = {
    "research": ["研究", "文献", "证据", "检索"],
    "script": ["脚本", "讲稿", "录课", "讲解"],
    "lesson-design": ["教案", "教学", "课程设计", "备课"],
    "curriculum": ["课程结构", "章节", "大纲", "项目"],
    "case": ["案例", "个例"],
    "assessment": ["评价", "课堂提问", "题目", "测验"],
    "worksheet": ["学习单", "worksheet"],
    "diagram": ["图示", "流程图", "概念图"],
    "animation": ["动画", "分镜"],
    "presentation": ["ppt", "幻灯片", "演示"],
    "review": ["检查", "评审", "qa"],
}

KNOWLEDGE_HINTS = {
    "observation": ["观察", "记录", "实录"],
    "distinction": ["辨析", "区分", "事实与判断", "vs"],
    "attitude": ["态度", "价值", "尊重", "伦理"],
    "reflection": ["反思", "感悟"],
    "procedure": ["流程", "步骤", "操作", "实务"],
    "concept": ["概念", "定义", "含义"],
    "transfer": ["迁移", "应用"],
    "critical-thinking": ["批判", "论证"],
    "research-literacy": ["文献阅读", "研究方法"],
    "case-analysis": ["个案分析", "案例分析"],
    "principle": ["原理", "规律", "原则"],
    "skill": ["技能", "技能训练"],
}


def detect_tasks(request: str) -> list[str]:
    text = request.lower()
    found = [task for task, words in TASK_KEYWORDS.items() if any(w in text for w in words)]
    if "script" not in found and any(w in text for w in ["写", "生成", "制作"]):
        found.append("script")
    return sorted(set(found)) or ["script"]


def detect_knowledge_hints(section_title: str, section_text: str = "") -> list[str]:
    text = (section_title + " " + section_text).lower()
    return [k for k, words in KNOWLEDGE_HINTS.items() if any(w in text for w in words)]


def allowed_strategies(knowledge_type: str) -> list[str]:
    mapping = config.ROUTER.get("strategy_map", {})
    return list(mapping.get(knowledge_type, [config.ROUTER.get("fallback_strategy", "explicit-instruction")]))


def parse_word_range(text: str) -> tuple[int | None, int | None]:
    patterns = [
        r"(\d{2,5})\s*[-–—~至]\s*(\d{2,5})\s*字",
        r"每?[节课][^0-9]{0,10}(\d{2,5})\s*[-–—~至]\s*(\d{2,5})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            lo, hi = int(match.group(1)), int(match.group(2))
            return (min(lo, hi), max(lo, hi))
    return (None, None)


NUMBERED_SECTION_PATTERN = re.compile(r"(?<![\d.])(\d{1,2}\.\d{1,2})\s*[、．.,，:：]?\s*([^\n，。,；;]{2,30})")


def parse_section_titles(text: str) -> list[str]:
    # M6 §23/§36：编号小节（"8.1 标题；8.2 标题"）是真正的章节；
    # 存在编号小节时，容器式标题（如"第八章四节课程脚本"）不再算作一节。
    numbered: list[str] = []
    for match in NUMBERED_SECTION_PATTERN.finditer(text):
        label = f"{match.group(1)} {match.group(2).strip()}"
        if label not in numbered:
            numbered.append(label)
    if numbered:
        return numbered

    titles: list[str] = []
    for pattern in [r"第[一二三四五六七八九十\d]+[章节节课]\s*[：:、]?\s*([^\n，。,；;]{2,30})"]:
        for match in re.finditer(pattern, text):
            title = match.group(1).strip()
            if title and title not in titles:
                titles.append(title)
    for match in re.finditer(r"(任务[一二三四五六七八九十\d]+)", text):
        if match.group(1) not in titles:
            titles.append(match.group(1))
    return titles


def requirements_from_request(request: str, template_spec: dict[str, Any] | None = None) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    outputs: list[str] = []
    word_min, word_max = parse_word_range(request)
    titles = parse_section_titles(request)
    required_components: list[str] = []
    if re.search(r"案例", request):
        required_components.append("case")
        items.append(
            {
                "req_id": "req_case",
                "text": "每节至少 1 个案例",
                "source": "user_explicit",
                "scope": "global",
                "status": "confirmed",
            }
        )
    if re.search(r"动画", request):
        required_components.append("animation")
        items.append(
            {
                "req_id": "req_animation",
                "text": "包含动画（需通过 Animation Gate，M1 尚未提供动画生产）",
                "source": "user_explicit",
                "scope": "global",
                "status": "confirmed",
            }
        )
    if re.search(r"图示|流程图|概念图", request):
        required_components.append("diagram")
    terminology = re.findall(r"[「“\"]([^」”\"]+?)[」”\"]", request)
    terminology += [t for t in ["婴幼儿", "幼儿"] if t in request and t not in terminology]
    if word_min and word_max:
        items.append(
            {
                "req_id": "req_wordcount",
                "text": f"每节 {word_min}–{word_max} 字（默认统计教师讲解正文）",
                "source": "user_explicit",
                "scope": "per_section",
                "status": "confirmed",
            }
        )
    if not titles:
        titles = ["课程内容"]
    for idx, title in enumerate(titles, start=1):
        sections.append(
            {
                "section_id": f"sec{idx}",
                "title": title,
                "word_min": word_min or 0,
                "word_max": word_max or 0,
                "required_components": list(required_components),
            }
        )
    outputs.extend(["script", "docx", "markdown"])
    if re.search(r"教案", request):
        outputs.append("lesson_plan")
        items.append(
            {
                "req_id": "req_lesson_plan",
                "text": "输出教案（含教学过程与时间安排）",
                "source": "user_explicit",
                "scope": "per_section",
                "status": "confirmed",
            }
        )
    if re.search(r"学习单|练习单|worksheet", request, re.I):
        outputs.append("worksheet")
        items.append(
            {
                "req_id": "req_worksheet",
                "text": "输出学习单（学生版不含答案）",
                "source": "user_explicit",
                "scope": "per_section",
                "status": "confirmed",
            }
        )
    if required_components:
        items.append(
            {
                "req_id": "req_components",
                "text": "每节必须包含：" + "、".join(required_components),
                "source": "user_explicit",
                "scope": "per_section",
                "status": "confirmed",
            }
        )
    items.append(
        {
            "req_id": "req_language",
            "text": "输出语言：中文",
            "source": "system_default",
            "scope": "global",
            "status": "proposed",
        }
    )
    result: dict[str, Any] = {
        "project_id": "",
        "course": titles[0] if titles else "课程",
        "language": "zh-CN",
        "outputs": outputs,
        "sections": sections,
        "word_rules": {
            "scope": "narration_body",
            "min": word_min or 0,
            "max": word_max or 0,
            "counting": config.RULES.get("word_counting", {}).get("method", "unicode_non_whitespace_chars"),
        },
        "terminology": terminology,
        "template_constraints": {},
        "items": items,
        "disallowed": [],
        "user_prompt": request,
        "template_ref": None,
    }
    if template_spec and template_spec.get("columns"):
        result["template_constraints"] = {
            "columns": [c["name"] for c in template_spec["columns"]],
            "kind": template_spec.get("kind"),
        }
    return result
