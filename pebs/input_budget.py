"""M6 §60：进入 LLM 的输入预算。

规则：
- 超出预算必须显式失败（on_exceed=reject）或显式 summarize/chunk，**禁止静默截断**；
- 每次运行都把预算记账写入产物（materials.budget_report），便于事后审计与成本分析。
"""

from __future__ import annotations

from typing import Any

from . import config

DEFAULTS = {
    "max_material_chars": 120000,
    "max_template_chars": 60000,
    "max_sections": 40,
    "max_files": 20,
    "on_exceed": "reject",
}


class InputBudgetExceeded(Exception):
    pass


def budget() -> dict[str, Any]:
    merged = dict(DEFAULTS)
    merged.update({key: value for key, value in (config.RULES.get("input_budget") or {}).items()})
    return merged


def measure(*, materials: list[dict[str, Any]], template_spec: dict[str, Any] | None = None, sections: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    material_chars = sum(len(str(entry.get("text") or "")) for entry in materials)
    template_text = ""
    if template_spec:
        template_text = str(template_spec.get("raw_text") or "")
        if not template_text:
            template_text = "\n".join(
                str(item) for item in (template_spec.get("section_headings") or []) + (template_spec.get("columns") or [])
            )
    return {
        "material_chars": material_chars,
        "template_chars": len(template_text),
        "files": len(materials),
        "sections": len(sections or []),
        "per_file_chars": [
            {"name": str(entry.get("name") or entry.get("path") or ""), "chars": len(str(entry.get("text") or ""))}
            for entry in materials
        ],
    }


def exceeded(measurement: dict[str, Any], *, rules: dict[str, Any] | None = None) -> list[str]:
    rules = rules or budget()
    problems: list[str] = []
    if measurement["material_chars"] > int(rules["max_material_chars"]):
        problems.append(f"材料文本 {measurement['material_chars']} 字 > 上限 {rules['max_material_chars']}")
    if measurement["template_chars"] > int(rules["max_template_chars"]):
        problems.append(f"模板文本 {measurement['template_chars']} 字 > 上限 {rules['max_template_chars']}")
    if measurement["files"] > int(rules["max_files"]):
        problems.append(f"文件数 {measurement['files']} > 上限 {rules['max_files']}")
    if measurement["sections"] > int(rules["max_sections"]):
        problems.append(f"章节数 {measurement['sections']} > 上限 {rules['max_sections']}")
    return problems


def enforce(measurement: dict[str, Any], *, rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """返回带 decision 的记账；超预算时按 on_exceed 决定 reject / summarize 标记。"""
    rules = rules or budget()
    problems = exceeded(measurement, rules=rules)
    decision = "accept" if not problems else str(rules.get("on_exceed") or "reject")
    report = {
        **measurement,
        "limits": {key: rules[key] for key in ("max_material_chars", "max_template_chars", "max_sections", "max_files")},
        "problems": problems,
        "decision": decision,
        "note": "预算记账：超限必须显式处理，禁止静默截断（M6 §60）",
    }
    if problems and decision == "reject":
        raise InputBudgetExceeded("；".join(problems))
    return report
