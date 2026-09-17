from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from . import config


class ParseError(Exception):
    pass


MAX_FILE_BYTES = int(config.RULES.get("limits", {}).get("max_file_mib", 25)) * 1024 * 1024
MAX_FILES = int(config.RULES.get("limits", {}).get("max_files_per_import", 20))
MAX_TOTAL_BYTES = int(config.RULES.get("limits", {}).get("max_total_mib", 100)) * 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_import_limits(paths: list[Path]) -> list[str]:
    warnings: list[str] = []
    if len(paths) > MAX_FILES:
        raise ParseError(f"一次导入最多 {MAX_FILES} 个文件，当前 {len(paths)} 个")
    total = 0
    for path in paths:
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise ParseError(f"文件超过 {MAX_FILE_BYTES // (1024 * 1024)} MiB: {path.name}")
        total += size
    if total > MAX_TOTAL_BYTES:
        raise ParseError(f"导入总量超过 {MAX_TOTAL_BYTES // (1024 * 1024)} MiB")
    return warnings


def _docx_text(path: Path) -> tuple[str, list[str]]:
    import docx

    warnings: list[str] = []
    document = docx.Document(str(path))
    parts = [p.text for p in document.paragraphs if p.text and p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    if not parts:
        warnings.append("DOCX 中未提取到文本，可能是扫描件或空文档")
    return "\n".join(parts), warnings


def _pdf_text(path: Path) -> tuple[str, list[str]]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "", ["PDF 解析库未安装（pypdf），该文件未解析，不计为已读取"]
    warnings: list[str] = []
    reader = PdfReader(str(path))
    parts: list[str] = []
    empty_pages = 0
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text)
        else:
            empty_pages += 1
    if empty_pages:
        warnings.append(f"{empty_pages} 页未提取到文本（可能是扫描页），这些页面未计为已读取")
    return "\n".join(parts), warnings


def extract_text(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md", ".markdown"):
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
            warnings: list[str] = []
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
            warnings = ["非 UTF-8 编码，已按替换字符解码"]
        if suffix in (".md", ".markdown"):
            kind = "markdown"
        else:
            kind = "txt"
    elif suffix == ".docx":
        text, warnings = _docx_text(path)
        kind = "docx"
    elif suffix == ".pdf":
        text, warnings = _pdf_text(path)
        kind = "pdf"
    else:
        raise ParseError(f"不支持的材料格式: {suffix or path.name}")
    return {
        "path": str(path),
        "kind": kind,
        "text": text,
        "sha256": sha256_file(path),
        "chars": len(text),
        "content_level": "full_text" if text.strip() else "metadata",
        "warnings": warnings,
    }


def _parse_docx_template(path: Path) -> dict[str, Any]:
    import docx

    document = docx.Document(str(path))
    columns: list[dict[str, Any]] = []
    warnings: list[str] = []
    headings: list[str] = []
    for para in document.paragraphs:
        if para.text.strip() and para.style and para.style.name and para.style.name.lower().startswith("heading"):
            headings.append(para.text.strip())
    if document.tables:
        table = document.tables[0]
        if table.rows:
            header = [cell.text.strip() for cell in table.rows[0].cells]
            for order, name in enumerate(header):
                if name:
                    columns.append({"name": name, "order": order, "required": True, "notes": ""})
        if len(document.tables) > 1:
            warnings.append(f"模板含 {len(document.tables)} 个表格，M1 仅解析第一个表格结构")
    else:
        warnings.append("DOCX 中未找到表格，模板栏目结构未解析")
    word_min, word_max = _word_range_from_text("\n".join(p.text for p in document.paragraphs))
    spec = {
        "kind": "docx_table",
        "path": str(path),
        "sha256": sha256_file(path),
        "columns": columns,
        "section_headings": headings,
        "terminology_rules": _terminology_from_text("\n".join(p.text for p in document.paragraphs)),
        "parse_warnings": warnings,
    }
    if word_min and word_max:
        spec["word_min"] = word_min
        spec["word_max"] = word_max
    return spec


def _parse_md_template(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    columns: list[dict[str, Any]] = []
    warnings: list[str] = []
    headings = [m.group(1).strip() for m in re.finditer(r"^#{1,4}\s+(.+)$", text, flags=re.M)]
    table_match = re.search(r"^\|(.+)\|\s*$\n^\|[-:\s|]+\|\s*$", text, flags=re.M)
    if table_match:
        header = [c.strip() for c in table_match.group(1).split("|")]
        for order, name in enumerate(header):
            if name:
                columns.append({"name": name, "order": order, "required": True, "notes": ""})
    else:
        warnings.append("Markdown 中未找到表格表头，栏目结构未解析")
    word_min, word_max = _word_range_from_text(text)
    spec = {
        "kind": "markdown",
        "path": str(path),
        "sha256": sha256_file(path),
        "columns": columns,
        "section_headings": headings,
        "terminology_rules": _terminology_from_text(text),
        "parse_warnings": warnings,
    }
    if word_min and word_max:
        spec["word_min"] = word_min
        spec["word_max"] = word_max
    return spec


def _terminology_from_text(text: str) -> list[str]:
    rules: list[str] = []
    for match in re.finditer(r"称谓[^。\n]{0,30}[「“\"]([^」”\"]+)[」”\"]", text):
        rules.append(match.group(1))
    for match in re.finditer(r"统一(?:使用|用)[「“\"]([^」”\"]+)[」”\"]", text):
        rules.append(match.group(1))
    return sorted(set(rules))


def _word_range_from_text(text: str) -> tuple[int | None, int | None]:
    match = re.search(r"(\d{2,5})\s*[-–—~至]\s*(\d{2,5})\s*字", text)
    if not match:
        return None, None
    lo, hi = int(match.group(1)), int(match.group(2))
    return min(lo, hi), max(lo, hi)


def parse_template(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _parse_docx_template(path)
    if suffix in (".md", ".markdown", ".txt"):
        return _parse_md_template(path)
    raise ParseError(f"不支持的模板格式: {suffix or path.name}")
