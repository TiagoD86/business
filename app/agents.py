SPECIALIST_AGENTS = {
    'ceo': 'Coordenação estratégica, prioridades de negócio e delegação executiva',
    'cfo': 'Controle financeiro, fluxo de caixa, margens, orçamento e análise de risco',
    'cmo': 'Marketing, tráfego pago, Google Ads Performance Max, ROAS, criativos e canais de venda',
    'coo': 'Operações, estoque, logística, conversão e execução diária',
}

WORKFLOW_AGENT_ORDER = ('ceo', 'cfo', 'cmo', 'coo')

AGENTS = {
    **SPECIALIST_AGENTS,
    'research': 'Pesquisa de mercado e produtos',
    'import': 'Fornecedores e simulações de importação',
    'compliance': 'Anatel, Inmetro e requisitos fiscais',
    'cto': 'Tecnologia, testes e automações',
}


def normalize_workflow_agents(agents: list[str] | None) -> list[str]:
    if agents is None:
        return list(WORKFLOW_AGENT_ORDER)
    normalized: list[str] = []
    for raw in agents:
        code = str(raw).strip().lower()
        if code not in SPECIALIST_AGENTS:
            allowed = ', '.join(WORKFLOW_AGENT_ORDER)
            raise ValueError(f'Unsupported specialist agent "{raw}". Allowed: {allowed}')
        if code not in normalized:
            normalized.append(code)
    if not normalized:
        raise ValueError('At least one specialist agent must be selected')
    return normalized
