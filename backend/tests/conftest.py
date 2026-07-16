import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# backend/ on path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Use in-memory SQLite for testing
TEST_DATABASE_URL = "sqlite:///./test.db"

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("CHROMA_ENABLED", "false")
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)

from app.core.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import models  # noqa: F401, E402


@pytest.fixture(scope="function")
def test_engine():
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(test_engine):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def auth_headers(client):
    payload = {
        "name": "Test User",
        "email": "test_user_conftest@example.com",
        "password": "securepass1",
    }
    r = client.post("/api/auth/signup", json=payload)
    if r.status_code == 400:
        r = client.post(
            "/api/auth/login",
            json={"email": payload["email"], "password": payload["password"]},
        )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def mock_parser(monkeypatch):
    """Mock the PDF parsing so we don't need real PDFs for router tests."""

    def fake_parse(file_path: str):
        text = "This is a mock resume text for a Software Engineer."
        parsed_data = {
            "skills": ["Python", "FastAPI", "React"],
            "experience": ["Software Engineer at TechCorp"],
        }
        return text, parsed_data

    # only mock if the path ends with .pdf to avoid intercepting our real parser tests using .txt
    original_parse = None
    try:
        from app.services.parser import parse_resume

        original_parse = parse_resume
    except ImportError:
        pass

    def conditional_parse(file_path: str):
        if str(file_path).endswith(".pdf"):
            return fake_parse(file_path)
        return original_parse(file_path)

    monkeypatch.setattr("app.routers.resume.parse_resume", conditional_parse)
