"""M6 §44–§45：研究层离线 fixture 与真实 provider 探针。

- 默认只在标记 `live_research` 时访问真实 API（scheduled / manual workflow），
  避免 Crossref/PubMed/Semantic Scholar 波动导致主 CI 变红；
- 离线部分（fixture 解析）始终可跑。
"""

from __future__ import annotations

import json

import pytest

from pebs.benchmark import cases

pytestmark = pytest.mark.live_research


def test_offline_research_fixture_is_valid():
    path = cases.benchmark_dir() / "fixtures" / "research" / "phone_anxiety_papers.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["synthetic"] is True
    for result in data["results"]:
        assert result["abstract"]
        assert result["causal_strength"] in {
            "association_only",
            "longitudinal_small_effect",
            "mixed_evidence",
        }


@pytest.mark.external
def test_live_research_providers_respond():
    from pebs import providers

    research = providers.get_research()
    availability = research.availability()
    if not availability.get("available"):
        pytest.skip("research providers 未配置：" + "；".join(availability.get("reasons", [])))
    result = research.search("college students smartphone use anxiety", rows=3)
    items = getattr(result, "items", result)
    assert items, "真实研究检索必须返回结果（per_source=%r, errors=%r）" % (
        getattr(result, "per_source", {}),
        getattr(result, "errors", {}),
    )
    first = items[0]
    assert first.get("title")
    # 合并后的条目至少要有可追溯标识（DOI 或 provider 来源），否则无法进入 Evidence Gate
    assert first.get("doi") or first.get("providers") or first.get("sources") or first.get("source")
