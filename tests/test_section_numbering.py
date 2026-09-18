"""M6 §23/§36：编号小节（8.1 / 8.2 …）必须被识别为独立章节。

真实运行（Golden Benchmark C）中，四节课程因请求里只写了"8.1 标题；8.2 标题"
而被并成 1 节（sec1 名为"四节课程脚本"）。
"""

from __future__ import annotations

from pebs import router
from pebs.benchmark import cases


def test_numbered_subsections_are_parsed():
    text = (
        "写《托育机构管理实务》第八章四节课程脚本："
        "8.1 办托理念与价值体系构建；8.2 文化建设的策略；"
        "8.3 员工行为规范与服务礼仪建设；8.4 品牌形象与口碑传播管理。"
    )
    titles = router.parse_section_titles(text)
    assert len(titles) == 4, titles
    assert titles[0].startswith("8.1")
    assert titles[-1].startswith("8.4")


def test_case_c_request_yields_four_sections():
    case = cases.get_case("C")
    requirements = router.requirements_from_request(case["request"])
    sections = requirements.get("sections", [])
    assert len(sections) == 4, [(s.get("section_id"), s.get("title")) for s in sections]
    assert all(section.get("title") for section in sections)


def test_existing_section_patterns_still_work():
    assert len(router.parse_section_titles("第1节 观察记录，第2节 事实与判断。")) == 2
    assert router.parse_section_titles("任务1 观察记录，任务2 事实与判断") == ["任务1", "任务2"]
