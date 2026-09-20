"""§20：`benchmarks/expected/` 必须存在，且与 case 定义保持一致（不得漂移）。"""

from __future__ import annotations

from pathlib import Path

from pebs.benchmark import cases, expected


def test_expected_directory_covers_every_case():
    ids = [case["id"] for case in cases.load_cases()]
    assert ids, "必须存在 golden case"
    on_disk = sorted(path.stem for path in expected.expected_dir().glob("*.yaml"))
    assert on_disk == sorted(ids), f"expected/ 与 cases/ 不一致：{on_disk} vs {sorted(ids)}"


def test_expected_projection_matches_its_source():
    """投影只是"读物"：内容必须等于 cases/*.yaml 的 expect 块。"""
    for case in cases.load_cases():
        path = expected.expected_dir() / f"{case['id']}.yaml"
        assert path.exists(), f"{case['id']}: 缺少 expected/{case['id']}.yaml"
        on_disk = path.read_text(encoding="utf-8")
        assert on_disk == expected.render(case), (
            f"{case['id']}: expected/ 已漂移；请调用 expected.write_expected() 重新生成"
        )
        loaded = expected.load_expected(case["id"])
        assert loaded["expect"] == (case.get("expect") or {})
        assert loaded["source"] == Path(str(case["_path"])).name
