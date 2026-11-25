from app.core.config import Settings


def test_settings_defaults_are_safe():
    s = Settings()
    assert s.app_name == "SitePilot AI"
    assert s.groq_configured is False  # no key set in test env


def test_groq_configured_detects_a_key():
    s = Settings(groq_api_key="test-key-not-real")
    assert s.groq_configured is True
