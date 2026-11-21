# Business AI OS — Fase 1 (starter)

Protótipo funcional da fundação: API REST, SQLite para desenvolvimento ou PostgreSQL via Docker, catálogo dos oito agentes, tarefas, aprovação humana, auditoria e registro interno de uso de IA. **Não executa chamadas Gemini nem agentes autônomos nesta fase.**

## Requisitos
Python 3.12+, pip. Para PostgreSQL: Docker Compose.

## Iniciar localmente
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # Windows: copy .env.example .env
# Edite .env: gere APP_API_KEY aleatória com 32+ caracteres
uvicorn app.main:app --reload --host 127.0.0.1
```
Abra http://127.0.0.1:8000/docs e use o cabeçalho `X-API-Key` nos endpoints protegidos. O `/health` é público.

## Testes
```bash
pytest -q
```

## PostgreSQL opcional
Defina `POSTGRES_PASSWORD` e `APP_API_KEY` no arquivo `.env` (não comite). Depois `docker compose up --build`. O banco SQLite é padrão apenas para desenvolvimento. `create_all` é bootstrap, não migração de produção.

## Google AI Studio
Abra `PROMPT_AI_STUDIO.md`, cole o prompt no AI Studio e forneça o ZIP do projeto ou seus arquivos em um ambiente que aceite projeto Python. AI Studio pode ajudar a gerar e revisar código, mas não é garantido que hospede o backend Python/PostgreSQL; execute localmente ou em hospedagem compatível.

## Endpoints
- GET /health — estado
- GET /agents — catálogo
- GET /budget — orçamento interno
- POST /usage — registro de gasto estimado/confirmado
- GET/POST /tasks — tarefas
- POST /approvals — solicitação
- POST /approvals/{id}/decision — aprovação/rejeição **sem execução**
- GET /audit — últimos 100 eventos

## Segurança e limitações
- Chave única `X-API-Key` serve **somente ao protótipo local**, não a múltiplos usuários nem frontend público. Não publicar porta/API na internet sem autenticação real, HTTPS, RBAC, rate limiting e revisão.
- O orçamento limita **registros internos** e não impede cobranças da API Gemini. A futura integração deve reservar o custo estimado antes da chamada, reconciliar custo real e definir limites também no provedor.
- Nenhuma integração externa ou compra está implementada.
- A API não recebe dados bancários, documentos pessoais ou credenciais de marketplace.
- O código contém trilha de auditoria básica; imutabilidade criptográfica, migrações, concorrência de orçamento e backups ainda são tarefas de produção.
- Nunca cole sua chave Gemini em prompts ou no repositório.

## Fase 2 incremental — CEO → CFO (protótipo)

Endpoint `POST /workflows/ceo-cfo` (protegido por `X-API-Key`):

```json
{"goal":"Planejar estratégia de afiliados sem gastar capital", "use_gemini":false}
```

O modo padrão **offline** é determinístico, permite validar a passagem CEO→CFO e não consome API. `use_gemini:true` ativa duas chamadas Gemini sequenciais **somente** com `GEMINI_API_KEY` configurada. A chave nunca deve ser colocada no frontend. O teto `GEMINI_MAX_WORKFLOW_BRL` (padrão R$ 1,00) é uma **reserva contábil conservadora por fluxo**, não um preço calculado nem um limite garantido de cobrança. Reservas não são reconciliadas automaticamente; falhas mantêm a reserva. NÃO ativar o modo pago em produção até adicionar precificação verificada, contagem de tokens, bloqueio concorrente e limites de faturamento externos.

`app/orchestration.py` contém `build_adk_agents()` com a definição nativa dos dois agentes Google ADK; **o endpoint ainda usa um orquestrador sequencial próprio**, não um `Runner` ADK. Instale dependências com `pip install -r requirements.txt`; as bibliotecas Google não estavam instaladas no ambiente de validação, portanto o modo Gemini/ADK não foi testado ao vivo. O modo offline e a API foram testados.

**Pendências prioritárias:** autenticação web real com cookies seguros e RBAC; UI responsiva; Runner ADK e sessões persistentes; migrações Alembic; reserva transacional e conciliação de custos; testes com mocks Gemini; testes PostgreSQL e implantação segura. Não exponha a API diretamente na internet.
