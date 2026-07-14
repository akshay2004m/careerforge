import logging

import fitz

from app.core.exceptions import ResumeParseError

logger = logging.getLogger("careerforge.parser")


def parse_resume(file_path: str):
    """
    Parses a PDF resume and extracts text and basic structured data.
    """
    text = ""
    page_count = 0
    try:
        with fitz.open(file_path) as doc:
            page_count = len(doc)
            for page in doc:
                text += page.get_text()
    except Exception as e:
        logger.error(f"Failed to parse PDF {file_path}: {e}")
        raise ResumeParseError(
            f"Could not read the PDF file. It might be corrupted or password-protected. Details: {e}"
        )

    text = text.strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    parsed_data = {
        "status": "parsed" if text else "empty",
        "extracted_length": len(text),
        "page_count": page_count,
        "line_count": len(lines),
        "preview": text[:200] if text else "",
    }

    return text, parsed_data
