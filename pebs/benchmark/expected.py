"""`benchmarks/expected/`（§20 要求的目录）。

期望值只有一个真实来源：`benchmarks/cases/*.yaml` 里的 `expect:` 块。
本模块把它投影成 `benchmarks/expected/<case_id>.yaml`，方便：

- 人工审阅"这一条 case 到底期望什么"，不必在 case 定义里翻找；
- 外部工具/CI 直接读期望而无需解析整个 case。

投影必须与来源一致：`write_expected()` 生成，测试保证不漂移。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from . import cases


def expected_dir() -> Path:
    return cases.benchmark_dir() / "expected"


def expected_payload(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case.get("id"),
        "title": case.get("title", ""),
        "mode_targets": case.get("mode_targets", []),
        "expect": case.get("expect") or {},
        "source": str(Path(str(case.get("_path") or "")).name),
    }


def render(case: dict[str, Any]) -> str:
    return yaml.safe_dump(expected_payload(case), allow_unicode=True, sort_keys=True)


def write_expected(case_list: list[dict[str, Any]] | None = None) -> list[Path]:
    target = expected_dir()
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for case in case_list if case_list is not None else cases.load_cases():
        path = target / f"{case['id']}.yaml"
        path.write_text(render(case), encoding="utf-8")
        written.append(path)
    return written


def load_expected(case_id: str) -> dict[str, Any]:
    path = expected_dir() / f"{case_id}.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
