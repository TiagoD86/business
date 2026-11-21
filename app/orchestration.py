"""CEO -> CFO analytical handoff. No external action tools are exposed."""
from decimal import Decimal
from typing import Protocol

class Analyst(Protocol):
    def generate(self, role: str, prompt: str) -> str: ...

class OfflineAnalyst:
    def generate(self, role: str, prompt: str) -> str:
        if role == 'cfo':
            return ('CFO (simulação offline): capital inicial R$ 2.000; teto mensal de API R$ 50. '
                    'Não há receitas/despesas verificadas. Recomendo preservar caixa, medir CAC e margem '
                    'antes de qualquer investimento. Nenhum gasto foi autorizado.')
        return ('CEO (simulação offline): priorizar testes de afiliados e UGC sem gastos automáticos. '
                'Encaminhar ao CFO análise de caixa e riscos. Decisões comerciais dependem de aprovação humana.')

class GeminiAnalyst:
    def __init__(self, api_key: str, model: str, max_output_tokens: int = 500):
        from google import genai
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.max_output_tokens = max_output_tokens

    def generate(self, role: str, prompt: str) -> str:
        from google.genai import types
        instructions = ('Você é o agente ' + role.upper() + ' do Business AI OS. '
                        'Somente análise textual. Não afirme ter realizado ações. '
                        'Nunca solicite ou execute compras, publicações, contratações ou transferências. '
                        'Diferencie hipóteses de fatos. Responda em português do Brasil.')
        response = self.client.models.generate_content(
            model=self.model, contents=prompt,
            config=types.GenerateContentConfig(system_instruction=instructions, max_output_tokens=self.max_output_tokens, temperature=0.2))
        txt = getattr(response, 'text', None)
        return txt.strip() if isinstance(txt, str) and txt.strip() else '[Resposta vazia]'

def run_ceo_cfo(goal: str, analyst: Analyst) -> dict:
    if not goal.strip() or len(goal) > 2000:
        raise ValueError('Goal must have 1-2000 non-whitespace characters')
    ceo = analyst.generate('ceo', f'Objetivo do usuário: {goal}\nProponha uma estratégia sem executar ações.')
    cfo = analyst.generate('cfo', f'Objetivo: {goal}\nParecer do CEO: {ceo}\nAvalie caixa, riscos e limites. Não invente números.')
    return {'mode': 'offline' if isinstance(analyst, OfflineAnalyst) else 'gemini',
            'messages': [{'from': 'user', 'to': 'ceo', 'content': goal},
                         {'from': 'ceo', 'to': 'cfo', 'content': ceo},
                         {'from': 'cfo', 'to': 'ceo', 'content': cfo}],
            'requires_human_approval_for_actions': True, 'actions_executed': 0}

def build_adk_agents(model: str):
    """Native Google ADK agents; orchestration endpoint uses explicit auditable handoff."""
    from google.adk.agents import Agent
    ceo = Agent(name='ceo', model=model, description='Estratégia e delegação',
                instruction='Analise estratégia. Não execute ações externas nem gastos.')
    cfo = Agent(name='cfo', model=model, description='Controle de caixa e riscos',
                instruction='Analise caixa, riscos e orçamento. Não execute ações externas nem gastos.')
    return {'ceo': ceo, 'cfo': cfo}

def read_only_business_snapshot(initial_capital_brl: float = 2000.0, monthly_ai_budget_brl: float = 50.0) -> dict:
    return {'initial_capital_brl': initial_capital_brl, 'monthly_ai_budget_brl': monthly_ai_budget_brl, 'read_only': True, 'actions_executed': 0}

def build_read_only_adk_runner(model: str, snapshot_fn=read_only_business_snapshot):
    from google.adk.agents import Agent
    from google.adk.runners import InMemorySessionService, Runner
    agent = Agent(name='ceo_cfo_read_only', model=model, description='Analise read-only de estrategia e caixa', instruction='Use apenas ferramentas de leitura. Nao execute acoes externas nem gastos.', tools=[snapshot_fn])
    return Runner(app_name='business_ai_os', agent=agent, session_service=InMemorySessionService())

