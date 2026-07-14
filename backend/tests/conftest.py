"""Pytest fixtures — isolated SQLite DB per test session."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# backend/ on path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("CHROMA_ENABLED", "false")
os.environ.setdefault("DATABASE_URL", "sqlite://")

from app.core.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import models  # noqa: F401, E402


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def client(db_engine):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client):
    payload = {
        "name": "Test User",
        "email": "test_user@example.com",
        "password": "securepass1",
    }
    r = client.post("/api/auth/signup", json=payload)
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
            "experience": ["Software Engineer at TechCorp"]
        }
        return text, parsed_data
    monkeypatch.setattr("app.routers.resume.parse_resume", fake_parse)
