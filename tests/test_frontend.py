def test_landing_page_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "SitePilot AI" in response.text
    assert "fictional" in response.text.lower()  # honest demo-data notice


def test_static_css_is_served(client):
    response = client.get("/static/css/app.css")
    assert response.status_code == 200
