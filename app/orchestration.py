"""Multi-agent analytical handoff (CEO, CFO, CMO, COO). No external action tools are exposed."""
from typing import Protocol
from .agents import SPECIALIST_AGENTS, normalize_workflow_agents


class Analyst(Protocol):
    def generate(self, role: str, prompt: str) -> str: ...


ROLE_GUIDANCE = {
    'ceo': (
        'Coordene a estratégia executiva, priorize iniciativas de maior retorno e delegue '
        'próximos passos sem executar ações externas.'
    ),
    'cfo': (
        'Avalie fluxo de caixa, margem de contribuição, CAC/LTV, riscos financeiros e limites '
        'orçamentários. Não invente números.'
    ),
    'cmo': (
        'Avalie marketing, tráfego pago, Google Ads Performance Max, ROAS, criativos, '
        'posicionamento e canais de venda sem ativar gastos automaticamente.'
    ),
    'coo': (
        'Avalie operações, estoque, logística, prazos de entrega, taxa de conversão e rotina '
        'de execução diária sem acionar integrações externas.'
    ),
}


def format_knowledge_context(kb) -> str:
    if kb is None:
        return ''
    is_active = kb.get('is_active', True) if isinstance(kb, dict) else getattr(kb, 'is_active', True)
    if not is_active:
        return ''

    def _val(field: str) -> str:
        raw = kb.get(field, '') if isinstance(kb, dict) else getattr(kb, field, '')
        return (raw or '').strip()

    company_name = _val('company_name')
    business_profile = _val('business_profile')
    goals_and_margins = _val('goals_and_margins')
    golden_rules = _val('golden_rules')
    agent_notes = _val('agent_notes')

    if not any([business_profile, goals_and_margins, golden_rules, agent_notes]) and (
        not company_name or company_name == 'Business AI OS'
    ):
        return ''

    parts = []
    if company_name:
        parts.append(f'Empresa: {company_name}')
    if business_profile:
        parts.append(f'Perfil e canais do negócio: {business_profile}')
    if goals_and_margins:
        parts.append(f'Metas e margens: {goals_and_margins}')
    if golden_rules:
        parts.append(f'Regras de ouro e restrições operacionais: {golden_rules}')
    if agent_notes:
        parts.append(f'Notas para agentes: {agent_notes}')
    return '\n'.join(parts)


class OfflineAnalyst:
    def __init__(self, knowledge_context: str = '', agents: list[str] | None = None):
        self.knowledge_context = (knowledge_context or '').strip()
        self.agents = normalize_workflow_agents(agents)

    def generate(self, role: str, prompt: str) -> str:
        code = role.strip().lower()
        kb_note = ''
        if self.knowledge_context or 'Base de Conhecimento da Empresa:' in prompt:
            kb_note = ' Contexto da Base de Conhecimento da empresa considerado na análise.'

        if code == 'cfo':
            return (
                'CFO (simulação offline): preservar caixa, validar CAC, margem líquida e limite '
                'orçamentário antes de aprovar qualquer investimento. Nenhum gasto foi autorizado.'
                + kb_note
            )
        if code == 'cmo':
            return (
                'CMO (simulação offline): estruturar testes de tráfego pago, Google Ads Performance Max, '
                'criativos e canais de venda com meta clara de ROAS e atribuição. Campanhas aguardam aprovação humana.'
                + kb_note
            )
        if code == 'coo':
            return (
                'COO (simulação offline): alinhar estoque, logística, SLA de expedição, conversão no '
                'checkout e checklist de execução diária antes de escalar demanda.'
                + kb_note
            )
        return (
            'CEO (simulação offline): priorizar alinhamento estratégico entre crescimento, caixa e '
            'capacidade operacional. Decisões comerciais dependem de aprovação humana.'
            + kb_note
        )


