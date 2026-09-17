from __future__ import annotations

from pebs import providers
from pebs.providers import (
    CompositeResearch,
    PubMedResearch,
    SemanticScholarResearch,
    UnpaywallLookup,
)


class StubResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.headers = {}

    def json(self):
        return self._payload


PUBMED_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>12345</PMID>
      <Article>
        <ArticleTitle>Observation training improves inference control</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Novices record inferences as facts.</AbstractText>
          <AbstractText>Training reduced this tendency.</AbstractText>
        </Abstract>
        <Journal>
          <Title>Journal of Teacher Education</Title>
          <JournalIssue><PubDate><Year>2021</Year></PubDate></JournalIssue>
        </Journal>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="doi">10.1002/pm.1</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>"""


def test_semantic_scholar_normalization(monkeypatch):
    payload = {
        "data": [
            {
                "title": "Observing without inferring",
                "abstract": "Direct observation precedes inference.",
                "year": 2019,
                "venue": "Teaching and Teacher Education",
                "externalIds": {"DOI": "10.1/ss.1"},
                "openAccessPdf": {"url": "https://ss.example/x.pdf"},
                "publicationTypes": ["Review"],
            }
        ]
    }
    monkeypatch.setattr(providers.httpx, "get", lambda *a, **k: StubResponse(200, payload))
    research = SemanticScholarResearch({"enabled": True, "allowed_sources": ["semantic_scholar"]})
    results = research.search("q")
    assert len(results) == 1
    item = results[0]
    assert item["doi"] == "10.1/ss.1"
    assert item["publish_date"] == "2019"
    assert item["content_level"] == "abstract"
    assert item["fulltext_url"] == "https://ss.example/x.pdf"
    assert item["database"] == "semantic_scholar"


def test_pubmed_esearch_efetch_parsing(monkeypatch):
    def fake_get(url, params=None, **kwargs):
        if "esearch" in url:
            return StubResponse(200, {"esearchresult": {"idlist": ["12345"]}})
        return StubResponse(200, text=PUBMED_XML)

    monkeypatch.setattr(providers.httpx, "get", fake_get)
    research = PubMedResearch({"enabled": True, "allowed_sources": ["pubmed"]})
    results = research.search("q")
    assert len(results) == 1
    item = results[0]
    assert item["title"] == "Observation training improves inference control"
    assert "BACKGROUND: Novices record inferences as facts." in item["abstract"]
    assert "Training reduced this tendency." in item["abstract"]
    assert item["doi"] == "10.1002/pm.1"
    assert item["publish_date"] == "2021"
    assert item["database"] == "pubmed"


def test_pubmed_empty_results(monkeypatch):
    monkeypatch.setattr(
        providers.httpx, "get", lambda *a, **k: StubResponse(200, {"esearchresult": {"idlist": []}})
    )
    research = PubMedResearch({"enabled": True, "allowed_sources": ["pubmed"]})
    assert research.search("q") == []


def test_unpaywall_finds_pdf_and_handles_404(monkeypatch):
    monkeypatch.setattr(
        providers.httpx,
        "get",
        lambda *a, **k: StubResponse(
            200, {"best_oa_location": {"url_for_pdf": "https://oa.example/paper.pdf"}}
        ),
    )
    lookup = UnpaywallLookup({"enabled": True, "contact_email": "a@b.c"})
    assert lookup.find_pdf("10.1/x") == "https://oa.example/paper.pdf"

    monkeypatch.setattr(providers.httpx, "get", lambda *a, **k: StubResponse(404))
    assert lookup.find_pdf("10.1/missing") is None


def test_unpaywall_requires_contact_email():
    lookup = UnpaywallLookup({"enabled": True, "contact_email": ""})
    assert lookup.availability()["available"] is False


def test_composite_includes_new_sources():
    composite = CompositeResearch(
        {
            "enabled": True,
            "allowed_sources": ["crossref", "openalex", "semantic_scholar", "pubmed"],
            "contact_email": "a@b.c",
        }
    )
    assert composite.sources() == ["crossref", "openalex", "semantic_scholar", "pubmed"]


def test_composite_find_fulltext_uses_unpaywall(monkeypatch):
    monkeypatch.setattr(
        providers.httpx,
        "get",
        lambda *a, **k: StubResponse(200, {"oa_locations": [{"url_for_pdf": "https://oa.example/z.pdf"}]}),
    )
    composite = CompositeResearch(
        {"enabled": True, "allowed_sources": [], "contact_email": "a@b.c", "use_unpaywall": True}
    )
    assert composite.find_fulltext("10.1/z") == "https://oa.example/z.pdf"


def test_composite_find_fulltext_without_email_returns_none():
    composite = CompositeResearch(
        {"enabled": True, "allowed_sources": [], "contact_email": "", "use_unpaywall": True}
    )
    assert composite.find_fulltext("10.1/z") is None
