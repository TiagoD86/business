from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
import hmac
import json
from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .agents import AGENTS, SPECIALIST_AGENTS, normalize_workflow_agents
from .auth import create_server_session, get_user_by_session_token, revoke_session_token, verify_password
from .config import Settings
from .db import make_engine, make_session_factory
from .models import AIUsage, Approval, AuditEvent, CompanyKnowledge, Task, User
from .orchestration import GeminiAnalyst, OfflineAnalyst, format_knowledge_context, run_ceo_cfo


class LoginIn(BaseModel):
    username: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=4, max_length=128)


class WorkflowIn(BaseModel):
    goal: str = Field(min_length=3, max_length=500)
    use_gemini: bool = False
    agents: list[str] | None = None

    @field_validator('agents')
    @classmethod
    def validate_agents(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return normalize_workflow_agents(value)


class TaskIn(BaseModel):
    title: str = Field(min_length=3, max_length=250)
    assigned_agent: str

    @field_validator('assigned_agent')
    @classmethod
    def validate_agent(cls, value: str) -> str:
        code = value.strip().lower()
        if code not in AGENTS:
            allowed = ', '.join(AGENTS.keys())
            raise ValueError(f'Unsupported agent "{value}". Allowed: {allowed}')
        return code


class KnowledgeIn(BaseModel):
    company_name: str = Field(default='Business AI OS', min_length=1, max_length=160)
    business_profile: str = Field(default='', max_length=4000)
    goals_and_margins: str = Field(default='', max_length=4000)
    golden_rules: str = Field(default='', max_length=4000)
    agent_notes: str = Field(default='', max_length=4000)
    is_active: bool = True


class ApprovalIn(BaseModel):
    action_type: str = Field(min_length=3, max_length=50)
    payload: dict


class DecisionIn(BaseModel):
    approve: bool


class Principal(BaseModel):
    username: str
    role: str
    auth_method: str


DASHBOARD_HTML = """<!doctype html>
<html lang="pt">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Business AI OS — Dashboard</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body { font-family: system-ui, -apple-system, sans-serif; margin: 0; background: #0f172a; color: #e2e8f0; }
    header { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; padding: 16px 24px; background: #1e293b; border-bottom: 1px solid #334155; }
    .header-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    main.dashboard-grid { max-width: 1200px; margin: 24px auto; padding: 0 16px 32px; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; align-items: stretch; }
    section.card { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 18px; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
    section.card-full { grid-column: 1 / -1; }
    h2 { margin: 0 0 6px; font-size: 1.05rem; color: #f8fafc; padding-bottom: 8px; border-bottom: 1px solid #334155; }
    label { display: block; font-size: 0.85rem; margin-top: 4px; color: #cbd5e1; }
    input, textarea, select, button { width: 100%; font: inherit; font-size: 0.9rem; line-height: 1.4; margin-top: 4px; padding: 8px 10px; border-radius: 6px; border: 1px solid #475569; background: #0f172a; color: #f8fafc; }
    button { cursor: pointer; background: #2563eb; border-color: #3b82f6; font-weight: 600; margin-top: 8px; }
    button.secondary { background: #334155; border-color: #475569; }
    button.approve { background: #15803d; border-color: #22c55e; width: auto; padding: 6px 10px; margin: 0 4px 0 0; }
    button.reject { background: #b91c1c; border-color: #ef4444; width: auto; padding: 6px 10px; margin: 0; }
    pre { background: #090d16; padding: 10px 12px; border-radius: 6px; border: 1px solid #1e293b; overflow: auto; max-width: 100%; max-height: 220px; margin: 6px 0 0; font-size: 0.8rem; white-space: pre-wrap; word-break: break-word; }
    .kpi { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-bottom: 4px; }
    .kpi div { background: #0f172a; padding: 10px; border-radius: 6px; border: 1px solid #334155; min-width: 0; }
    .kpi span { display: block; font-size: 0.75rem; color: #94a3b8; }
    .kpi strong { font-size: 1rem; color: #f8fafc; word-break: break-word; }
    .row { border-bottom: 1px solid #334155; padding: 8px 0; font-size: 0.88rem; word-break: break-word; }
    .list-box { max-height: 220px; overflow-y: auto; margin-top: 6px; }
    .inline-check { display: flex; align-items: center; gap: 8px; margin-top: 6px; }
    .inline-check input { width: auto; margin: 0; }
    .badge { font-size: 0.8rem; padding: 4px 10px; border-radius: 999px; background: #0f172a; border: 1px solid #475569; }
    .approval-form { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto; gap: 12px; align-items: end; }
    .approval-form > div { min-width: 0; }
    .approval-form button { margin-top: 0; white-space: nowrap; padding: 8px 16px; }
    .agent-checks { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px 12px; margin-top: 2px; }
    .kb-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
    .kb-grid > div { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
    .kb-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; margin-top: 6px; }
    .kb-actions button { width: auto; margin-top: 0; padding: 8px 18px; }
    @media (max-width: 860px) {
      main.dashboard-grid { grid-template-columns: 1fr; }
      .approval-form { grid-template-columns: 1fr; }
      .approval-form button { width: 100%; }
      .kb-grid { grid-template-columns: 1fr; }
      .kb-actions button { width: 100%; }
    }
    @media (max-width: 480px) {
      .kpi { grid-template-columns: 1fr; }
      .agent-checks { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <div><strong>Business AI OS</strong> — Painel CEO / CFO, Caixa e Aprovações</div>
    <div class="header-actions">
      <span id="session-badge" class="badge">Sessão: não autenticado</span>
      <button id="btn-logout" class="secondary" style="width:auto; margin:0; padding:6px 12px;" onclick="logout()">Sair</button>
    </div>
  </header>

  <main class="dashboard-grid">
    <section id="sec-session" class="card">
      <h2>1. Sessão e Chave Opcional</h2>
      <label>Utilizador</label>
      <input id="login-user" placeholder="ex: admin" />
      <label>Palavra-passe</label>
      <input id="login-pass" type="password" placeholder="••••••••" />
      <button onclick="login()">Entrar com Sessão</button>
      <label>X-API-Key opcional (fallback de serviço)</label>
      <input id="api-key" placeholder="Opcional se já estiver autenticado por sessão" />
      <button class="secondary" onclick="refreshAll()">Atualizar Dados</button>
    </section>

    <section id="sec-workflow" class="card">
      <h2>2. Conversa e Workflow CEO / CFO</h2>
      <label>Objetivo estratégico ou financeiro</label>
      <textarea id="wf-goal" rows="3" placeholder="Ex: Avaliar margem líquida e caixa para o próximo trimestre"></textarea>
      <label>Agentes especialistas no workflow</label>
      <div class="agent-checks">
        <label class="inline-check"><input type="checkbox" class="wf-agent" value="ceo" checked /><span>CEO (Estratégia)</span></label>
        <label class="inline-check"><input type="checkbox" class="wf-agent" value="cfo" checked /><span>CFO (Finanças)</span></label>
        <label class="inline-check"><input type="checkbox" class="wf-agent" value="cmo" checked /><span>CMO (Marketing / Ads)</span></label>
        <label class="inline-check"><input type="checkbox" class="wf-agent" value="coo" checked /><span>COO (Operações)</span></label>
      </div>
      <label class="inline-check">
        <input id="wf-gemini" type="checkbox" />
        <span>Usar Gemini (sujeito a chave e reserva de orçamento)</span>
      </label>
      <button onclick="runWorkflow()">Executar Workflow Especialistas</button>
      <pre id="wf-output">Aguardando execução...</pre>
    </section>

    <section id="sec-budget" class="card">
      <h2>3. Controle de Caixa e Orçamento IA</h2>
      <div class="kpi">
        <div><span>Capital Inicial (BRL)</span><strong id="kpi-capital">__CAPITAL__</strong></div>
        <div><span>Teto Mensal IA (BRL)</span><strong id="kpi-budget">__BUDGET__</strong></div>
      </div>
      <div class="row">Regra de aprovação: decisões registam estado sem execução automática (<code>executed: false</code>).</div>
      <pre id="audit-output">Auditoria disponível para perfil admin ou X-API-Key.</pre>
    </section>

    <section id="sec-tasks" class="card">
      <h2>4. Tarefas</h2>
      <label>Título da tarefa</label>
      <input id="task-title" placeholder="Ex: Rever fluxo de caixa semanal" />
      <label>Agente responsável</label>
      <select id="task-agent">
        <option value="cfo" selected>CFO — Finanças e Caixa</option>
        <option value="ceo">CEO — Estratégia e Delegação</option>
        <option value="cmo">CMO — Marketing, PMax e ROAS</option>
        <option value="coo">COO — Operações, Estoque e Logística</option>
      </select>
      <button onclick="createTask()">Criar Tarefa</button>
      <div id="tasks-list" class="list-box"></div>
    </section>

    <section id="sec-approvals" class="card card-full">
      <h2>5. Aprovações Humanas (Sem Execução Automática)</h2>
      <div class="approval-form">
        <div>
          <label>Tipo de ação</label>
          <input id="app-action" placeholder="Ex: budget_reallocation" />
        </div>
        <div>
          <label>Payload JSON</label>
          <input id="app-payload" value='{"amount_brl": 250}' />
        </div>
        <button onclick="requestApproval()">Solicitar Aprovação</button>
      </div>
      <div id="approvals-list" class="list-box"></div>
    </section>

    <section id="sec-knowledge" class="card card-full">
      <h2>6. Base de Conhecimento da Empresa</h2>
      <div class="kb-grid">
        <div>
          <label>Nome da empresa / marca</label>
          <input id="kb-company" placeholder="Ex: Minha Loja Digital" />
          <label>Perfil e canais do negócio</label>
          <textarea id="kb-profile" rows="3" placeholder="Ex: E-commerce próprio + Google Ads Performance Max + marketplaces"></textarea>
          <label>Metas e margens</label>
          <textarea id="kb-goals" rows="3" placeholder="Ex: Margem líquida mínima 18%, ROAS alvo 4.5x"></textarea>
        </div>
        <div>
          <label>Regras de ouro e restrições operacionais</label>
          <textarea id="kb-rules" rows="3" placeholder="Ex: Nunca aprovar compra ou aumento de verba sem revisão humana"></textarea>
          <label>Notas gerais ou por agente (CEO, CFO, CMO, COO)</label>
          <textarea id="kb-notes" rows="4" placeholder="Ex: CMO focar em criativos UGC e PMax; COO monitorar estoque crítico"></textarea>
          <label class="inline-check">
            <input id="kb-active" type="checkbox" checked />
            <span>Injetar automaticamente no contexto dos agentes</span>
          </label>
        </div>
      </div>
      <div class="kb-actions">
        <button onclick="saveKnowledge()">Salvar Base de Conhecimento</button>
        <span id="kb-status" class="badge">Aguardando autenticação</span>
      </div>
    </section>
  </main>

  <script>
    function authHeaders(extra = {}) {
      const key = document.getElementById('api-key').value.trim();
      const headers = { 'Content-Type': 'application/json', ...extra };
      if (key) headers['X-API-Key'] = key;
      return headers;
    }

    async function login() {
      const username = document.getElementById('login-user').value.trim();
      const password = document.getElementById('login-pass').value;
      const res = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        alert('Falha no login (' + res.status + ')');
        return;
      }
      await refreshAll();
    }

    async function logout() {
      await fetch('/auth/logout', { method: 'POST', headers: authHeaders() });
      document.getElementById('session-badge').textContent = 'Sessão: não autenticado';
      document.getElementById('tasks-list').innerHTML = '';
      document.getElementById('approvals-list').innerHTML = '';
      document.getElementById('kb-status').textContent = 'Aguardando autenticação';
    }

    async function loadMe() {
      const res = await fetch('/auth/me', { headers: authHeaders() });
      const badge = document.getElementById('session-badge');
      if (!res.ok) {
        badge.textContent = 'Sessão: não autenticado';
        return null;
      }
      const me = await res.json();
      badge.textContent = `Sessão: ${me.username} (${me.role})`;
      return me;
    }

    async function runWorkflow() {
      const goal = document.getElementById('wf-goal').value;
      const use_gemini = document.getElementById('wf-gemini').checked;
      const agents = Array.from(document.querySelectorAll('.wf-agent:checked')).map(el => el.value);
      if (agents.length === 0) {
        alert('Selecione pelo menos um agente especialista.');
        return;
      }
      const res = await fetch('/workflows/ceo-cfo', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ goal, use_gemini, agents }),
      });
      const data = await res.json();
      document.getElementById('wf-output').textContent = JSON.stringify({ status: res.status, data }, null, 2);
      await loadAudit();
    }

    async function createTask() {
      const title = document.getElementById('task-title').value;
      const assigned_agent = document.getElementById('task-agent').value;
      const res = await fetch('/tasks', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ title, assigned_agent }),
      });
      if (!res.ok) {
        alert('Erro ao criar tarefa (' + res.status + ')');
        return;
      }
      document.getElementById('task-title').value = '';
      await loadTasks();
    }

    async function loadTasks() {
      const res = await fetch('/tasks', { headers: authHeaders() });
      if (!res.ok) return;
      const tasks = await res.json();
      document.getElementById('tasks-list').innerHTML = tasks.map(t =>
        `<div class="row"><strong>#${t.id}</strong> ${t.title} — <em>${t.assigned_agent}</em> [${t.status}]</div>`
      ).join('') || '<div class="row">Sem tarefas.</div>';
    }

    async function requestApproval() {
      const action_type = document.getElementById('app-action').value;
      let payload = {};
      try { payload = JSON.parse(document.getElementById('app-payload').value || '{}'); }
      catch { alert('Payload JSON inválido'); return; }
      const res = await fetch('/approvals', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ action_type, payload }),
      });
      if (!res.ok) {
        alert('Erro ao solicitar aprovação (' + res.status + ')');
        return;
      }
      const created = await res.json();
      renderApprovalItem(created);
    }

    function renderApprovalItem(item) {
      const container = document.getElementById('approvals-list');
      const div = document.createElement('div');
      div.className = 'row';
      div.id = 'approval-' + item.id;
      div.innerHTML = `
        <strong>Aprovação #${item.id}</strong> — ${item.action_type || 'ação'} · estado: <span id="app-status-${item.id}">${item.status}</span>
        <span id="app-exec-${item.id}"></span>
        <div style="margin-top:6px;">
          <button class="approve" onclick="decideApproval(${item.id}, true)">Aprovar</button>
          <button class="reject" onclick="decideApproval(${item.id}, false)">Rejeitar</button>
        </div>`;
      container.prepend(div);
    }

    async function decideApproval(id, approve) {
      const res = await fetch(`/approvals/${id}/decision`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ approve }),
      });
      const data = await res.json();
      if (!res.ok) {
        alert('Decisão bloqueada (' + res.status + '): ' + (data.detail || ''));
        return;
      }
      document.getElementById('app-status-' + id).textContent = data.status;
      document.getElementById('app-exec-' + id).textContent = ` (executed: ${data.executed})`;
      await loadAudit();
    }

    async function loadAudit() {
      const res = await fetch('/audit', { headers: authHeaders() });
      const out = document.getElementById('audit-output');
      if (!res.ok) {
        out.textContent = `Auditoria indisponível (${res.status})`;
        return;
      }
      const rows = await res.json();
      out.textContent = JSON.stringify(rows.slice(0, 15), null, 2);
    }

    async function loadKnowledge() {
      const res = await fetch('/knowledge', { headers: authHeaders() });
      const statusEl = document.getElementById('kb-status');
      if (!res.ok) {
        statusEl.textContent = `Base indisponível (${res.status})`;
        return;
      }
      const kb = await res.json();
      document.getElementById('kb-company').value = kb.company_name || '';
      document.getElementById('kb-profile').value = kb.business_profile || '';
      document.getElementById('kb-goals').value = kb.goals_and_margins || '';
      document.getElementById('kb-rules').value = kb.golden_rules || '';
      document.getElementById('kb-notes').value = kb.agent_notes || '';
      document.getElementById('kb-active').checked = Boolean(kb.is_active);
      if (kb.id) {
        statusEl.textContent = `Base carregada (por ${kb.updated_by || 'sistema'})`;
      } else {
        statusEl.textContent = 'Base inicial (ainda não salva)';
      }
    }

    async function saveKnowledge() {
      const payload = {
        company_name: document.getElementById('kb-company').value.trim() || 'Business AI OS',
        business_profile: document.getElementById('kb-profile').value,
        goals_and_margins: document.getElementById('kb-goals').value,
        golden_rules: document.getElementById('kb-rules').value,
        agent_notes: document.getElementById('kb-notes').value,
        is_active: document.getElementById('kb-active').checked,
      };
      const res = await fetch('/knowledge', {
        method: 'PUT',
        headers: authHeaders(),
        body: JSON.stringify(payload),
      });
      const statusEl = document.getElementById('kb-status');
      if (!res.ok) {
        alert('Erro ao salvar base de conhecimento (' + res.status + ')');
        return;
      }
      const saved = await res.json();
      statusEl.textContent = `Base salva (por ${saved.updated_by || 'sistema'})`;
      await loadAudit();
    }

    async function refreshAll() {
      await loadMe();
      await loadTasks();
      await loadKnowledge();
      await loadAudit();
    }

    refreshAll();
  </script>
</body>
</html>"""

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

    def serialize_knowledge(kb: CompanyKnowledge | None) -> dict:
        if kb is None:
            return {
                'id': None,
                'company_name': 'Business AI OS',
                'business_profile': '',
                'goals_and_margins': '',
                'golden_rules': '',
                'agent_notes': '',
                'is_active': True,
                'updated_by': None,
                'updated_at': None,
            }
        return {
            'id': kb.id,
            'company_name': kb.company_name,
            'business_profile': kb.business_profile,
            'goals_and_margins': kb.goals_and_margins,
            'golden_rules': kb.golden_rules,
            'agent_notes': kb.agent_notes,
            'is_active': kb.is_active,
            'updated_by': kb.updated_by,
            'updated_at': kb.updated_at.isoformat() if kb.updated_at else None,
        }

    @app.get('/agents')
    def list_agents(principal: Principal = Depends(require_roles('admin', 'operator', 'viewer'))):
        return {'specialists': SPECIALIST_AGENTS, 'all': AGENTS}

    @app.get('/knowledge')
    def get_knowledge(
        principal: Principal = Depends(require_roles('admin', 'operator', 'viewer')),
        session: Session = Depends(db),
    ):
        kb = session.scalar(select(CompanyKnowledge).order_by(CompanyKnowledge.id.desc()))
        return serialize_knowledge(kb)

    @app.put('/knowledge')
    @app.post('/knowledge')
    def upsert_knowledge(
        data: KnowledgeIn,
        principal: Principal = Depends(require_roles('admin', 'operator')),
        session: Session = Depends(db),
    ):
        kb = session.scalar(select(CompanyKnowledge).order_by(CompanyKnowledge.id.desc()))
        if kb is None:
            kb = CompanyKnowledge()
            session.add(kb)
        kb.company_name = data.company_name.strip()
        kb.business_profile = data.business_profile.strip()
        kb.goals_and_margins = data.goals_and_margins.strip()
        kb.golden_rules = data.golden_rules.strip()
        kb.agent_notes = data.agent_notes.strip()
        kb.is_active = data.is_active
        kb.updated_by = principal.username
        kb.updated_at = datetime.now(timezone.utc)
        session.flush()
        audit(session, 'knowledge.updated', f'{principal.username}:{kb.id}:active={kb.is_active}')
        session.commit()
        session.refresh(kb)
        return serialize_knowledge(kb)

    @app.post('/workflows/ceo-cfo')
    @app.post('/workflows/specialists')
    def ceo_cfo(
        data: WorkflowIn,
        principal: Principal = Depends(require_roles('admin', 'operator')),
        session: Session = Depends(db),
    ):
        selected_agents = normalize_workflow_agents(data.agents)
        active_kb = session.scalar(
            select(CompanyKnowledge).where(CompanyKnowledge.is_active.is_(True)).order_by(CompanyKnowledge.id.desc())
        )
        kb_context = format_knowledge_context(active_kb)

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
                analyst = GeminiAnalyst(
                    cfg.gemini_api_key,
                    cfg.gemini_model,
                    knowledge_context=kb_context,
                    agents=selected_agents,
                )
                result = run_ceo_cfo(data.goal, analyst)
            except Exception as exc:
                audit(session, 'ai.workflow_failed', f'{principal.username}:{exc}')
                session.commit()
                raise HTTPException(status_code=502, detail='Gemini workflow failed') from exc
            audit(session, 'workflow.ceo_cfo', f'{principal.username}:gemini:{",".join(selected_agents)}')
            session.commit()
            return result

        analyst = OfflineAnalyst(knowledge_context=kb_context, agents=selected_agents)
        result = run_ceo_cfo(data.goal, analyst)
        audit(session, 'workflow.ceo_cfo', f'{principal.username}:offline:{",".join(selected_agents)}')
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
