def test_list_applications_empty(client, auth_headers):
    response = client.get("/api/applications", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_create_application(client, auth_headers):
    payload = {
        "company": "TechCorp",
        "role": "Software Engineer",
        "status": "applied",
        "job_description": "We need a great engineer.",
        "skills": ["Python", "FastAPI"],
    }
    response = client.post("/api/applications", headers=auth_headers, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] is not None
    assert data["company"] == "TechCorp"
    assert data["status"] == "applied"


def test_update_application(client, auth_headers):
    # Create first
    payload = {"company": "TechCorp", "role": "Software Engineer"}
    create_res = client.post("/api/applications", headers=auth_headers, json=payload)
    app_id = create_res.json()["id"]

    # Update
    update_payload = {"status": "interview", "notes": "Got a call!"}
    update_res = client.patch(
        f"/api/applications/{app_id}", headers=auth_headers, json=update_payload
    )
    assert update_res.status_code == 200
    assert update_res.json()["status"] == "interview"
    assert update_res.json()["notes"] == "Got a call!"


def test_delete_application(client, auth_headers):
    # Create first
    payload = {"company": "DeleteMe", "role": "Tester"}
    create_res = client.post("/api/applications", headers=auth_headers, json=payload)
    app_id = create_res.json()["id"]

    # Delete
    del_res = client.delete(f"/api/applications/{app_id}", headers=auth_headers)
    assert del_res.status_code == 200

    # Ensure it's gone
    list_res = client.get("/api/applications", headers=auth_headers)
    assert len(list_res.json()) == 0
