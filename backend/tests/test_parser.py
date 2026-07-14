import os
import tempfile

import fitz
import pytest

from app.core.exceptions import ResumeParseError
from app.services.parser import parse_resume


def test_parse_resume_success():
    """Test parsing a valid PDF resume."""
    # Create a temporary PDF file path
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(tmp_fd)  # Close it so fitz can write to it on Windows

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "John Doe\nSoftware Engineer\nPython, Java")
    doc.save(tmp_path)
    doc.close()

    try:
        text, parsed_data = parse_resume(tmp_path)
        assert text.startswith("John Doe")
        assert "Software Engineer" in text
        assert parsed_data["status"] == "parsed"
        assert parsed_data["page_count"] == 1
        assert parsed_data["line_count"] > 0
    finally:
        os.remove(tmp_path)


def test_parse_resume_empty_or_invalid():
    """Test parsing an invalid or non-existent PDF."""
    with pytest.raises(ResumeParseError):
        parse_resume("non_existent_file.pdf")
