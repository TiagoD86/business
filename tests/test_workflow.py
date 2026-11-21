import os, subprocess, sys
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app

def _migrate(db_url: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=r"D:\Antigravity\Business-AI-OS-Fase2", env=env, check=True)

KEY = "test-secret-key-1234567890123456"

def test_ceo_cfo_offline_and_guards(tmp_path):
    db_url = f"sqlite:///{tmp_path}/flow.db"
    _migrate(db_url)
    cfg = Settings(app_api_key=KEY, database_url=db_url, gemini_api_key="")
    with TestClient(create_app(cfg)) as c:
        r_off = c.post("/workflows/ceo-cfo", json={"goal": "Resumo de caixa mensal", "use_gemini": False}, headers={"X-API-Key": KEY})
        assert r_off.status_code == 200
        r_nokey = c.post("/workflows/ceo-cfo", json={"goal": "Analise estrategica", "use_gemini": True}, headers={"X-API-Key": KEY})
        assert r_nokey.status_code == 503

def test_ceo_cfo_gemini_mock_and_budget_guards(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path}/flow.db"
    _migrate(db_url)
    monkeypatch.setattr("app.main.run_ceo_cfo", lambda goal, analyst=None: {"mode": "gemini", "goal": goal, "summary": "ok"})
    cfg = Settings(app_api_key=KEY, database_url=db_url, gemini_api_key="fake-key", monthly_ai_budget_brl=5.0, gemini_max_workflow_brl=3.0)
    with TestClient(create_app(cfg)) as c:
        r1 = c.post("/workflows/ceo-cfo", json={"goal": "Analise margem", "use_gemini": True}, headers={"X-API-Key": KEY})
        assert r1.status_code == 200
        r2 = c.post("/workflows/ceo-cfo", json={"goal": "Segunda analise", "use_gemini": True}, headers={"X-API-Key": KEY})
        assert r2.status_code == 409

def test_read_only_adk_runner_mock(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path}/flow_fail.db"
    _migrate(db_url)
    monkeypatch.setattr("app.main.run_ceo_cfo", lambda goal, analyst=None: {"mode": "offline", "goal": goal, "summary": "read-only ok"})
    cfg = Settings(app_api_key=KEY, database_url=db_url, gemini_api_key="")
    with TestClient(create_app(cfg)) as c:
        r = c.post("/workflows/ceo-cfo", json={"goal": "Leitura segura", "use_gemini": False}, headers={"X-API-Key": KEY})
        assert r.status_code == 200
