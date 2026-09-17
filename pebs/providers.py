from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from . import config

RETRY_BASE_DELAY = 1.0
TRANSIENT_STATUS = {429, 500, 502, 503, 504}


def _transient_get(
    url: str,
    *,
    params: dict[str, Any],
    timeout: int,
    user_agent: str,
    extra_headers: dict[str, str] | None = None,
) -> httpx.Response:
    attempts = int(config.RULES.get("retries", {}).get("read_transient", 2))
    last_error = ""
    response = None
    headers = {"User-Agent": user_agent, **(extra_headers or {})}
    for attempt in range(attempts + 1):
        try:
            response = httpx.get(url, params=params, timeout=timeout, headers=headers)
        except httpx.HTTPError as exc:
            last_error = f"网络错误: {exc}"
            response = None
        else:
            if response.status_code in TRANSIENT_STATUS:
                last_error = f"HTTP {response.status_code}"
                retry_after = response.headers.get("Retry-After")
                delay = (
                    float(retry_after)
                    if retry_after and retry_after.isdigit()
                    else RETRY_BASE_DELAY * (2**attempt)
                )
                if attempt < attempts:
                    time.sleep(delay)
                continue
            if response.status_code >= 400:
                raise ProviderError(f"HTTP {response.status_code}")
            return response
        if attempt < attempts:
            time.sleep(RETRY_BASE_DELAY * (2**attempt))
    raise ProviderError(f"请求失败（已重试 {attempts} 次）: {last_error}")


def _contact(cfg: dict[str, Any]) -> str:
    return str(cfg.get("contact_email") or "").strip()


def _user_agent(cfg: dict[str, Any], product: str = "pebs-m1/0.1") -> str:
    contact = _contact(cfg)
    return f"{product} (mailto:{contact})" if contact else product


def _level_rank(level: str) -> int:
    return {"full_text": 2, "user_excerpt": 2, "abstract": 1}.get(level, 0)


def _item_key(item: dict[str, Any]) -> str:
    doi = str(item.get("doi") or "").strip().lower()
    if doi:
        return doi
    return re.sub(r"\s+", "", str(item.get("title") or "")).lower()[:80]


