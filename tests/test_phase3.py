import os
from pathlib import Path
import subprocess
import sys
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from app.auth import hash_password
from app.config import Settings
from app.db import make_engine, make_session_factory
from app.main import create_app
from app.models import AuditEvent, User

REPO_ROOT = str(Path(__file__).resolve().parent.parent)
KEY = "test-secret-key-1234567890123456"


def _migrate(db_url: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
    )


def _seed_users(cfg: Settings) -> None:
    engine = make_engine(cfg)
    sessions = make_session_factory(engine)
    try:
        with sessions() as s:
            s.add_all([
                User(username="admin_p3", password_hash=hash_password("AdminPass123!"), role="admin", is_active=True),
                User(username="op_p3", password_hash=hash_password("OperPass123!"), role="operator", is_active=True),
                User(username="view_p3", password_hash=hash_password("ViewPass123!"), role="viewer", is_active=True),
            ])
            s.commit()
    finally:
        engine.dispose()


def test_alembic_migration_creates_company_knowledge_table(tmp_path):
    db_url = f"sqlite:///{tmp_path}/phase3_mig.db"
    _migrate(db_url)
    cfg = Settings(app_api_key=KEY, database_url=db_url, gemini_api_key="")
    engine = make_engine(cfg)
    try:
        tables = set(inspect(engine).get_table_names())
        assert "company_knowledge" in tables
        cols = {c["name"] for c in inspect(engine).get_columns("company_knowledge")}
        assert {
            "id",
            "company_name",
            "business_profile",
            "goals_and_margins",
            "golden_rules",
            "agent_notes",
            "is_active",
            "updated_by",
        }.issubset(cols)
    finally:
        engine.dispose()


def test_knowledge_rbac_and_audit_trail(tmp_path):
    db_url = f"sqlite:///{tmp_path}/phase3_kb_rbac.db"
    _migrate(db_url)
    cfg = Settings(app_api_key=KEY, database_url=db_url, gemini_api_key="")
    _seed_users(cfg)

    payload = {
        "company_name": "Loja Alpha",
        "business_profile": "E-commerce D2C e Google Ads Performance Max",
        "goals_and_margins": "Margem líquida >= 20%, ROAS mínimo 4.0x",
        "golden_rules": "Nunca aprovar aumento de orçamento sem aprovação humana",
        "agent_notes": "CMO focar em criativos PMax; COO controlar estoque mínimo",
        "is_active": True,
    }

    with TestClient(create_app(cfg)) as viewer_client:
        assert viewer_client.post("/auth/login", json={"username": "view_p3", "password": "ViewPass123!"}).status_code == 200
        r_get_empty = viewer_client.get("/knowledge")
        assert r_get_empty.status_code == 200
        assert r_get_empty.json()["id"] is None
        assert viewer_client.put("/knowledge", json=payload).status_code == 403
        assert viewer_client.post("/knowledge", json=payload).status_code == 403

    with TestClient(create_app(cfg)) as op_client:
        assert op_client.post("/auth/login", json={"username": "op_p3", "password": "OperPass123!"}).status_code == 200
        r_save = op_client.put("/knowledge", json=payload)
        assert r_save.status_code == 200
        saved = r_save.json()
        assert saved["id"] is not None
        assert saved["company_name"] == "Loja Alpha"
        assert saved["updated_by"] == "op_p3"
        assert saved["is_active"] is True

    with TestClient(create_app(cfg)) as viewer_client:
        assert viewer_client.post("/auth/login", json={"username": "view_p3", "password": "ViewPass123!"}).status_code == 200
        r_read = viewer_client.get("/knowledge")
        assert r_read.status_code == 200
        assert r_read.json()["company_name"] == "Loja Alpha"
        assert "Performance Max" in r_read.json()["business_profile"]

    with TestClient(create_app(cfg)) as admin_client:
        assert admin_client.post("/auth/login", json={"username": "admin_p3", "password": "AdminPass123!"}).status_code == 200
        r_update = admin_client.post("/knowledge", json={**payload, "company_name": "Loja Alpha v2"})
        assert r_update.status_code == 200
        assert r_update.json()["company_name"] == "Loja Alpha v2"
        assert r_update.json()["updated_by"] == "admin_p3"

        r_audit = admin_client.get("/audit")
        assert r_audit.status_code == 200
        actions = [item["action"] for item in r_audit.json()]
        assert "knowledge.updated" in actions


