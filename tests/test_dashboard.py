from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app


def test_dashboard_renders_and_shows_financial_limits():
    cfg = Settings(
        app_api_key="test-secret-key-1234567890123456",
        database_url="sqlite:///:memory:",
        initial_capital_brl="3500",
        monthly_ai_budget_brl="75",
    )
    with TestClient(create_app(cfg)) as c:
        r = c.get("/dashboard")
        assert r.status_code == 200
        assert "charset=utf-8" in r.headers.get("content-type", "").lower()
        assert "Business AI OS" in r.text
        assert "Aprova??es" in r.text
        assert "3500" in r.text
        assert "75" in r.text
        assert "executed: false" in r.text
