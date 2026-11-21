from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
import hmac
import json
from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .auth import create_server_session, get_user_by_session_token, revoke_session_token, verify_password
from .config import Settings
from .db import make_engine, make_session_factory
from .models import AIUsage, Approval, AuditEvent, Task, User
from .orchestration import GeminiAnalyst, OfflineAnalyst, run_ceo_cfo


class LoginIn(BaseModel):
    username: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=4, max_length=128)


class WorkflowIn(BaseModel):
    goal: str = Field(min_length=3, max_length=500)
    use_gemini: bool = False


class TaskIn(BaseModel):
    title: str = Field(min_length=3, max_length=250)
    assigned_agent: str


class ApprovalIn(BaseModel):
    action_type: str = Field(min_length=3, max_length=50)
    payload: dict


class DecisionIn(BaseModel):
    approve: bool


class Principal(BaseModel):
    username: str
    role: str
    auth_method: str


DASHBOARD_HTML = '<!doctype html>\n<html lang="pt">\n<head>\n  <meta charset="utf-8" />\n  <meta name="viewport" content="width=device-width, initial-scale=1" />\n  <title>Business AI OS ? Dashboard</title>\n  <style>\n    body { font-family: system-ui, sans-serif; margin: 0; background: #0f172a; color: #e2e8f0; }\n    header { display: flex; justify-content: space-between; align-items: center; padding: 16px 24px; background: #1e293b; border-bottom: 1px solid #334155; }\n    main { max-width: 1180px; margin: 24px auto; padding: 0 16px; display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 16px; }\n    section { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 16px; }\n    h2 { margin: 0 0 12px; font-size: 1.05rem; color: #f8fafc; }\n    label { display: block; font-size: 0.85rem; margin-top: 8px; color: #cbd5e1; }\n    input, textarea, select, button { width: 100%; box-sizing: border-box; margin-top: 4px; padding: 8px 10px; border-radius: 6px; border: 1px solid #475569; background: #0f172a; color: #f8fafc; }\n    button { cursor: pointer; background: #2563eb; border-color: #3b82f6; font-weight: 600; margin-top: 10px; }\n    button.secondary { background: #334155; border-color: #475569; }\n    button.approve { background: #15803d; border-color: #22c55e; width: auto; padding: 6px 10px; margin: 0 4px 0 0; }\n    button.reject { background: #b91c1c; border-color: #ef4444; width: auto; padding: 6px 10px; margin: 0; }\n    pre { background: #090d16; padding: 10px; border-radius: 6px; overflow: auto; max-height: 220px; font-size: 0.8rem; }\n    .kpi { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-bottom: 10px; }\n    .kpi div { background: #0f172a; padding: 10px; border-radius: 6px; border: 1px solid #334155; }\n    .kpi span { display: block; font-size: 0.75rem; color: #94a3b8; }\n    .kpi strong { font-size: 1rem; color: #f8fafc; }\n    .row { border-bottom: 1px solid #334155; padding: 8px 0; font-size: 0.88rem; }\n    .inline-check { display: flex; align-items: center; gap: 8px; margin-top: 10px; }\n    .inline-check input { width: auto; margin: 0; }\n    .badge { font-size: 0.8rem; padding: 4px 8px; border-radius: 999px; background: #0f172a; border: 1px solid #475569; }\n  </style>\n</head>\n<body>\n  <header>\n    <div><strong>Business AI OS</strong> ? Painel CEO / CFO, Caixa e Aprova??es</div>\n    <div style="display:flex; gap:8px; align-items:center;">\n      <span id="session-badge" class="badge">Sess?o: n?o autenticado</span>\n      <button id="btn-logout" class="secondary" style="width:auto; margin:0; padding:6px 12px;" onclick="logout()">Sair</button>\n    </div>\n  </header>\n\n  <main>\n    <section>\n      <h2>1. Sess?o e Chave Opcional</h2>\n      <label>Utilizador</label>\n      <input id="login-user" placeholder="ex: admin" />\n      <label>Palavra-passe</label>\n      <input id="login-pass" type="password" placeholder="????????" />\n      <button onclick="login()">Entrar com Sess?o</button>\n      <label>X-API-Key opcional (fallback de servi?o)</label>\n      <input id="api-key" placeholder="Opcional se j? estiver autenticado por sess?o" />\n      <button class="secondary" onclick="refreshAll()">Atualizar Dados</button>\n    </section>\n\n    <section>\n      <h2>2. Conversa e Workflow CEO / CFO</h2>\n      <label>Objetivo estrat?gico ou financeiro</label>\n      <textarea id="wf-goal" rows="3" placeholder="Ex: Avaliar margem l?quida e caixa para o pr?ximo trimestre"></textarea>\n      <label class="inline-check">\n        <input id="wf-gemini" type="checkbox" />\n        <span>Usar Gemini (sujeito a chave e reserva de or?amento)</span>\n      </label>\n      <button onclick="runWorkflow()">Executar Workflow CEO / CFO</button>\n      <pre id="wf-output">Aguardando execu??o...</pre>\n    </section>\n\n    <section>\n      <h2>3. Controle de Caixa e Or?amento IA</h2>\n      <div class="kpi">\n        <div><span>Capital Inicial (BRL)</span><strong id="kpi-capital">__CAPITAL__</strong></div>\n        <div><span>Teto Mensal IA (BRL)</span><strong id="kpi-budget">__BUDGET__</strong></div>\n      </div>\n      <div class="row">Regra de aprova??o: decis?es registam estado sem execu??o autom?tica (<code>executed: false</code>).</div>\n      <pre id="audit-output">Auditoria dispon?vel para perfil admin ou X-API-Key.</pre>\n    </section>\n\n    <section>\n      <h2>4. Tarefas</h2>\n      <label>T?tulo da tarefa</label>\n      <input id="task-title" placeholder="Ex: Rever fluxo de caixa semanal" />\n      <label>Agente respons?vel</label>\n      <input id="task-agent" value="cfo" />\n      <button onclick="createTask()">Criar Tarefa</button>\n      <div id="tasks-list"></div>\n    </section>\n\n    <section style="grid-column: 1 / -1;">\n      <h2>5. Aprova??es Humanas (Sem Execu??o Autom?tica)</h2>\n      <div style="display:grid; grid-template-columns: 1fr 1fr auto; gap:8px; align-items:end;">\n        <div>\n          <label>Tipo de a??o</label>\n          <input id="app-action" placeholder="Ex: budget_reallocation" />\n        </div>\n        <div>\n          <label>Payload JSON</label>\n          <input id="app-payload" value=\'{"amount_brl": 250}\' />\n        </div>\n        <button onclick="requestApproval()">Solicitar Aprova??o</button>\n      </div>\n      <div id="approvals-list" style="margin-top:12px;"></div>\n    </section>\n  </main>\n\n  <script>\n    function authHeaders(extra = {}) {\n      const key = document.getElementById(\'api-key\').value.trim();\n      const headers = { \'Content-Type\': \'application/json\', ...extra };\n      if (key) headers[\'X-API-Key\'] = key;\n      return headers;\n    }\n\n    async function login() {\n      const username = document.getElementById(\'login-user\').value.trim();\n      const password = document.getElementById(\'login-pass\').value;\n      const res = await fetch(\'/auth/login\', {\n        method: \'POST\',\n        headers: { \'Content-Type\': \'application/json\' },\n        body: JSON.stringify({ username, password }),\n      });\n      if (!res.ok) {\n        alert(\'Falha no login (\' + res.status + \')\');\n        return;\n      }\n      await refreshAll();\n    }\n\n    async function logout() {\n      await fetch(\'/auth/logout\', { method: \'POST\', headers: authHeaders() });\n      document.getElementById(\'session-badge\').textContent = \'Sess?o: n?o autenticado\';\n      document.getElementById(\'tasks-list\').innerHTML = \'\';\n      document.getElementById(\'approvals-list\').innerHTML = \'\';\n    }\n\n    async function loadMe() {\n      const res = await fetch(\'/auth/me\', { headers: authHeaders() });\n      const badge = document.getElementById(\'session-badge\');\n      if (!res.ok) {\n        badge.textContent = \'Sess?o: n?o autenticado\';\n        return null;\n      }\n      const me = await res.json();\n      badge.textContent = `Sess?o: ${me.username} (${me.role})`;\n      return me;\n    }\n\n    async function runWorkflow() {\n      const goal = document.getElementById(\'wf-goal\').value;\n      const use_gemini = document.getElementById(\'wf-gemini\').checked;\n      const res = await fetch(\'/workflows/ceo-cfo\', {\n        method: \'POST\',\n        headers: authHeaders(),\n        body: JSON.stringify({ goal, use_gemini }),\n      });\n      const data = await res.json();\n      document.getElementById(\'wf-output\').textContent = JSON.stringify({ status: res.status, data }, null, 2);\n      await loadAudit();\n    }\n\n    async function createTask() {\n      const title = document.getElementById(\'task-title\').value;\n      const assigned_agent = document.getElementById(\'task-agent\').value;\n      const res = await fetch(\'/tasks\', {\n        method: \'POST\',\n        headers: authHeaders(),\n        body: JSON.stringify({ title, assigned_agent }),\n      });\n      if (!res.ok) {\n        alert(\'Erro ao criar tarefa (\' + res.status + \')\');\n        return;\n      }\n      document.getElementById(\'task-title\').value = \'\';\n      await loadTasks();\n    }\n\n    async function loadTasks() {\n      const res = await fetch(\'/tasks\', { headers: authHeaders() });\n      if (!res.ok) return;\n      const tasks = await res.json();\n      document.getElementById(\'tasks-list\').innerHTML = tasks.map(t =>\n        `<div class="row"><strong>#${t.id}</strong> ${t.title} ? <em>${t.assigned_agent}</em> [${t.status}]</div>`\n      ).join(\'\') || \'<div class="row">Sem tarefas.</div>\';\n    }\n\n    async function requestApproval() {\n      const action_type = document.getElementById(\'app-action\').value;\n      let payload = {};\n      try { payload = JSON.parse(document.getElementById(\'app-payload\').value || \'{}\'); }\n      catch { alert(\'Payload JSON inv?lido\'); return; }\n      const res = await fetch(\'/approvals\', {\n        method: \'POST\',\n        headers: authHeaders(),\n        body: JSON.stringify({ action_type, payload }),\n      });\n      if (!res.ok) {\n        alert(\'Erro ao solicitar aprova??o (\' + res.status + \')\');\n        return;\n      }\n      const created = await res.json();\n      renderApprovalItem(created);\n    }\n\n    function renderApprovalItem(item) {\n      const container = document.getElementById(\'approvals-list\');\n      const div = document.createElement(\'div\');\n      div.className = \'row\';\n      div.id = \'approval-\' + item.id;\n      div.innerHTML = `\n        <strong>Aprova??o #${item.id}</strong> ? ${item.action_type || \'a??o\'} ? estado: <span id="app-status-${item.id}">${item.status}</span>\n        <span id="app-exec-${item.id}"></span>\n        <div style="margin-top:6px;">\n          <button class="approve" onclick="decideApproval(${item.id}, true)">Aprovar</button>\n          <button class="reject" onclick="decideApproval(${item.id}, false)">Rejeitar</button>\n        </div>`;\n      container.prepend(div);\n    }\n\n    async function decideApproval(id, approve) {\n      const res = await fetch(`/approvals/${id}/decision`, {\n        method: \'POST\',\n        headers: authHeaders(),\n        body: JSON.stringify({ approve }),\n      });\n      const data = await res.json();\n      if (!res.ok) {\n        alert(\'Decis?o bloqueada (\' + res.status + \'): \' + (data.detail || \'\'));\n        return;\n      }\n      document.getElementById(\'app-status-\' + id).textContent = data.status;\n      document.getElementById(\'app-exec-\' + id).textContent = ` (executed: ${data.executed})`;\n      await loadAudit();\n    }\n\n    async function loadAudit() {\n      const res = await fetch(\'/audit\', { headers: authHeaders() });\n      const out = document.getElementById(\'audit-output\');\n      if (!res.ok) {\n        out.textContent = `Auditoria indispon?vel (${res.status})`;\n        return;\n      }\n      const rows = await res.json();\n      out.textContent = JSON.stringify(rows.slice(0, 15), null, 2);\n    }\n\n    async function refreshAll() {\n      await loadMe();\n      await loadTasks();\n      await loadAudit();\n    }\n\n    refreshAll();\n  </script>\n</body>\n</html>'

