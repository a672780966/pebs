from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

MAX_SVG_BYTES = 200 * 1024

FORBIDDEN_TAGS = {"script", "foreignObject"}
BAD_HREF_PREFIXES = ("http://", "https://", "//", "data:", "file:")


def validate_svg(svg: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(svg, str) or not svg.strip():
        return ["SVG 为空"]
    if len(svg.encode("utf-8")) > MAX_SVG_BYTES:
        errors.append(f"SVG 超过大小限制（{MAX_SVG_BYTES // 1024} KB）")
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        return [f"SVG XML 解析失败：{exc}"]
    if root.tag.split("}")[-1] != "svg":
        errors.append("根元素不是 <svg>")
    if "viewBox" not in root.attrib:
        errors.append("缺少 viewBox（无法安全缩放）")
    text_count = 0
    for node in root.iter():
        tag = node.tag.split("}")[-1]
        if tag in FORBIDDEN_TAGS:
            errors.append(f"包含禁用标签 <{tag}>")
        if tag == "text":
            text_count += 1
        for raw_key, value in node.attrib.items():
            key = raw_key.split("}")[-1].lower()
            if key.startswith("on"):
                errors.append(f"包含事件属性 {key}")
            if key in ("href", "src") and str(value).lower().startswith(BAD_HREF_PREFIXES):
                errors.append(f"包含外部引用：{value[:60]}")
            if key == "style" and ("url(" in str(value) or "@import" in str(value)):
                errors.append("style 含外部引用")
    if text_count == 0:
        errors.append("SVG 没有任何 <text> 标签（视觉必须承担知识功能）")
    return errors


def svg_sha256(svg: str) -> str:
    return hashlib.sha256(svg.encode("utf-8")).hexdigest()


def media_dir(base_dir: Path, kind: str) -> Path:
    target = Path(base_dir) / "media" / kind
    target.mkdir(parents=True, exist_ok=True)
    return target


def write_media_file(base_dir: Path, kind: str, filename: str, content: str) -> Path:
    target = media_dir(base_dir, kind) / filename
    target.write_text(content, encoding="utf-8")
    return target


def storyboard_markdown(storyboard: dict[str, Any]) -> str:
    lines = [f"# 教学分镜（{storyboard.get('section_id', '')}）", ""]
    if not storyboard.get("shots"):
        lines.append("（本节没有通过 Animation Gate 的动画候选；未生成分镜。）")
        return "\n".join(lines)
    for shot in storyboard["shots"]:
        lines.append(f"## {shot.get('shot_id')} · {shot.get('knowledge_function', '')}")
        lines.append(f"- 学习目标：{shot.get('learning_goal', '')}")
        lines.append(f"- 讲解：{shot.get('narration', '')}")
        lines.append(f"- 起始画面：{shot.get('visual_state_start', '')}")
        lines.append(f"- 变化：{shot.get('visual_change', '')}")
        lines.append(f"- 终态画面：{shot.get('visual_state_end', '')}")
        lines.append(f"- 屏幕文字：{shot.get('on_screen_text', '')}")
        if shot.get("labels"):
            lines.append(f"- 标注：{'、'.join(shot['labels'])}")
        lines.append(f"- 时长：{shot.get('duration')} 秒")
        if shot.get("cognitive_load_note"):
            lines.append(f"- 认知负荷提示：{shot['cognitive_load_note']}")
        lines.append(f"- 衔接：{shot.get('continuity_from', '')} → {shot.get('continuity_to', '')}")
        lines.append("")
    lines.append("## 静态终态设计")
    lines.append(storyboard.get("static_terminal_state", ""))
    lines.append("")
    lines.append("## 视频生成提示词（在视频渲染前停止）")
    lines.append(storyboard.get("video_prompt", ""))
    return "\n".join(lines)
