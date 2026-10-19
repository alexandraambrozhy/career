"""Извлечение текста из резюме (PDF, DOCX, TXT)."""
import io

MAX_CHARS = 30_000


def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif name.endswith(".docx"):
        from docx import Document

        doc = Document(io.BytesIO(data))
        text = "\n".join(p.text for p in doc.paragraphs)
    elif name.endswith((".txt", ".md", ".rtf")):
        text = data.decode("utf-8", errors="ignore")
    else:
        raise ValueError("Поддерживаются PDF, DOCX и TXT")
    return text.strip()[:MAX_CHARS]
