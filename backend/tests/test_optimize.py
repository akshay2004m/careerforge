from unittest.mock import patch


def _seed_resume(client, headers, text="Engineer resume with Python FastAPI AWS SQL experience."):
    # Bypass PDF upload — insert via optimize dependency by mocking DB would be heavy;
    # use upload with a tiny PDF-like approach is hard. Insert through ORM via optimize path
    # by calling an internal helper: create resume via direct API if available.
    # We'll use the TestClient + override by posting to a thin test-only path is not available.
    # Instead create user resume through sqlalchemy session from client app.
    from app.core.database import get_db
    from app.models.models import Resume, User
    from datetime import datetime

    # Get user id
    me = client.get("/api/auth/me", headers=headers).json()
    # Access the overridden session
    gen = client.app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        resume = Resume(
            user_id=me["id"],
            title="Test Resume",
            original_text=text * 3,
            parsed_data={"status": "parsed"},
            is_primary=True,
            created_at=datetime.utcnow(),
        )
        db.add(resume)
        db.commit()
        db.refresh(resume)
        return resume.id
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


def test_optimize_not_found(auth_headers, client):
    r = client.post(
        "/api/optimize",
        headers=auth_headers,
        json={
            "resume_id": 99999,
            "job_description": "Looking for a Python FastAPI engineer with AWS experience please.",
        },
    )
    assert r.status_code == 404


def test_optimize_with_mocked_llm(auth_headers, client):
    resume_id = _seed_resume(client, auth_headers)

    fake = {
        "tailored_resume": "Jane Doe\nPython FastAPI AWS SQL\nExperience\n- Built APIs\nSkills\nPython",
        "key_improvements": ["Added AWS keywords"],
        "missing_keywords": ["kubernetes"],
        "cover_letter": "Dear Hiring Manager,...",
        "ats_score": 90,  # should be ignored / overwritten by hybrid scorer
        "matched_keywords": ["python"],
        "used_vector_context": False,
        "ats_breakdown": {"keyword_coverage": {"score": 20}},
        "ats_summary": ["test"],
        "ats_method": "hybrid-rules-v1",
        "score_before": 50,
        "score_delta": 10,
    }

    with patch("app.routers.optimize.optimize_resume", return_value=fake):
        r = client.post(
            "/api/optimize",
            headers=auth_headers,
            json={
                "resume_id": resume_id,
                "job_description": "We need Python FastAPI SQL AWS Docker engineers for APIs.",
                "create_application": True,
                "company": "Acme",
                "role": "Backend Engineer",
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ats_score"] == 90
    assert body["application_id"] is not None
    assert body["tailored_resume_id"] is not None
    assert "cover_letter" in body


def test_history_empty(auth_headers, client):
    r = client.get("/api/history", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []
