import difflib
import hashlib
from pathlib import Path
from uuid import UUID

import fitz  # PyMuPDF
from docx import Document as DocxDocument
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Document, DocumentVersion, DocStatus
from app.core.exceptions import NotFoundException

settings = get_settings()


def compute_file_hash(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_pdf(file_path: str) -> list[dict]:
    sections = []
    doc = fitz.open(file_path)
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text()
        if text.strip():
            sections.append({
                "content": text,
                "metadata": {"page": page_num, "source": "pdf"},
            })
    doc.close()
    return sections


def parse_docx(file_path: str) -> list[dict]:
    sections = []
    doc = DocxDocument(file_path)
    current_section = ""
    current_heading = ""

    for para in doc.paragraphs:
        if para.style.name.startswith("Heading"):
            if current_section.strip():
                sections.append({
                    "content": current_section.strip(),
                    "metadata": {"heading": current_heading, "source": "docx"},
                })
            current_heading = para.text
            current_section = para.text + "\n"
        else:
            current_section += para.text + "\n"

    if current_section.strip():
        sections.append({
            "content": current_section.strip(),
            "metadata": {"heading": current_heading, "source": "docx"},
        })

    return sections


def parse_markdown(file_path: str) -> list[dict]:
    sections = []
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    current_section = ""
    current_heading = ""

    for line in content.split("\n"):
        if line.startswith("#"):
            if current_section.strip():
                sections.append({
                    "content": current_section.strip(),
                    "metadata": {"heading": current_heading, "source": "markdown"},
                })
            current_heading = line.lstrip("#").strip()
            current_section = line + "\n"
        else:
            current_section += line + "\n"

    if current_section.strip():
        sections.append({
            "content": current_section.strip(),
            "metadata": {"heading": current_heading, "source": "markdown"},
        })

    return sections


def parse_document(file_path: str, file_type: str) -> list[dict]:
    parsers = {
        "pdf": parse_pdf,
        "docx": parse_docx,
        "md": parse_markdown,
    }
    parser = parsers.get(file_type)
    if not parser:
        raise ValueError(f"Unsupported file type: {file_type}")
    sections = parser(file_path)
    if not sections:
        raise ValueError(f"Document is empty or could not be parsed: {file_path}")
    return sections


async def save_uploaded_file(file_content: bytes, filename: str, kb_id: UUID) -> str:
    upload_dir = Path(settings.upload_dir) / str(kb_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / filename
    with open(file_path, "wb") as f:
        f.write(file_content)

    return str(file_path)



async def get_document_or_404(document_id: UUID, db: AsyncSession) -> Document:
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundException("Document not found")
    return doc


def extract_text_content(file_path: str, file_type: str) -> str:
    try:
        sections = parse_document(file_path, file_type)
        return "\n\n".join(s["content"] for s in sections)
    except Exception:
        return ""


async def save_version_snapshot(doc: Document, db: AsyncSession, change_summary: str = "") -> DocumentVersion:
    content_snapshot = extract_text_content(doc.file_path, doc.file_type)

    version = DocumentVersion(
        document_id=doc.id,
        version_number=doc.version,
        file_path=doc.file_path,
        file_hash=doc.file_hash,
        content_snapshot=content_snapshot,
        change_summary=change_summary,
        uploaded_by=doc.uploaded_by,
    )
    db.add(version)
    await db.flush()
    return version


def compute_diff(text_a: str, text_b: str) -> list[dict]:
    lines_a = text_a.splitlines(keepends=True)
    lines_b = text_b.splitlines(keepends=True)

    diff_result = []
    matcher = difflib.SequenceMatcher(None, lines_a, lines_b)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for idx, line in enumerate(lines_a[i1:i2]):
                diff_result.append({"type": "context", "line": line.rstrip("\n"), "line_number": i1 + idx + 1})
        elif tag == "delete":
            for idx, line in enumerate(lines_a[i1:i2]):
                diff_result.append({"type": "remove", "line": line.rstrip("\n"), "line_number": i1 + idx + 1})
        elif tag == "insert":
            for idx, line in enumerate(lines_b[j1:j2]):
                diff_result.append({"type": "add", "line": line.rstrip("\n"), "line_number": j1 + idx + 1})
        elif tag == "replace":
            for idx, line in enumerate(lines_a[i1:i2]):
                diff_result.append({"type": "remove", "line": line.rstrip("\n"), "line_number": i1 + idx + 1})
            for idx, line in enumerate(lines_b[j1:j2]):
                diff_result.append({"type": "add", "line": line.rstrip("\n"), "line_number": j1 + idx + 1})
    return diff_result
