"""Extract bounded, assessment-ready evidence from submitted artifacts."""

from __future__ import annotations

import base64
import io
import mimetypes
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


_TEXT_SUFFIXES = {
    ".md", ".txt", ".rst", ".csv", ".tsv", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".xml", ".html", ".htm", ".py", ".js",
    ".ts", ".tsx", ".jsx", ".java", ".c", ".h", ".cpp", ".cs", ".go",
    ".rs", ".sql", ".sh", ".ps1", ".css", ".scss", ".vue",
}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
_OFFICE_SUFFIXES = {".docx", ".odt", ".pptx", ".xlsx"}
_LEGACY_OFFICE_SUFFIXES = {".doc", ".ppt", ".xls"}
_VISUAL_DOCUMENT_SUFFIXES = {".pdf", ".docx", ".odt", ".pptx", ".xlsx"}
_MAX_PDF_PAGES = 6
_MAX_IMAGE_BYTES = 1_500_000


@dataclass(frozen=True)
class VisualEvidence:
    """A safely bounded image supplied as supplementary report evidence."""

    label: str
    mime_type: str
    data: bytes

    def data_url(self) -> str:
        encoded = base64.b64encode(self.data).decode("ascii")
        return f"data:{self.mime_type};base64,{encoded}"


def _xml_text(raw: bytes, members: list[str]) -> str:
    parts: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for name in members:
                if name not in archive.namelist():
                    continue
                root = ET.fromstring(archive.read(name))
                lines: list[str] = []
                for node in root.iter():
                    tag = node.tag.rsplit("}", 1)[-1]
                    if tag == "t" and node.text:
                        lines.append(node.text)
                    elif tag in {"tab", "tabStop"}:
                        lines.append("\t")
                    elif tag in {"br", "cr", "p", "tr"}:
                        lines.append("\n")
                text = "".join(lines)
                if text.strip():
                    parts.append(text)
    except (ET.ParseError, OSError, ValueError, zipfile.BadZipFile):
        return ""
    return "\n\n".join(parts)


def _office_text(raw: bytes, suffix: str) -> str:
    if suffix == ".docx":
        return _xml_text(raw, ["word/document.xml"])
    if suffix == ".odt":
        return _xml_text(raw, ["content.xml"])
    if suffix == ".pptx":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                slides = sorted(
                    name for name in archive.namelist()
                    if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
                )
        except (OSError, ValueError, zipfile.BadZipFile):
            return ""
        return _xml_text(raw, slides)
    if suffix == ".xlsx":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                members = ["xl/sharedStrings.xml"] + sorted(
                    name for name in archive.namelist()
                    if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
                )
        except (OSError, ValueError, zipfile.BadZipFile):
            return ""
        return _xml_text(raw, members)
    return ""


def _legacy_office_text(raw: bytes) -> str:
    """Best-effort extraction for old binary Office documents."""
    unicode_chunks = re.findall(rb"(?:[\x20-\x7e\x80-\xff]\x00){4,}", raw)
    ansi_chunks = re.findall(rb"[\x20-\x7e]{8,}", raw)
    chunks = [chunk.decode("utf-16-le", errors="ignore") for chunk in unicode_chunks]
    decoded = raw.decode("utf-16-le", errors="ignore")
    chunks.extend(re.findall(r"[^\x00-\x1f]{4,}", decoded))
    chunks.extend(chunk.decode("gb18030", errors="ignore") for chunk in ansi_chunks)
    cleaned: list[str] = []
    for chunk in chunks:
        text = " ".join(chunk.split())
        if text and text not in cleaned:
            cleaned.append(text)
    return "\n".join(cleaned)


def _rtf_text(raw: bytes) -> str:
    text = raw.decode("latin-1", errors="ignore")
    text = re.sub(r"\\'[0-9a-fA-F]{2}", " ", text)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", " ", text)
    return " ".join(text.replace("{", " ").replace("}", " ").split())


def _pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n\n".join(
            page.extract_text() or "" for page in reader.pages[:_MAX_PDF_PAGES]
        )
    except Exception:
        return ""


