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
