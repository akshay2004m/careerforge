def test_list_resumes_empty(client, auth_headers):
    response = client.get("/api/resume/list", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_upload_resume(client, auth_headers):
    # We use a dummy file since we mocked the parser
    # Need to prefix with %PDF to pass the magic bytes validation
    files = {"file": ("test_resume.pdf", b"%PDF-1.4 dummy pdf content", "application/pdf")}
    response = client.post("/api/resume/upload", headers=auth_headers, files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["resume_id"] is not None


def test_delete_resume(client, auth_headers):
    # Upload first
    files = {"file": ("test_resume.pdf", b"%PDF-1.4 dummy pdf content", "application/pdf")}
    response = client.post("/api/resume/upload", headers=auth_headers, files=files)
    resume_id = response.json()["resume_id"]

    # Delete
    del_res = client.delete(f"/api/resume/{resume_id}", headers=auth_headers)
    assert del_res.status_code == 200

    # Check it's gone
    list_res = client.get("/api/resume/list", headers=auth_headers)
    assert len(list_res.json()) == 0


def test_delete_non_existent_resume(client, auth_headers):
    response = client.delete("/api/resume/999", headers=auth_headers)
    assert response.status_code == 404
