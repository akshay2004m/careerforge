import fitz  # PyMuPDF
import pdfplumber

def parse_resume(file_path: str):
    # Extract text using PyMuPDF
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()

    # Better structured parsing with pdfplumber
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""

    # Simple parsing (you can improve this later)
    parsed_data = {
        "raw_text": text,
        "skills": [],  # TODO: Add skill extraction
        "experience": [],
        "education": []
    }
    
    return text, parsed_data