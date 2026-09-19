"""M6 §49–§56：安全 / 因果 / 语言 / 案例 / PPT 的可自动检查部分。

设计原则：
- 安全与因果（§49–§52）是硬门：命中 forbidden_regex 记为 SAFETY/EVIDENCE 问题；
- 语言与风格（§53–§58）是**度量**而非硬门：输出 frequency / distribution / context，
  由人工评分或报告阈值判断，禁止"出现即 FAIL"。
"""

from __future__ import annotations

import re
from typing import Any

SAFETY_FIXTURE = "fixtures/safety/adversarial.yaml"

# §53：机械连接词——只统计密度与分布，不做硬失败
MECHANICAL_CONNECTORS = (
    "首先",
    "其次",
    "再次",
    "最后",
    "值得注意的是",
    "综上所述",
    "由此可见",
    "具有重要意义",
)

# §55：案例红旗（合成/虚假机构、编造研究、隐藏诊断）
CASE_RED_FLAGS = (
    (r"(某某|X{2,}|某)大学.{0,8}(研究|调查)发现", "疑似编造研究来源"),
    (r"(研究|调查)(表明|显示).{0,12}(必然|一定|证明)", "把研究结论写成必然"),
    (r"(天才|问题儿童|坏孩子|多动症孩子|自闭症孩子)", "标签化个案"),
    (r"(某|某某)(小学|幼儿园|机构|医院)", "虚构机构名"),
)