def test_specialists_cmo_coo_workflow_and_knowledge_injection(tmp_path):
    db_url = f"sqlite:///{tmp_path}/phase3_wf.db"
    _migrate(db_url)
    cfg = Settings(app_api_key=KEY, database_url=db_url, gemini_api_key="")
    _seed_users(cfg)

    with TestClient(create_app(cfg)) as c:
        assert c.post("/auth/login", json={"username": "op_p3", "password": "OperPass123!"}).status_code == 200

        r_agents = c.get("/agents")
        assert r_agents.status_code == 200
        specialists = r_agents.json()["specialists"]
        assert set(["ceo", "cfo", "cmo", "coo"]).issubset(specialists.keys())

        r_kb = c.put(
            "/knowledge",
            json={
                "company_name": "Marca Beta",
                "business_profile": "Loja própria + Google Ads Performance Max",
                "goals_and_margins": "ROAS alvo 5x e margem líquida 22%",
                "golden_rules": "Nenhuma compra ou gasto sem aprovação humana",
                "agent_notes": "CMO revisar segmentação PMax; COO revisar SLA de envio",
                "is_active": True,
            },
        )
        assert r_kb.status_code == 200

        # Todos os 4 especialistas (padrão) com injeção automática da Base de Conhecimento
        r_all = c.post("/workflows/ceo-cfo", json={"goal": "Plano Q1 com foco em ROAS e estoque", "use_gemini": False})
        assert r_all.status_code == 200
        body_all = r_all.json()
        assert body_all["agents"] == ["ceo", "cfo", "cmo", "coo"]
        assert set(body_all["outputs"].keys()) == {"ceo", "cfo", "cmo", "coo"}
        assert body_all["knowledge_injected"] is True
        assert "Marca Beta" in body_all["knowledge_context"]
        assert "Performance Max" in body_all["outputs"]["cmo"]
        assert "estoque" in body_all["outputs"]["coo"].lower()
        assert body_all["requires_human_approval_for_actions"] is True
        assert body_all["actions_executed"] == 0

        # Seleção específica apenas de CMO e COO via alias /workflows/specialists
        r_sub = c.post(
            "/workflows/specialists",
            json={"goal": "Escalar campanhas PMax sem ruptura de estoque", "agents": ["cmo", "coo"], "use_gemini": False},
        )
        assert r_sub.status_code == 200
        body_sub = r_sub.json()
        assert body_sub["agents"] == ["cmo", "coo"]
        assert set(body_sub["outputs"].keys()) == {"cmo", "coo"}

        # Agente inválido no workflow retorna 422
        r_bad = c.post("/workflows/ceo-cfo", json={"goal": "Teste inválido", "agents": ["inexistente"], "use_gemini": False})
        assert r_bad.status_code == 422


def test_tasks_support_cmo_and_coo_and_reject_unknown_agent(tmp_path):
    db_url = f"sqlite:///{tmp_path}/phase3_tasks.db"
    _migrate(db_url)
    cfg = Settings(app_api_key=KEY, database_url=db_url, gemini_api_key="")
    _seed_users(cfg)

    with TestClient(create_app(cfg)) as c:
        assert c.post("/auth/login", json={"username": "op_p3", "password": "OperPass123!"}).status_code == 200

        t_cmo = c.post("/tasks", json={"title": "Revisar criativos PMax e ROAS", "assigned_agent": "CMO"})
        assert t_cmo.status_code == 201
        assert t_cmo.json()["assigned_agent"] == "cmo"

        t_coo = c.post("/tasks", json={"title": "Auditar estoque crítico e logística", "assigned_agent": "coo"})
        assert t_coo.status_code == 201
        assert t_coo.json()["assigned_agent"] == "coo"

        t_bad = c.post("/tasks", json={"title": "Tarefa inválida", "assigned_agent": "agente_invalido"})
        assert t_bad.status_code == 422

        listed = c.get("/tasks")
        assert listed.status_code == 200
        agents_in_list = {item["assigned_agent"] for item in listed.json()}
        assert {"cmo", "coo"}.issubset(agents_in_list)
