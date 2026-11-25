def test_health_returns_ok(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "SitePilot AI"
    assert body["database"] == "ok"
    assert body["environment"] == "test"


def test_health_never_leaks_groq_key(client):
    body = client.get("/api/v1/health").json()
    # Only a boolean presence flag may be exposed — never a key value.
    assert body["groq_configured"] is False
    assert "groq_api_key" not in body
