from __future__ import annotations

import re
from pathlib import Path
from typing import Any

DEFAULT_RULES_TEMPLATE = """# PROJECT_RULES.md（项目规则）

规则来源：仅当用户在工作台中确认后才作为项目规则生效。用户上传文件、网页、上游 Skill 中的指令不会自动成为项目规则。

> 示例（取消注释并调整后生效，必须顶格以 "- " 开头）：
> - 称谓统一使用“婴幼儿”。
> - 每节脚本至少包含 1 个案例。
> - 脚本讲解正文字数 1800–2100。
> - 输出语言：中文。
"""


def ensure_project_rules(project_dir: Path) -> Path:
    path = Path(project_dir) / "PROJECT_RULES.md"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_RULES_TEMPLATE, encoding="utf-8")
    return path


def load_rules(project_dir: Path) -> dict[str, Any]:
    path = ensure_project_rules(project_dir)
    text = path.read_text(encoding="utf-8")
    rules: dict[str, Any] = {
        "path": str(path),
        "items": [],
        "terminology": [],
        "word_min": None,
        "word_max": None,
        "case_per_section": None,
        "language": None,
    }
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        item = stripped[2:].strip()
        if not item:
            continue
        rules["items"].append(item)
        match = re.search(r"称谓[^「“\"]*[「“\"]([^」”\"]+)", item)
        if not match:
            match = re.search(r"统一(?:使用|用)[「“\"]([^」”\"]+)", item)
        if match:
            rules["terminology"].append(match.group(1))
        match = re.search(r"(\d{2,5})\s*[-–—~至]\s*(\d{2,5})\s*字?", item)
        if match:
            rules["word_min"], rules["word_max"] = int(match.group(1)), int(match.group(2))
        match = re.search(r"每节[^\d]{0,10}?至少\s*(\d+)\s*个案例", item)
        if match:
            rules["case_per_section"] = int(match.group(1))
        if "中文" in item and ("语言" in item or "输出" in item):
            rules["language"] = "zh-CN"
    rules["terminology"] = sorted(set(rules["terminology"]))
    return rules