class GeminiAnalyst:
    def __init__(
        self,
        api_key: str,
        model: str,
        max_output_tokens: int = 500,
        knowledge_context: str = '',
        agents: list[str] | None = None,
    ):
        from google import genai
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.knowledge_context = (knowledge_context or '').strip()
        self.agents = normalize_workflow_agents(agents)

    def generate(self, role: str, prompt: str) -> str:
        from google.genai import types
        code = role.strip().lower()
        role_focus = ROLE_GUIDANCE.get(code, SPECIALIST_AGENTS.get(code, ''))
        kb_block = f'\n\nBase de Conhecimento da Empresa:\n{self.knowledge_context}' if self.knowledge_context else ''
        instructions = (
            f'Você é o agente {code.upper()} do Business AI OS. {role_focus} '
            'Somente análise textual. Não afirme ter realizado ações. '
            'Nunca solicite ou execute compras, publicações, contratações ou transferências. '
            'Diferencie hipóteses de fatos. Responda em português do Brasil.'
            f'{kb_block}'
        )
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=instructions,
                max_output_tokens=self.max_output_tokens,
                temperature=0.2,
            ),
        )
        txt = getattr(response, 'text', None)
        return txt.strip() if isinstance(txt, str) and txt.strip() else '[Resposta vazia]'


def run_ceo_cfo(
    goal: str,
    analyst: Analyst,
    agents: list[str] | None = None,
    knowledge_context: str = '',
) -> dict:
    if not goal.strip() or len(goal) > 2000:
        raise ValueError('Goal must have 1-2000 non-whitespace characters')

    raw_agents = agents if agents is not None else getattr(analyst, 'agents', None)
    selected_agents = normalize_workflow_agents(raw_agents)
    kb = (knowledge_context or getattr(analyst, 'knowledge_context', '') or '').strip()

    outputs: dict[str, str] = {}
    messages: list[dict[str, str]] = [{'from': 'user', 'to': selected_agents[0], 'content': goal}]

    for idx, role in enumerate(selected_agents):
        prompt_parts = [f'Objetivo do usuário: {goal}']
        if kb:
            prompt_parts.append(f'Base de Conhecimento da Empresa:\n{kb}')
        if outputs:
            prior = '\n'.join(f'- Parecer do {k.upper()}: {v}' for k, v in outputs.items())
            prompt_parts.append(f'Pareceres anteriores:\n{prior}')
        guidance = ROLE_GUIDANCE.get(role, '')
        if guidance:
            prompt_parts.append(f'Foco do {role.upper()}: {guidance}')
        prompt = '\n\n'.join(prompt_parts)

        reply = analyst.generate(role, prompt)
        outputs[role] = reply
        next_role = selected_agents[idx + 1] if idx + 1 < len(selected_agents) else ('ceo' if role != 'ceo' else 'user')
        messages.append({'from': role, 'to': next_role, 'content': reply})

    return {
        'mode': 'offline' if isinstance(analyst, OfflineAnalyst) else 'gemini',
        'agents': selected_agents,
        'outputs': outputs,
        'messages': messages,
        'knowledge_injected': bool(kb),
        'knowledge_context': kb,
        'requires_human_approval_for_actions': True,
        'actions_executed': 0,
    }


def build_adk_agents(model: str):
    """Native Google ADK agents; orchestration endpoint uses explicit auditable handoff."""
    from google.adk.agents import Agent
    return {
        code: Agent(
            name=code,
            model=model,
            description=SPECIALIST_AGENTS[code],
            instruction=f'{ROLE_GUIDANCE[code]} Não execute ações externas nem gastos.',
        )
        for code in ('ceo', 'cfo', 'cmo', 'coo')
    }


def read_only_business_snapshot(initial_capital_brl: float = 2000.0, monthly_ai_budget_brl: float = 50.0) -> dict:
    return {
        'initial_capital_brl': initial_capital_brl,
        'monthly_ai_budget_brl': monthly_ai_budget_brl,
        'read_only': True,
        'actions_executed': 0,
    }


def build_read_only_adk_runner(model: str, snapshot_fn=read_only_business_snapshot):
    from google.adk.agents import Agent
    from google.adk.runners import InMemorySessionService, Runner
    agent = Agent(
        name='ceo_cfo_read_only',
        model=model,
        description='Analise read-only de estrategia, caixa, marketing e operacoes',
        instruction='Use apenas ferramentas de leitura. Nao execute acoes externas nem gastos.',
        tools=[snapshot_fn],
    )
    return Runner(app_name='business_ai_os', agent=agent, session_service=InMemorySessionService())
