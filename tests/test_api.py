import os, subprocess, sys
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app

def _migrate(db_url: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=r"D:\Antigravity\Business-AI-OS-Fase2", env=env, check=True)

KEY = "test-secret-key-1234567890123456"

def test_core(tmp_path):
    db_url = f"sqlite:///{tmp_path}/test.db"
    _migrate(db_url)
    cfg = Settings(app_api_key=KEY, database_url=db_url)
    with TestClient(create_app(cfg)) as c:
        assert c.get("/health").status_code == 200