def load_safety_cases(benchmark_dir: Any) -> dict[str, Any]:
    import yaml

    path = benchmark_dir / SAFETY_FIXTURE
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def safety_checks(text: str, case: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for pattern in case.get("forbidden_regex", []):
        if re.search(pattern, text):
            issues.append({"kind": str(case.get("category") or "SAFETY"), "detail": f"命中禁止表达：{pattern}（{case.get('id')}）"})
    required = case.get("required_any_regex") or []
    if required and not any(re.search(pattern, text) for pattern in required):
        issues.append(
            {
                "kind": str(case.get("category") or "SAFETY"),
                "detail": f"缺少应有的限定/支持性表述（{case.get('id')}）：{required}",
            }
        )
    return issues


def language_metrics(text: str) -> dict[str, Any]:
    """§53：连接词 frequency / distribution / context（非硬门）。"""
    total_chars = max(len(re.findall(r"[\u4e00-\u9fff]", text or "")), 1)
    counts = {word: len(re.findall(word, text or "")) for word in MECHANICAL_CONNECTORS}
    used = {word: count for word, count in counts.items() if count}
    per_1000 = round(sum(used.values()) * 1000 / total_chars, 2)
    positions = [
        match.start() / max(len(text or ""), 1)
        for word in used
        for match in re.finditer(word, text or "")
    ]
    return {
        "counts": counts,
        "total": sum(used.values()),
        "per_1000_chars": per_1000,
        "distribution": [round(position, 2) for position in sorted(positions)],
        "note": "密度仅供参考；教学语言允许适度使用连接词，只有机械堆砌才需要人工介入",
    }


def case_quality_checks(case_doc: dict[str, Any]) -> list[dict[str, Any]]:
    """§55：案例红旗与结构要求（linked_goal / 决策点 / 充分信息）。"""
    issues: list[dict[str, Any]] = []
    text = str(case_doc.get("text") or "")
    if not case_doc.get("linked_goal"):
        issues.append({"kind": "PEDAGOGY", "detail": f"{case_doc.get('case_id')} 未关联学习目标（linked_goal）"})
    for pattern, reason in CASE_RED_FLAGS:
        if re.search(pattern, text):
            issues.append({"kind": "CONTENT", "detail": f"{case_doc.get('case_id')} {reason}：{pattern}"})
    if len(text) < 80:
        issues.append({"kind": "CONTENT", "detail": f"{case_doc.get('case_id')} 信息量不足，无法支撑教学决策点"})
    return issues


def content_metrics(store: Any) -> dict[str, Any]:
    """把语言/PPT 度量汇总给 benchmark run 记录（§53/§58，供人工评分参考）。"""
    scripts: list[str] = []
    slides: list[dict[str, Any]] = []
    for item in store.list_artifacts():
        if not item.get("accepted_rev"):
            continue
        content = store.accepted_content(item["artifact_id"]) or {}
        if item["artifact_type"] == "script":
            scripts.extend(str(unit.get("text") or "") for unit in content.get("units", []))
        if item["artifact_type"] == "slide_plan":
            slides.extend(content.get("rows", []))
    text = "\n".join(scripts)
    return {
        "language": language_metrics(text) if text else {},
        "ppt": ppt_metrics(slides) if slides else {},
        "oral": oral_lecture_metrics(store),
    }


# §57：知识功能 → 媒体形式的预期一致性（内容本身决定图文是否有价值）
RELATIONAL_FUNCTIONS = ("causality", "state_change", "sequence", "hierarchy", "spatial_relation", "comparison")
TEMPORAL_FUNCTIONS = ("state_change", "sequence")


def diagram_checks(store: Any) -> list[dict[str, Any]]:
    """§57：Diagram 是否真的比文字有价值——关系型知识不该只用纯文本；非时序知识不该默认动画。"""
    issues: list[dict[str, Any]] = []
    for item in store.list_artifacts():
        if item["artifact_type"] != "media_plan" or not item.get("accepted_rev"):
            continue
        content = store.accepted_content(item["artifact_id"]) or {}
        for row in content.get("items", []):
            function = str(row.get("knowledge_function") or "")
            medium = str(row.get("recommended_medium") or "")
            if function in RELATIONAL_FUNCTIONS and medium == "text":
                issues.append(
                    {
                        "kind": "MEDIA",
                        "detail": f"{item['artifact_id']}/{row.get('item_id')}：{function} 关系型知识建议图示而非纯文本",
                    }
                )
            if medium == "animation" and function not in TEMPORAL_FUNCTIONS and function:
                issues.append(
                    {
                        "kind": "MEDIA",
                        "detail": f"{item['artifact_id']}/{row.get('item_id')}：{function} 非时序知识不应默认动画（应说明时序必要性）",
                    }
                )
    return issues


# §54：口语讲稿 ≠ 文章。这里给出可解释的度量，供人工评分参考（不做硬门）。
SPOKEN_MARKERS = ("我们", "你", "大家", "想想", "请", "一起", "来看", "试试")
WRITTEN_ONLY_MARKERS = ("综上所述", "由此可见", "具有重要意义", "值得注意的是", "如上所述")


def oral_lecture_metrics(store: Any) -> dict[str, Any]:
    sentences: list[str] = []
    narration = 0
    for item in store.list_artifacts():
        if item["artifact_type"] != "script" or not item.get("accepted_rev"):
            continue
        content = store.accepted_content(item["artifact_id"]) or {}
        for unit in content.get("units", []):
            if str(unit.get("kind")) != "narration":
                continue
            narration += 1
            sentences.extend(
                part.strip()
                for part in re.split(r"[。！？!?]", str(unit.get("text") or ""))
                if part.strip()
            )
    if not sentences:
        return {}
    long_sentences = [text for text in sentences if len(text) > 50]
    spoken = sum(1 for text in sentences if any(marker in text for marker in SPOKEN_MARKERS))
    written = sum(1 for text in sentences if any(marker in text for marker in WRITTEN_ONLY_MARKERS))
    return {
        "narration_units": narration,
        "sentences": len(sentences),
        "avg_sentence_chars": round(sum(len(text) for text in sentences) / len(sentences), 1),
        "long_sentence_ratio": round(len(long_sentences) / len(sentences), 3),
        "spoken_marker_ratio": round(spoken / len(sentences), 3),
        "written_only_marker_count": written,
        "note": "口语自然度以频率/分布呈现，供人工评分；不设自动阈值（§53/§54）",
    }


def ppt_metrics(slides: list[dict[str, Any]]) -> dict[str, Any]:
    """§58：幻灯片密度 / 版式重复 / notes 对应（度量，作为人工评分辅助）。"""
    densities = [str(slide.get("density") or "") for slide in slides]
    layouts = [str(slide.get("layout_archetype") or "") for slide in slides]
    notes_missing = [slide.get("slide") for slide in slides if not str(slide.get("notes") or "").strip()]
    density_counts: dict[str, int] = {}
    for value in densities:
        density_counts[value] = density_counts.get(value, 0) + 1
    layout_counts: dict[str, int] = {}
    for value in layouts:
        layout_counts[value] = layout_counts.get(value, 0) + 1
    repeated = {layout: count for layout, count in layout_counts.items() if layout and count >= 4}
    dense = sum(1 for value in densities if value == "dense")
    return {
        "slides": len(slides),
        "density": density_counts,
        "dense_ratio": round(dense / max(len(slides), 1), 3),
        "repeated_layouts": repeated,
        "missing_notes": notes_missing,
        "too_dense": dense >= max(3, len(slides) // 2),
    }
