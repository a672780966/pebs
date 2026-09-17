from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

COMMON_PATHS = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/usr/bin/soffice",
    "/usr/local/bin/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
]


def find_renderer() -> str:
    for candidate in ("soffice", "libreoffice"):
        found = shutil.which(candidate)
        if found:
            return found
    for path in COMMON_PATHS:
        if Path(path).exists():
            return path
    for candidate in ("POWERPNT", "POWERPNT.EXE"):
        found = shutil.which(candidate)
        if found:
            return found
    return ""


def render_pptx_to_png(pptx_path: Path, output_dir: Path, *, timeout: int = 180) -> dict[str, Any]:
    renderer = find_renderer()
    if not renderer:
        raise RuntimeError("未检测到 LibreOffice/PowerPoint 渲染器")
    pptx_path = Path(pptx_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if "soffice" in renderer.lower() or "libreoffice" in renderer.lower():
        command = [
            renderer,
            "--headless",
            "--norestore",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(pptx_path),
        ]
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"LibreOffice 渲染超时：{exc}") from exc
        pdf_path = output_dir / f"{pptx_path.stem}.pdf"
        if proc.returncode != 0 or not pdf_path.exists():
            tail = ((proc.stderr or "") + (proc.stdout or ""))[-300:]
            raise RuntimeError(f"LibreOffice 渲染失败：{tail}")
    else:
        raise RuntimeError(f"渲染器 {renderer} 暂不支持自动转 PDF")
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    thumbs: list[str] = []
    for index in range(len(pdf)):
        page = pdf[index]
        bitmap = page.render(scale=1.6)
        image_path = output_dir / f"slide{index + 1}.png"
        bitmap.to_pil().save(str(image_path))
        thumbs.append(str(image_path))
    pdf.close()
    return {"renderer": renderer, "pdf": str(pdf_path), "thumbnails": thumbs, "slides": len(thumbs)}
