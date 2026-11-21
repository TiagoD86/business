# Prompt para continuar no Google AI Studio

Você é arquiteto de software sênior. Continue o projeto Business AI OS anexado, sem reescrever funcionalidades testadas. A arquitetura é Python FastAPI, SQLAlchemy, PostgreSQL, ADK e Gemini API, com 8 agentes lógicos. O projeto está na Fase 1: autenticação por chave de API para desenvolvimento, tarefas, aprovações, orçamento registrado e auditoria. Leia README.md e execute os testes antes de editar.

Próximas entregas, nesta ordem:
1. Corrigir quaisquer testes quebrados sem remover validações.
2. Criar migrações Alembic e persistência de configuração.
3. Implementar autenticação de usuário real com sessão segura e papéis; não expor API key no frontend.
4. Implementar gateway Gemini com modelos disponíveis consultados na documentação oficial, limite de tokens, estimativa/reserva de custos antes da chamada, contabilização posterior e tratamento de erros.
5. Integrar Google ADK com CEO e CFO, inicialmente apenas ferramentas read-only.
6. Criar dashboard web com aprovações explícitas, histórico e controle de caixa.

Regras: nenhuma compra, publicação, transferência, contratação ou alteração financeira definitiva sem aprovação humana; não executar ações automaticamente após a aprovação até haver executor específico e validação adicional. Não inventar preços de API, permissões TikTok ou regras regulatórias. Não adicionar credenciais ao repositório. Gerar testes para cada recurso. Preservar limite de capital inicial R$ 2.000 e orçamento mensal de IA R$ 50 configuráveis.

## Estado após incremento da Fase 2
Foi adicionado `POST /workflows/ceo-cfo` com handoff CEO→CFO, modo offline testado, gateway opcional Gemini e definições de agentes Google ADK. O fluxo ainda NÃO roda via ADK Runner; priorize integrá-lo com testes mockados e limites de custos confiáveis. Depois crie frontend web responsivo com autenticação de sessão no servidor (nunca expor APP_API_KEY/GEMINI_API_KEY no browser). Preserve o contrato do endpoint e os testes existentes.