def extract_document_text(path: Path, max_chars: int = 16_000) -> str:
    """Extract text/table cells without treating binary document bytes as text."""
    suffix = path.suffix.lower()
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    if suffix in _TEXT_SUFFIXES:
        text = raw.decode("utf-8", errors="replace")
    elif suffix in _OFFICE_SUFFIXES:
        text = _office_text(raw, suffix)
    elif suffix in _LEGACY_OFFICE_SUFFIXES:
        text = "[旧版 Office 文档，以下为尽力提取的文字]\n" + _legacy_office_text(raw)
    elif suffix == ".pdf":
        text = _pdf_text(path)
    elif suffix == ".rtf":
        text = _rtf_text(raw)
    else:
        return ""
    text = text.strip()
    return text[:max_chars] + ("\n...[内容已截断]..." if len(text) > max_chars else "")


def _zip_images(path: Path, prefix: str) -> list[tuple[str, bytes]]:
    try:
        with zipfile.ZipFile(path) as archive:
            return [
                (name, archive.read(name))
                for name in archive.namelist()
                if name.startswith(prefix) and Path(name).suffix.lower() in _IMAGE_SUFFIXES
            ]
    except (OSError, ValueError, zipfile.BadZipFile):
        return []


def _pdf_page_images(path: Path, max_images: int) -> list[tuple[str, bytes]]:
    """Render PDF pages, including vector charts and tables, for Kimi vision."""
    try:
        import fitz  # PyMuPDF

        document = fitz.open(path)
        images: list[tuple[str, bytes]] = []
        for page_number in range(min(len(document), _MAX_PDF_PAGES, max_images)):
            pixmap = document[page_number].get_pixmap(
                matrix=fitz.Matrix(1.25, 1.25), alpha=False
            )
            images.append((f"{path.name} 第 {page_number + 1} 页", pixmap.tobytes("png")))
        document.close()
        return images
    except Exception:
        return []


def _normalise_image(raw: bytes, suffix: str) -> tuple[str, bytes] | None:
    mime_type = mimetypes.guess_type(f"image{suffix}")[0] or "image/png"
    if len(raw) <= _MAX_IMAGE_BYTES and mime_type in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
        return mime_type, raw
    try:
        from PIL import Image

        with Image.open(io.BytesIO(raw)) as image:
            image.thumbnail((1600, 1600))
            if image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=82, optimize=True)
            compressed = output.getvalue()
            if len(compressed) <= _MAX_IMAGE_BYTES:
                return "image/jpeg", compressed
    except Exception:
        return None
    return None


def collect_visual_evidence(root: str | Path, max_images: int = 4) -> list[VisualEvidence]:
    """Collect a small, bounded set of uploaded figures and report charts."""
    base = Path(root)
    if not base.exists() or max_images <= 0:
        return []
    candidates: list[tuple[str, bytes]] = []
    paths = sorted(
        (path for path in base.rglob("*") if path.is_file()),
        key=lambda item: (
            0 if item.suffix.lower() in _VISUAL_DOCUMENT_SUFFIXES else 1,
            str(item).lower(),
        ),
    )
    for path in paths:
        suffix = path.suffix.lower()
        rel = path.relative_to(base).as_posix()
        if suffix in _IMAGE_SUFFIXES:
            try:
                candidates.append((rel, path.read_bytes()))
            except OSError:
                continue
        elif suffix == ".pdf":
            candidates.extend(_pdf_page_images(path, max_images - len(candidates)))
        elif suffix == ".docx":
            candidates.extend((f"{rel}: {name}", raw) for name, raw in _zip_images(path, "word/media/"))
        elif suffix == ".pptx":
            candidates.extend((f"{rel}: {name}", raw) for name, raw in _zip_images(path, "ppt/media/"))
        elif suffix == ".xlsx":
            candidates.extend((f"{rel}: {name}", raw) for name, raw in _zip_images(path, "xl/media/"))
        elif suffix == ".odt":
            candidates.extend((f"{rel}: {name}", raw) for name, raw in _zip_images(path, "Pictures/"))
        if len(candidates) >= max_images:
            break
    evidence: list[VisualEvidence] = []
    for label, raw in candidates[:max_images]:
        normalised = _normalise_image(raw, Path(label).suffix.lower())
        if normalised is not None:
            mime_type, data = normalised
            evidence.append(VisualEvidence(label=label, mime_type=mime_type, data=data))
    return evidence
