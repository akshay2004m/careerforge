from unittest.mock import patch

from app.services.parser import parse_resume


class TestResumeParser:
    def test_parse_resume_returns_text(self, tmp_path):
        # Create a simple text file to simulate PDF (for basic test)
        # fitz (PyMuPDF) can read text files just fine
        test_file = tmp_path / "test_resume.txt"
        test_file.write_text("Python Developer with 3 years experience in FastAPI and Docker.")

        # Note: For real PDF testing, you should use a sample PDF file
        text, parsed_data = parse_resume(str(test_file))

        assert isinstance(text, str)
        assert len(text) > 0
        assert "python" in text.lower() or "fastapi" in text.lower()

    def test_parse_resume_structure(self, tmp_path):
        test_file = tmp_path / "resume.txt"
        test_file.write_text("""
        John Doe
        Experience:
        - Software Engineer at TechCorp (2021-2024)
        Skills: Python, FastAPI, SQL
        """)

        text, data = parse_resume(str(test_file))

        assert "status" in data
        assert data["status"] == "parsed"


class TestParserDeep:
    @patch("app.services.parser.fitz.open")
    def test_parse_pdf_mocked(self, mock_fitz_open, tmp_path):
        class MockPage:
            def get_text(self):
                return "Mocked PDF text with Python and FastAPI."

        class MockDocument:
            def __init__(self):
                self.page_count = 1
                self.metadata = {}

            def __len__(self):
                return self.page_count

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

            def __iter__(self):
                yield MockPage()

        mock_fitz_open.return_value = MockDocument()

        test_file = tmp_path / "mock.pdf"
        test_file.write_bytes(b"%PDF-1.4\n")

        text, data = parse_resume(str(test_file))
        assert "mocked pdf text" in text.lower()