def create_app(settings: Settings | None = None):
    cfg = settings or Settings()
    engine = make_engine(cfg)
    sessions = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        engine.dispose()

    app = FastAPI(title='Business AI OS', version='0.1.0', lifespan=lifespan)

    def db():
        with sessions() as session:
            yield session

    def audit(session: Session, action: str, detail: str):
        session.add(AuditEvent(action=action, detail=detail))

    def usage_total(session: Session) -> Decimal:
        period = datetime.now(timezone.utc).strftime('%Y-%m')
        value = session.scalar(select(func.sum(AIUsage.amount_brl)).where(AIUsage.period == period))
        return Decimal(str(value or 0))

    def current_principal(
        x_api_key: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=cfg.session_cookie_name),
        session: Session = Depends(db),
    ) -> Principal:
        if x_api_key and hmac.compare_digest(x_api_key, cfg.app_api_key):
            return Principal(username='api_service', role='admin', auth_method='api_key')
        user = get_user_by_session_token(session, session_cookie)
        if user is not None:
            return Principal(username=user.username, role=user.role, auth_method='session')
        raise HTTPException(status_code=401, detail='Unauthorized')

    def require_roles(*allowed_roles: str):
        def _guard(principal: Principal = Depends(current_principal)) -> Principal:
            if principal.role not in allowed_roles:
                raise HTTPException(status_code=403, detail='Forbidden')
            return principal
        return _guard

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.post('/auth/login')
    def login(data: LoginIn, response: Response, session: Session = Depends(db)):
        user = session.scalar(select(User).where(User.username == data.username, User.is_active.is_(True)))
        if not user or not verify_password(data.password, user.password_hash):
            raise HTTPException(status_code=401, detail='Invalid credentials')
        raw_token, _ = create_server_session(session, user, cfg.session_ttl_hours)
        audit(session, 'auth.login', f'{user.username}:{user.role}')
        session.commit()
        response.set_cookie(
            key=cfg.session_cookie_name,
            value=raw_token,
            max_age=cfg.session_ttl_hours * 3600,
            httponly=True,
            samesite='lax',
            secure=cfg.session_cookie_secure,
            path='/',
        )
        return {'username': user.username, 'role': user.role}

    @app.post('/auth/logout')
    def logout(
        response: Response,
        session_cookie: str | None = Cookie(default=None, alias=cfg.session_cookie_name),
        session: Session = Depends(db),
    ):
        revoked = revoke_session_token(session, session_cookie)
        if revoked:
            audit(session, 'auth.logout', 'session_revoked')
            session.commit()
        response.delete_cookie(key=cfg.session_cookie_name, path='/')
        return {'logged_out': True}

    @app.get('/auth/me')
    def me(principal: Principal = Depends(current_principal)):
        return principal

    @app.post('/workflows/ceo-cfo')
    def ceo_cfo(
        data: WorkflowIn,
        principal: Principal = Depends(require_roles('admin', 'operator')),
        session: Session = Depends(db),
    ):
        if data.use_gemini:
            if not cfg.gemini_api_key:
                raise HTTPException(status_code=503, detail='Gemini API key not configured')
            ceiling = cfg.gemini_max_workflow_brl
            if ceiling <= 0 or usage_total(session) + ceiling > cfg.monthly_ai_budget_brl:
                raise HTTPException(status_code=409, detail='Insufficient internal AI budget for conservative reservation')
            period = datetime.now(timezone.utc).strftime('%Y-%m')
            reservation = AIUsage(period=period, amount_brl=ceiling)
            session.add(reservation)
            audit(session, 'ai.budget_reserved', f'{principal.username}:{ceiling}')
            session.commit()
            try:
                result = run_ceo_cfo(data.goal, GeminiAnalyst(cfg.gemini_api_key, cfg.gemini_model))
            except Exception as exc:
                audit(session, 'ai.workflow_failed', f'{principal.username}:{exc}')
                session.commit()
                raise HTTPException(status_code=502, detail='Gemini workflow failed') from exc
            audit(session, 'workflow.ceo_cfo', f'{principal.username}:gemini')
            session.commit()
            return result

        result = run_ceo_cfo(data.goal, OfflineAnalyst())
        audit(session, 'workflow.ceo_cfo', f'{principal.username}:offline')
        session.commit()
        return result

    @app.post('/tasks', status_code=201)
    def create_task(
        data: TaskIn,
        principal: Principal = Depends(require_roles('admin', 'operator')),
        session: Session = Depends(db),
    ):
        t = Task(title=data.title, assigned_agent=data.assigned_agent)
        session.add(t)
        session.flush()
        audit(session, 'task.created', f'{principal.username}:{t.id}')
        session.commit()
        return {'id': t.id, 'title': t.title, 'assigned_agent': t.assigned_agent, 'status': t.status}

    @app.get('/tasks')
    def list_tasks(
        principal: Principal = Depends(require_roles('admin', 'operator', 'viewer')),
        session: Session = Depends(db),
    ):
        return [
            {'id': t.id, 'title': t.title, 'assigned_agent': t.assigned_agent, 'status': t.status}
            for t in session.scalars(select(Task).order_by(Task.id.desc())).all()
        ]

    @app.post('/approvals', status_code=201)
    def request_approval(
        data: ApprovalIn,
        principal: Principal = Depends(require_roles('admin', 'operator')),
        session: Session = Depends(db),
    ):
        a = Approval(action_type=data.action_type, payload_json=json.dumps(data.payload, sort_keys=True))
        session.add(a)
        session.flush()
        audit(session, 'approval.requested', f'{principal.username}:{a.id}')
        session.commit()
        return {'id': a.id, 'status': a.status}

    @app.post('/approvals/{approval_id}/decision')
    def decide(
        approval_id: int,
        data: DecisionIn,
        principal: Principal = Depends(require_roles('admin')),
        session: Session = Depends(db),
    ):
        a = session.get(Approval, approval_id)
        if not a:
            raise HTTPException(status_code=404, detail='Not found')
        if a.status != 'pending':
            raise HTTPException(status_code=409, detail='Already decided')
        a.status = 'approved' if data.approve else 'rejected'
        audit(session, 'approval.decided', f'{principal.username}:{approval_id}:{a.status}')
        session.commit()
        return {'id': a.id, 'status': a.status, 'executed': False}

    @app.get('/audit')
    def audit_events(
        principal: Principal = Depends(require_roles('admin')),
        session: Session = Depends(db),
    ):
        return [
            {'id': e.id, 'action': e.action, 'detail': e.detail}
            for e in session.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(100)).all()
        ]


    @app.get('/', response_class=HTMLResponse)
    @app.get('/dashboard', response_class=HTMLResponse)
    def dashboard():
        html = DASHBOARD_HTML.replace('__CAPITAL__', str(cfg.initial_capital_brl)).replace('__BUDGET__', str(cfg.monthly_ai_budget_brl))
        return HTMLResponse(content=html, media_type='text/html; charset=utf-8')

    return app


app = create_app()
