from __future__ import annotations

import io

import pytest
from conftest import REQUEST_1, FakeLLM, FakeResearch, run_build

from pebs import providers
from pebs.providers import (
    CompositeResearch,
    OpenAlexResearch,
    ProviderError,
    fetch_pdf_text,
)


class StubResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


class StubStreamResponse:
    def __init__(self, status_code=200, headers=None, chunks=()):
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = list(chunks)

    def iter_bytes(self):
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_openalex_normalizes_abstract_doi_and_oa(monkeypatch):
    payload = {
        "results": [
            {
                "display_name": "Observation and inference in teacher training",
                "doi": "https://doi.org/10.5555/oa.1",
                "publication_year": 2021,
                "type": "review",
                "abstract_inverted_index": {"Observe": [0], "first": [1], "then": [2], "infer": [3]},
                "best_oa_location": {"pdf_url": "https://oa.example.org/paper.pdf"},
                "primary_location": {"source": {"display_name": "Journal of Teacher Education"}},
            }
        ]
    }
    monkeypatch.setattr(providers.httpx, "get", lambda *a, **k: StubResponse(200, payload))
    research = OpenAlexResearch({"enabled": True, "allowed_sources": ["openalex"], "require_api_key": False})
    results = research.search("q")
    assert len(results) == 1
    item = results[0]
    assert item["doi"] == "10.5555/oa.1"
    assert item["abstract"] == "Observe first then infer"
    assert item["content_level"] == "abstract"
    assert item["fulltext_url"] == "https://oa.example.org/paper.pdf"
    assert item["database"] == "openalex"
    assert item["publish_date"] == "2021"


def test_openalex_without_abstract_is_metadata(monkeypatch):
    payload = {"results": [{"display_name": "No abstract", "doi": "10.1/x"}]}
    monkeypatch.setattr(providers.httpx, "get", lambda *a, **k: StubResponse(200, payload))
    research = OpenAlexResearch({"enabled": True, "allowed_sources": ["openalex"]})
    results = research.search("q")
    assert results[0]["content_level"] == "metadata"
    assert results[0]["abstract"] == ""


class _StubAdapter:
    def __init__(self, items, error: str | None = None):
        self.items = items
        self.error = error

    def search(self, query, rows=5):
        if self.error:
            raise ProviderError(self.error)
        return self.items


def test_composite_merges_dedupes_and_reports_errors():
    composite = CompositeResearch({"enabled": True, "allowed_sources": []})
    crossref_items = [
        {
            "title": "Same paper",
            "doi": "10.1/dup",
            "abstract": "",
            "content_level": "metadata",
            "fulltext_url": None,
            "database": "crossref",
        }
    ]
    openalex_items = [
        {
            "title": "Same paper",
            "doi": "10.1/dup",
            "abstract": "Rich abstract",
            "content_level": "abstract",
            "fulltext_url": "https://oa.example/x.pdf",
            "database": "openalex",
        },
        {"title": "Other", "doi": "10.2/other", "abstract": "", "content_level": "metadata", "database": "openalex"},
    ]
    composite.adapters = [
        ("crossref", _StubAdapter(crossref_items)),
        ("openalex", _StubAdapter(openalex_items)),
    ]
    result = composite.search("q")
    assert result.per_source == {"crossref": 1, "openalex": 2}
    assert result.errors == {}
    assert len(result.items) == 2
    merged = next(i for i in result.items if i["doi"] == "10.1/dup")
    assert merged["content_level"] == "abstract"
    assert merged["abstract"] == "Rich abstract"
    assert merged["fulltext_url"] == "https://oa.example/x.pdf"

    composite.adapters = [
        ("crossref", _StubAdapter([], error="HTTP 429")),
        ("openalex", _StubAdapter(openalex_items)),
    ]
    result = composite.search("q")
    assert result.errors == {"crossref": "HTTP 429"}
    assert result.per_source == {"openalex": 2}


def test_composite_availability_reports_configuration():
    none = CompositeResearch({"enabled": False, "allowed_sources": []})
    status = none.availability()
    assert status["available"] is False
    assert len(status["reasons"]) == 2
    both = CompositeResearch({"enabled": True, "allowed_sources": ["crossref", "openalex"]})
    status = both.availability()
    assert status["available"] is True
    assert status["allowed_sources"] == ["crossref", "openalex"]
    assert both.sources() == ["crossref", "openalex"]


def test_fetch_pdf_rejects_wrong_mime(monkeypatch):
    def fake_stream(method, url, **kwargs):
        return StubStreamResponse(headers={"Content-Type": "text/html"}, chunks=[b"%PDF-1.4"])

    monkeypatch.setattr(providers.httpx, "stream", fake_stream)
    with pytest.raises(ProviderError, match="MIME"):
        fetch_pdf_text("https://example.org/page")


def test_fetch_pdf_rejects_bad_magic(monkeypatch):
    def fake_stream(method, url, **kwargs):
        return StubStreamResponse(headers={"Content-Type": "application/pdf"}, chunks=[b"<html>nope</html>"])

    monkeypatch.setattr(providers.httpx, "stream", fake_stream)
    with pytest.raises(ProviderError, match="magic"):
        fetch_pdf_text("https://example.org/x.pdf")


def test_fetch_pdf_rejects_oversize(monkeypatch):
    def fake_stream(method, url, **kwargs):
        return StubStreamResponse(
            headers={"Content-Type": "application/pdf", "Content-Length": str(99 * 1024 * 1024)},
            chunks=[b"%PDF-1.4"],
        )

    monkeypatch.setattr(providers.httpx, "stream", fake_stream)
    with pytest.raises(ProviderError, match="大小限制"):
        fetch_pdf_text("https://example.org/x.pdf", max_bytes=1024)


def test_fetch_pdf_rejects_non_http_scheme():
    with pytest.raises(ProviderError, match="http"):
        fetch_pdf_text("file:///etc/passwd")


def test_extract_pdf_text_reports_scanned_pdf():
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(ProviderError, match="未提取到文本"):
        providers._extract_pdf_text(buffer.getvalue())


def test_fulltext_fallback_supports_claim(engine):
    engine.llm = FakeLLM()
    engine.research = FakeResearch(
        abstract=False, fulltext_url="https://oa.example.org/paper.pdf"
    )
    run_id, changeset_id = run_build(engine, REQUEST_1)
    assert engine.research.fulltext_calls == ["https://oa.example.org/paper.pdf"]
    engine.accept(changeset_id)
    claims = engine.evidence.claims()
    assert claims and claims[0]["status"] == "SUPPORTED"
    sources = engine.evidence.sources()
    full_text_sources = [s for s in sources if s["content_level"] == "full_text"]
    assert full_text_sources
    g2 = engine.store.accepted_content("gate:G2:script:sec1")
    assert g2["status"] == "PASS"
