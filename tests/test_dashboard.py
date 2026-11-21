from fastapi.testclient import TestClient
from sqlalchemy import select
from app.auth import hash_password
from app.config import Settings
from app.db import make_engine, make_session_factory
from app.main import create_app
from app.models import Base, User


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


def test_dashboard_session_approval_flow_and_rbac(tmp_path):
    db_file = tmp_path / "dash_rbac.db"
    cfg = Settings(
        app_api_key="test-secret-key-1234567890123456",
        database_url=f"sqlite:///{db_file.as_posix()}",
        initial_capital_brl="3500",
        monthly_ai_budget_brl="75",
    )
    engine = make_engine(cfg)
    Base.metadata.create_all(engine)
    sessions = make_session_factory(engine)
    app = create_app(cfg)

    with TestClient(app) as c:
        with sessions() as s:
            if not s.scalar(select(User).where(User.username == "admin")):
                s.add(User(username="admin", password_hash=hash_password("Admin1234!"), role="admin", is_active=True))
            if not s.scalar(select(User).where(User.username == "viewer")):
                s.add(User(username="viewer", password_hash=hash_password("Viewer1234!"), role="viewer", is_active=True))
            s.commit()

        # Login viewer: n?o cria aprova??o nem acede ? auditoria
        r_v = c.post("/auth/login", json={"username": "viewer", "password": "Viewer1234!"})
        assert r_v.status_code == 200
        assert c.post("/approvals", json={"action_type": "budget_shift", "payload": {"amount_brl": 100}}).status_code == 403
        assert c.get("/audit").status_code == 403
        c.post("/auth/logout")

        # Login admin: cria aprova??o e aprova sem execu??o autom?tica
        r_a = c.post("/auth/login", json={"username": "admin", "password": "Admin1234!"})
        assert r_a.status_code == 200
        created = c.post("/approvals", json={"action_type": "budget_shift", "payload": {"amount_brl": 100}})
        assert created.status_code == 201
        app_id = created.json()["id"]

        decided = c.post(f"/approvals/{app_id}/decision", json={"approve": True})
        assert decided.status_code == 200
        body = decided.json()
        assert body["status"] == "approved"
        assert body["executed"] is False

    engine.dispose()
