"""Subagent 种类的唯一常量源（registry 与 runtime 共享，避免循环导入）。"""

from __future__ import annotations

RESEARCH = "research-agent"
CURRICULUM = "curriculum-agent"
PEDAGOGY = "pedagogy-agent"
MEDIA = "media-agent"
QA = "qa-agent"

AGENT_NAMES: tuple[str, ...] = (RESEARCH, CURRICULUM, PEDAGOGY, MEDIA, QA)
