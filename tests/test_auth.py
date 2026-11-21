from pathlib import Path
import os
import subprocess
import sys
from fastapi.testclient import TestClient
from app.auth import hash_password
from app.config import Settings
from app.db import make_engine, make_session_factory
from app.main import create_app
from app.models import Approval, User


def _migrate(db_url: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(Path(__file__).resolve().parent.parent),
        env=env,
        check=True,
    )


def _seed_users(cfg: Settings) -> None:
    engine = make_engine(cfg)
    sessions = make_session_factory(engine)
    try:
        with sessions() as s:
            s.add_all([
                User(username="admin_user", password_hash=hash_password("AdminPass123!"), role="admin", is_active=True),
                User(username="op_user", password_hash=hash_password("OperPass123!"), role="operator", is_active=True),
                User(username="view_user", password_hash=hash_password("ViewPass123!"), role="viewer", is_active=True),
            ])
            s.commit()
    finally:
        engine.dispose()


KEY = "test-secret-key-1234567890123456"


def test_session_login_me_and_logout_revocation(tmp_path):
    db_url = f"sqlite:///{tmp_path}/auth_session.db"
    _migrate(db_url)
    cfg = Settings(app_api_key=KEY, database_url=db_url, gemini_api_key="")
    _seed_users(cfg)

    with TestClient(create_app(cfg)) as c:
        bad = c.post("/auth/login", json={"username": "admin_user", "password": "WrongPassword"})
        assert bad.status_code == 401

        r_login = c.post("/auth/login", json={"username": "admin_user", "password": "AdminPass123!"})
        assert r_login.status_code == 200
        assert cfg.session_cookie_name in c.cookies

        r_me = c.get("/auth/me")
        assert r_me.status_code == 200
        assert r_me.json()["username"] == "admin_user"
        assert r_me.json()["role"] == "admin"
        assert r_me.json()["auth_method"] == "session"

        r_logout = c.post("/auth/logout")
        assert r_logout.status_code == 200

        r_me_after = c.get("/auth/me")
        assert r_me_after.status_code == 401


def test_role_based_guards_and_api_key_compatibility(tmp_path):
    db_url = f"sqlite:///{tmp_path}/auth_roles.db"
    _migrate(db_url)
    cfg = Settings(app_api_key=KEY, database_url=db_url, gemini_api_key="")
    _seed_users(cfg)

    engine = make_engine(cfg)
    sessions = make_session_factory(engine)
    with sessions() as s:
        ap = Approval(action_type="cash_transfer", payload_json='{"amount": 100}')
        s.add(ap)
        s.commit()
        approval_id = ap.id
    engine.dispose()

    with TestClient(create_app(cfg)) as viewer_client:
        assert viewer_client.post("/auth/login", json={"username": "view_user", "password": "ViewPass123!"}).status_code == 200
        assert viewer_client.get("/tasks").status_code == 200
        assert viewer_client.post("/tasks", json={"title": "Tarefa bloqueada", "assigned_agent": "ceo"}).status_code == 403
        assert viewer_client.post(f"/approvals/{approval_id}/decision", json={"approve": True}).status_code == 403
        assert viewer_client.get("/audit").status_code == 403

    with TestClient(create_app(cfg)) as op_client:
        assert op_client.post("/auth/login", json={"username": "op_user", "password": "OperPass123!"}).status_code == 200
        assert op_client.post("/tasks", json={"title": "Tarefa operador", "assigned_agent": "ceo"}).status_code == 201
        assert op_client.post(f"/approvals/{approval_id}/decision", json={"approve": True}).status_code == 403

    with TestClient(create_app(cfg)) as api_client:
        r_dec = api_client.post(
            f"/approvals/{approval_id}/decision",
            json={"approve": True},
            headers={"X-API-Key": KEY},
        )
        assert r_dec.status_code == 200
        assert r_dec.json()["status"] == "approved"
        assert r_dec.json()["executed"] is False