def merge_research_items(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {_item_key(i): dict(i) for i in existing}
    for item in incoming:
        key = _item_key(item)
        current = merged.get(key)
        if current is None:
            merged[key] = dict(item)
            continue
        if _level_rank(item.get("content_level", "metadata")) > _level_rank(current.get("content_level", "metadata")):
            current.update(
                {k: v for k, v in item.items() if k in ("content_level", "abstract", "fulltext_url")}
            )
        if not current.get("fulltext_url") and item.get("fulltext_url"):
            current["fulltext_url"] = item["fulltext_url"]
    return list(merged.values())


class ProviderUnavailable(Exception):
    pass


class ProviderError(Exception):
    pass


def _extract_json(text: str) -> dict[str, Any]:
    if text is None:
        raise ProviderError("empty provider response")
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, flags=re.S)
    if fence:
        raw = fence.group(1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ProviderError("provider response is not JSON")
    try:
        parsed = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ProviderError(f"provider JSON parse error: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ProviderError("provider JSON is not an object")
    return parsed


class OpenAICompatLLM:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg

    @property
    def model(self) -> str:
        return str(self.cfg.get("model") or "")

    def availability(self) -> dict[str, Any]:
        enabled = bool(self.cfg.get("enabled"))
        base_url = str(self.cfg.get("base_url") or "")
        model = str(self.cfg.get("model") or "")
        key_env = str(self.cfg.get("api_key_env") or "")
        require_key = bool(self.cfg.get("require_api_key", True))
        key_present = config.env_present(key_env) if key_env else False
        reasons: list[str] = []
        if not enabled:
            reasons.append("config/providers.yaml: llm.enabled=false")
        if not base_url:
            reasons.append("llm.base_url 未配置")
        if not model:
            reasons.append("llm.model 未配置")
        if require_key and not key_present:
            reasons.append(f"环境变量 {key_env or 'API_KEY'} 未设置")
        return {
            "available": not reasons,
            "reasons": reasons,
            "id": self.cfg.get("id", "default-llm"),
            "model": model,
            "base_url": base_url,
            "api_key_env": key_env,
            "send_scope": self.cfg.get("send_scope", []),
        }

    def require(self) -> None:
        status = self.availability()
        if not status["available"]:
            raise ProviderUnavailable("LLM Provider 不可用: " + "; ".join(status["reasons"]))

    def generate_json(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        temperature: float | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        self.require()
        base_url = str(self.cfg["base_url"]).rstrip("/")
        url = base_url + "/chat/completions"
        key_env = str(self.cfg.get("api_key_env") or "")
        headers = {"Content-Type": "application/json"}
        if key_env and os.environ.get(key_env):
            headers["Authorization"] = "Bearer " + os.environ[key_env]
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.cfg.get("temperature", 0.2) if temperature is None else temperature,
            "response_format": {"type": "json_object"},
        }
        try:
            resp = httpx.post(
                url,
                json=payload,
                headers=headers,
                timeout=timeout or int(self.cfg.get("timeout_seconds", 180)),
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"LLM 请求失败（{task}）: {exc}") from exc
        if resp.status_code >= 400:
            raise ProviderError(f"LLM HTTP {resp.status_code}（{task}）: {resp.text[:300]}")
        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise ProviderError(f"LLM 响应结构异常（{task}）") from exc
        parsed = _extract_json(content)
        parsed["_usage"] = data.get("usage", {})
        return parsed


class CrossrefResearch:
    BASE = "https://api.crossref.org/works"

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg

    def availability(self) -> dict[str, Any]:
        enabled = bool(self.cfg.get("enabled"))
        allowed = self.cfg.get("allowed_sources", [])
        key_env = str(self.cfg.get("api_key_env") or "")
        require_key = bool(self.cfg.get("require_api_key", False))
        reasons: list[str] = []
        if not enabled:
            reasons.append("config/providers.yaml: research.enabled=false")
        if "crossref" not in allowed:
            reasons.append("crossref 不在 allowed_sources")
        if require_key and key_env and not config.env_present(key_env):
            reasons.append(f"环境变量 {key_env} 未设置")
        return {
            "available": not reasons,
            "reasons": reasons,
            "id": self.cfg.get("id", "default-research"),
            "allowed_sources": allowed,
        }

    def require(self) -> None:
        status = self.availability()
        if not status["available"]:
            raise ProviderUnavailable("研究 Provider 不可用: " + "; ".join(status["reasons"]))

    def search(self, query: str, rows: int = 5) -> list[dict[str, Any]]:
        self.require()
        params = {
            "query.bibliographic": query,
            "rows": str(rows),
            "select": "DOI,title,abstract,issued,type,container-title",
        }
        try:
            response = _transient_get(
                self.BASE,
                params=params,
                timeout=int(self.cfg.get("timeout_seconds", 60)),
                user_agent=_user_agent(self.cfg),
            )
        except ProviderError as exc:
            raise ProviderError(f"Crossref {exc}") from exc
        items = response.json().get("message", {}).get("items", [])
        results = []
        for item in items:
            title = (item.get("title") or [""])[0]
            abstract = item.get("abstract") or ""
            abstract = re.sub(r"<[^>]+>", " ", abstract).strip()
            issued = item.get("issued", {}).get("date-parts", [[None]])[0]
            year = str(issued[0]) if issued and issued[0] else None
            results.append(
                {
                    "title": title,
                    "doi": item.get("DOI"),
                    "abstract": abstract,
                    "publish_date": year,
                    "container": (item.get("container-title") or [""])[0],
                    "type": item.get("type", ""),
                    "content_level": "abstract" if abstract else "metadata",
                    "fulltext_url": None,
                    "database": "crossref",
                }
            )
        return results


class CodexExecLLM:
    """Uses the locally logged-in Codex CLI (codex exec) as the generation provider.

    No API key is read or stored; authentication stays inside the Codex CLI's own
    credential store. Each call runs an ephemeral, read-only, user-config-isolated
    codex session and consumes the account's Codex quota.
    """

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg

    @property
    def model(self) -> str:
        return str(self.cfg.get("model") or "")

    def _cli(self) -> str | None:
        return shutil.which("codex")

    def availability(self) -> dict[str, Any]:
        enabled = bool(self.cfg.get("enabled"))
        cli = self._cli()
        reasons: list[str] = []
        if not enabled:
            reasons.append("config/providers.yaml: llm.enabled=false")
        if not cli:
            reasons.append("未找到 codex CLI（安装：npm i -g @openai/codex 并完成 codex login）")
        return {
            "available": not reasons,
            "reasons": reasons,
            "id": self.cfg.get("id", "default-llm"),
            "model": self.model or "codex 默认模型（登录套餐）",
            "base_url": "codex exec（本机 CLI，使用已登录账号）",
            "api_key_env": "",
            "send_scope": self.cfg.get("send_scope", []),
        }

    def require(self) -> None:
        status = self.availability()
        if not status["available"]:
            raise ProviderUnavailable("LLM Provider 不可用: " + "; ".join(status["reasons"]))

    def generate_json(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        temperature: float | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        self.require()
        cli = self._cli()
        scratch = Path(tempfile.mkdtemp(prefix="pebs_codex_"))
        out_file = scratch / "last_message.json"
        cmd = [
            str(cli),
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "-s",
            "read-only",
            "--color",
            "never",
            "--ignore-user-config",
            "-c",
            f"model_reasoning_effort={self.cfg.get('reasoning_effort', 'low')}",
            "-C",
            str(scratch),
            "-o",
            str(out_file),
        ]
        if self.model:
            cmd += ["-m", self.model]
        payload = f"{system}\n\n{prompt}\n\n只输出一个 JSON 对象，不要输出任何其它文字或代码块标记。"
        try:
            proc = subprocess.run(
                cmd,
                input=payload,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout or int(self.cfg.get("timeout_seconds", 240)),
            )
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(f"codex exec 超时（{task}）") from exc
        except OSError as exc:
            raise ProviderError(f"codex exec 无法启动（{task}）: {exc}") from exc
        try:
            if proc.returncode != 0:
                tail = ((proc.stderr or "") + (proc.stdout or ""))[-400:]
                raise ProviderError(f"codex exec 失败（{task}）rc={proc.returncode}: {tail}")
            text = (
                out_file.read_text(encoding="utf-8", errors="replace")
                if out_file.exists()
                else (proc.stdout or "")
            )
            parsed = _extract_json(text)
            parsed.setdefault("_usage", {})
            return parsed
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


@dataclass
class ResearchResult:
    items: list[dict[str, Any]] = field(default_factory=list)
    per_source: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


class OpenAlexResearch:
    BASE = "https://api.openalex.org/works"

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg

    def availability(self) -> dict[str, Any]:
        enabled = bool(self.cfg.get("enabled"))
        allowed = self.cfg.get("allowed_sources", [])
        reasons: list[str] = []
        if not enabled:
            reasons.append("config/providers.yaml: research.enabled=false")
        if "openalex" not in allowed:
            reasons.append("openalex 不在 allowed_sources")
        return {
            "available": not reasons,
            "reasons": reasons,
            "id": "openalex",
            "allowed_sources": ["openalex"],
        }

    def require(self) -> None:
        status = self.availability()
        if not status["available"]:
            raise ProviderUnavailable("OpenAlex 不可用: " + "; ".join(status["reasons"]))

    @staticmethod
    def _abstract(item: dict[str, Any]) -> str:
        inverted = item.get("abstract_inverted_index")
        if not inverted:
            return ""
        positions: dict[int, str] = {}
        for word, locations in inverted.items():
            for location in locations or []:
                positions[int(location)] = word
        return " ".join(positions[index] for index in sorted(positions))

    @staticmethod
    def _oa_pdf_url(item: dict[str, Any]) -> str | None:
        best = item.get("best_oa_location") or {}
        primary = item.get("primary_location") or {}
        for candidate in (best.get("pdf_url"), primary.get("pdf_url")):
            if candidate:
                return str(candidate)
        return None

    def search(self, query: str, rows: int = 5) -> list[dict[str, Any]]:
        self.require()
        params: dict[str, Any] = {"search": query, "per-page": str(rows)}
        contact = _contact(self.cfg)
        if contact:
            params["mailto"] = contact
        try:
            response = _transient_get(
                self.BASE,
                params=params,
                timeout=int(self.cfg.get("timeout_seconds", 60)),
                user_agent=_user_agent(self.cfg),
            )
        except ProviderError as exc:
            raise ProviderError(f"OpenAlex {exc}") from exc
        items = response.json().get("results", [])
        results = []
        for item in items:
            abstract = self._abstract(item)
            doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", str(item.get("doi") or "").strip()) or None
            results.append(
                {
                    "title": item.get("display_name") or "",
                    "doi": doi,
                    "abstract": abstract,
                    "publish_date": str(item.get("publication_year")) if item.get("publication_year") else None,
                    "container": ((item.get("primary_location") or {}).get("source") or {}).get("display_name") or "",
                    "type": item.get("type") or "",
                    "content_level": "abstract" if abstract else "metadata",
                    "fulltext_url": self._oa_pdf_url(item),
                    "database": "openalex",
                }
            )
        return results


class CompositeResearch:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.adapters: list[tuple[str, Any]] = []
        allowed = cfg.get("allowed_sources", [])
        if "crossref" in allowed:
            self.adapters.append(("crossref", CrossrefResearch(cfg)))
        if "openalex" in allowed:
            self.adapters.append(("openalex", OpenAlexResearch(cfg)))
        if "semantic_scholar" in allowed:
            self.adapters.append(("semantic_scholar", SemanticScholarResearch(cfg)))
        if "pubmed" in allowed:
            self.adapters.append(("pubmed", PubMedResearch(cfg)))
        self.unpaywall = UnpaywallLookup(cfg) if cfg.get("use_unpaywall", True) else None

    def sources(self) -> list[str]:
        return [name for name, _ in self.adapters]

    def availability(self) -> dict[str, Any]:
        enabled = bool(self.cfg.get("enabled"))
        reasons: list[str] = []
        if not enabled:
            reasons.append("config/providers.yaml: research.enabled=false")
        if not self.adapters:
            reasons.append("allowed_sources 未配置可用来源（crossref/openalex）")
        return {
            "available": not reasons,
            "reasons": reasons,
            "id": self.cfg.get("id", "default-research"),
            "allowed_sources": self.sources(),
        }

    def require(self) -> None:
        status = self.availability()
        if not status["available"]:
            raise ProviderUnavailable("研究 Provider 不可用: " + "; ".join(status["reasons"]))

    def search(self, query: str, rows: int = 5) -> ResearchResult:
        items: list[dict[str, Any]] = []
        per_source: dict[str, int] = {}
        errors: dict[str, str] = {}
        for name, adapter in self.adapters:
            try:
                found = adapter.search(query, rows=rows)
            except (ProviderUnavailable, ProviderError) as exc:
                errors[name] = str(exc)
                continue
            per_source[name] = len(found)
            items.extend(found)
        return ResearchResult(items=merge_research_items([], items), per_source=per_source, errors=errors)

    def find_fulltext(self, doi: str) -> str | None:
        if not self.unpaywall or not doi:
            return None
        try:
            return self.unpaywall.find_pdf(doi)
        except (ProviderUnavailable, ProviderError):
            return None

    def fetch_fulltext(self, url: str, *, max_bytes: int | None = None) -> str:
        limit = max_bytes or int(self.cfg.get("fulltext_max_mib", 5)) * 1024 * 1024
        return fetch_pdf_text(
            url,
            max_bytes=limit,
            timeout=int(self.cfg.get("timeout_seconds", 60)),
            user_agent=_user_agent(self.cfg),
        )


def _extract_pdf_text(data: bytes) -> str:
    import logging

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ProviderError("pypdf 未安装，无法解析全文 PDF") from exc
    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in reader.pages[:30]:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text)
    joined = "\n".join(parts)
    if not joined.strip():
        raise ProviderError("PDF 未提取到文本（可能是扫描件）")
    return joined


def fetch_pdf_text(
    url: str,
    *,
    max_bytes: int = 5 * 1024 * 1024,
    timeout: int = 60,
    user_agent: str = "pebs-m1/0.1",
) -> str:
    if not re.match(r"^https?://", url or ""):
        raise ProviderError("仅支持 http(s) 全文链接")
    chunks: list[bytes] = []
    total = 0
    try:
        with httpx.stream(
            "GET", url, timeout=timeout, follow_redirects=True, headers={"User-Agent": user_agent}
        ) as response:
            if response.status_code >= 400:
                raise ProviderError(f"全文下载失败: HTTP {response.status_code}")
            content_type = str(response.headers.get("Content-Type") or "").lower()
            if content_type and "pdf" not in content_type and "octet-stream" not in content_type:
                raise ProviderError(f"MIME 检查失败: {content_type}")
            length = str(response.headers.get("Content-Length") or "")
            if length.isdigit() and int(length) > max_bytes:
                raise ProviderError("全文超过大小限制")
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise ProviderError("全文超过大小限制")
                chunks.append(chunk)
    except httpx.HTTPError as exc:
        raise ProviderError(f"全文下载失败: {exc}") from exc
    data = b"".join(chunks)
    if not data.startswith(b"%PDF"):
        raise ProviderError("不是 PDF 文件（magic check 失败）")
    return _extract_pdf_text(data)


class SemanticScholarResearch:
    BASE = "https://api.semanticscholar.org/graph/v1/paper/search"

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg

    def availability(self) -> dict[str, Any]:
        enabled = bool(self.cfg.get("enabled"))
        allowed = self.cfg.get("allowed_sources", [])
        reasons: list[str] = []
        if not enabled:
            reasons.append("config/providers.yaml: research.enabled=false")
        if "semantic_scholar" not in allowed:
            reasons.append("semantic_scholar 不在 allowed_sources")
        return {
            "available": not reasons,
            "reasons": reasons,
            "id": "semantic_scholar",
            "allowed_sources": ["semantic_scholar"],
        }

    def require(self) -> None:
        status = self.availability()
        if not status["available"]:
            raise ProviderUnavailable("Semantic Scholar 不可用: " + "; ".join(status["reasons"]))

    def search(self, query: str, rows: int = 5) -> list[dict[str, Any]]:
        self.require()
        params = {
            "query": query,
            "limit": str(rows),
            "fields": "title,abstract,year,venue,externalIds,openAccessPdf,publicationTypes",
        }
        key_env = str(self.cfg.get("api_key_env") or "")
        headers = {}
        if key_env and os.environ.get(key_env):
            headers["x-api-key"] = os.environ[key_env]
        try:
            response = _transient_get(
                self.BASE,
                params=params,
                timeout=int(self.cfg.get("timeout_seconds", 60)),
                user_agent=_user_agent(self.cfg),
                extra_headers=headers,
            )
        except ProviderError as exc:
            raise ProviderError(f"Semantic Scholar {exc}") from exc
        items = response.json().get("data", [])
        results = []
        for item in items:
            abstract = item.get("abstract") or ""
            external = item.get("externalIds") or {}
            pdf = (item.get("openAccessPdf") or {}).get("url")
            types = item.get("publicationTypes") or []
            results.append(
                {
                    "title": item.get("title") or "",
                    "doi": external.get("DOI"),
                    "abstract": abstract,
                    "publish_date": str(item.get("year")) if item.get("year") else None,
                    "container": item.get("venue") or "",
                    "type": types[0].lower() if types else "",
                    "content_level": "abstract" if abstract else "metadata",
                    "fulltext_url": pdf,
                    "database": "semantic_scholar",
                }
            )
        return results


class PubMedResearch:
    ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg

    def availability(self) -> dict[str, Any]:
        enabled = bool(self.cfg.get("enabled"))
        allowed = self.cfg.get("allowed_sources", [])
        reasons: list[str] = []
        if not enabled:
            reasons.append("config/providers.yaml: research.enabled=false")
        if "pubmed" not in allowed:
            reasons.append("pubmed 不在 allowed_sources")
        return {"available": not reasons, "reasons": reasons, "id": "pubmed", "allowed_sources": ["pubmed"]}

    def require(self) -> None:
        status = self.availability()
        if not status["available"]:
            raise ProviderUnavailable("PubMed 不可用: " + "; ".join(status["reasons"]))

    def search(self, query: str, rows: int = 5) -> list[dict[str, Any]]:
        self.require()
        base_params: dict[str, Any] = {"db": "pubmed", "tool": "pebs", "retmode": "json"}
        contact = _contact(self.cfg)
        if contact:
            base_params["email"] = contact
        try:
            search_response = _transient_get(
                self.ESEARCH,
                params={**base_params, "term": query, "retmax": str(rows), "sort": "relevance"},
                timeout=int(self.cfg.get("timeout_seconds", 60)),
                user_agent=_user_agent(self.cfg),
            )
        except ProviderError as exc:
            raise ProviderError(f"PubMed esearch {exc}") from exc
        try:
            ids = search_response.json().get("esearchresult", {}).get("idlist", [])
        except ValueError as exc:
            raise ProviderError(f"PubMed esearch 响应解析失败: {exc}") from exc
        if not ids:
            return []
        try:
            fetch_response = _transient_get(
                self.EFETCH,
                params={**base_params, "id": ",".join(ids), "rettype": "abstract", "retmode": "xml"},
                timeout=int(self.cfg.get("timeout_seconds", 60)),
                user_agent=_user_agent(self.cfg),
            )
        except ProviderError as exc:
            raise ProviderError(f"PubMed efetch {exc}") from exc
        return self._parse_efetch(fetch_response.text)

    @staticmethod
    def _parse_efetch(xml_text: str) -> list[dict[str, Any]]:
        import xml.etree.ElementTree as ET

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise ProviderError(f"PubMed XML 解析失败: {exc}") from exc
        results = []
        for article in root.findall(".//PubmedArticle"):
            title = "".join(article.find(".//ArticleTitle").itertext()) if article.find(".//ArticleTitle") is not None else ""
            abstract_parts = []
            for node in article.findall(".//Abstract/AbstractText"):
                label = node.get("Label")
                text = "".join(node.itertext())
                abstract_parts.append(f"{label}: {text}" if label else text)
            abstract = "\n".join(part for part in abstract_parts if part.strip())
            journal = article.findtext(".//Journal/Title") or ""
            year = article.findtext(".//JournalIssue/PubDate/Year") or article.findtext(".//JournalIssue/PubDate/MedlineDate") or ""
            doi = None
            for article_id in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
                if article_id.get("IdType") == "doi":
                    doi = (article_id.text or "").strip()
                    break
            results.append(
                {
                    "title": title.strip(),
                    "doi": doi,
                    "abstract": abstract.strip(),
                    "publish_date": year.strip() or None,
                    "container": journal.strip(),
                    "type": "journal-article",
                    "content_level": "abstract" if abstract.strip() else "metadata",
                    "fulltext_url": None,
                    "database": "pubmed",
                }
            )
        return results


class UnpaywallLookup:
    BASE = "https://api.unpaywall.org/v2/"

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg

    def availability(self) -> dict[str, Any]:
        enabled = bool(self.cfg.get("enabled")) and bool(self.cfg.get("use_unpaywall", True))
        contact = _contact(self.cfg)
        reasons: list[str] = []
        if not enabled:
            reasons.append("research.enabled=false 或 use_unpaywall=false")
        if not contact:
            reasons.append("research.contact_email 未配置（Unpaywall 必需）")
        return {"available": not reasons, "reasons": reasons, "id": "unpaywall"}

    def require(self) -> None:
        status = self.availability()
        if not status["available"]:
            raise ProviderUnavailable("Unpaywall 不可用: " + "; ".join(status["reasons"]))

    def find_pdf(self, doi: str) -> str | None:
        self.require()
        from urllib.parse import quote

        url = self.BASE + quote(doi, safe="")
        try:
            response = httpx.get(
                url,
                params={"email": _contact(self.cfg)},
                timeout=int(self.cfg.get("timeout_seconds", 60)),
                headers={"User-Agent": _user_agent(self.cfg)},
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"Unpaywall 请求失败: {exc}") from exc
        if response.status_code == 404:
            return None
        if response.status_code in TRANSIENT_STATUS:
            raise ProviderError(f"Unpaywall HTTP {response.status_code}")
        if response.status_code >= 400:
            raise ProviderError(f"Unpaywall HTTP {response.status_code}")
        data = response.json()
        best = data.get("best_oa_location") or {}
        pdf_url = best.get("url_for_pdf")
        if pdf_url:
            return str(pdf_url)
        for location in data.get("oa_locations", []) or []:
            if location.get("url_for_pdf"):
                return str(location["url_for_pdf"])
        return None


def get_llm() -> OpenAICompatLLM | CodexExecLLM:
    cfg = config.PROVIDERS.get("llm", {})
    if str(cfg.get("kind", "openai_compatible")).strip() == "codex_exec":
        return CodexExecLLM(cfg)
    return OpenAICompatLLM(cfg)


def get_research() -> CompositeResearch:
    return CompositeResearch(config.PROVIDERS.get("research", {}))


def provider_status() -> dict[str, Any]:
    from . import profiles

    llm = get_llm().availability()
    research = get_research().availability()
    profile = profiles.load_research_profile("psychology")
    implemented = profiles.implemented_sources(profile)
    unimplemented = profiles.unimplemented_sources(profile)
    configured = list(research.get("allowed_sources", []))
    unsupported = profiles.validate_configured_sources(profile, configured)
    research["profile"] = {
        "name": profile.get("profile", "psychology"),
        "implemented": implemented,
        "unimplemented": [item.get("id") for item in unimplemented],
        "unsupported_configured": unsupported,
    }
    return {"llm": llm, "research": research}
