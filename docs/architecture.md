# Arquitetura do Synapse Sniper

## Objetivo

O Synapse Sniper será um monólito modular server-rendered, acompanhado por um worker assíncrono. A arquitetura prioriza auditabilidade, poucas dependências operacionais e substituição simples das fontes externas.

## Stack escolhida

- Python 3.12;
- Django 5.2 LTS;
- PostgreSQL 16 ou superior;
- templates Django, HTML semântico, CSS próprio e JavaScript vanilla;
- Gunicorn para servir a aplicação;
- worker próprio baseado em jobs persistidos no PostgreSQL;
- Docker e Coolify;
- pytest e pytest-django para testes.

Django concentra autenticação, autorização, migrations, ORM, formulários, proteção CSRF e painel administrativo. Não haverá SPA nem API pública no MVP.

## Contexto de execução

```text
Navegador
   │ HTTPS
   ▼
Django Web ─────────────── PostgreSQL
   │                           ▲
   │ cria jobs                 │ claim/resultado
   ▼                           │
Worker ────────────────────────┘
   │
   ├── CNPJAdapter ─── Receita Federal / arquivos temporários
   ├── MapsAdapter ─── google-maps-scraper isolado
   ├── PlacesAdapter ─ Overture / OpenStreetMap
   ├── WebsiteAdapter ─ sites das empresas
   └── JobsAdapter ─── JobSpy / páginas de carreira
```

Serviços mínimos no Coolify:

1. `web`: Django + Gunicorn;
2. `worker`: mesmo artefato da aplicação, executando o consumidor de jobs;
3. `postgres`: banco persistente;
4. `maps`: opcional no primeiro deploy, container isolado do scraper.

Não usar Redis inicialmente. O worker fará claim transacional com `SELECT ... FOR UPDATE SKIP LOCKED`. Redis poderá ser introduzido somente após medição de gargalo.

## Módulos da aplicação

| Módulo | Responsabilidade |
|---|---|
| `accounts` | usuários, papéis e auditoria de sessão |
| `companies` | empresa canônica, CNAEs, contatos, status e notas |
| `discovery` | consultas, filtros, execuções e candidatos |
| `sources` | adapters, registros de fonte e proveniência |
| `crawler` | páginas de websites e políticas de coleta |
| `signals` | catálogo, detecção, evidências, ativação e expiração |
| `scoring` | regras, versões, cálculo, decay e explicações |
| `jobs` | fila, tentativas, locks, métricas e erros |
| `dashboard` | rankings, filtros, indicadores e telas analíticas |

Dependências entre módulos seguem a direção:

```text
sources → companies → signals → scoring → dashboard
             ▲
discovery ───┘
jobs orquestra casos de uso, mas não contém regras de domínio
```

Adapters nunca chamam o motor de score diretamente. Eles devolvem DTOs normalizados; serviços da aplicação persistem observações, geram sinais e enfileiram o próximo passo.

## Pipeline de descoberta

```text
1. Normalizar consulta e gerar fingerprint
2. Verificar cobertura/cache válido
3. Criar QueryRun e jobs por fonte
4. Coletar candidatos em cada adapter
5. Persistir SourceRecord imutável
6. Normalizar campos
7. Resolver identidade/deduplicar
8. Criar ou atualizar Company e observações
9. Enfileirar enriquecimento permitido
10. Detectar sinais
11. Calcular scores
12. Publicar resultados da consulta
```

Uma falha em uma fonte não invalida resultados das outras. O `QueryRun` termina como `PARTIAL` quando ao menos uma fonte falhar e outra produzir resultado.

## Processamento seletivo do CNPJ

Os projetos rictom constroem primeiro uma base SQLite nacional completa. O Sniper não seguirá esse modelo.

### Algoritmo proposto

1. consultar o índice WebDAV da Receita e fixar uma competência;
2. baixar arquivos de referência pequenos necessários;
3. baixar uma parte de estabelecimentos por vez;
4. ler o CSV dentro do ZIP em streaming/chunks;
5. filtrar cedo por situação, UF, município, CNAE e data;
6. gravar somente candidatos em uma staging table do PostgreSQL;
7. reunir os `cnpj_basico` encontrados;
8. processar as partes de empresas e Simples, conservando apenas esses radicais;
9. materializar as empresas normalizadas;
10. apagar cada artefato temporário depois de checksum, processamento e commit;
11. registrar competência, arquivos, checksums e contagens.

Sócios não entram no primeiro corte. CNAE secundário será dividido apenas para candidatos, evitando criar uma tabela nacional derivada.

Consultas posteriores usam primeiro a base curada. Se os filtros excederem a cobertura registrada, uma nova varredura seletiva será executada.

## Contrato conceitual dos adapters

```python
class SourceAdapter(Protocol):
    key: str

    def validate_query(self, query: SourceQuery) -> None: ...
    def collect(self, query: SourceQuery, context: RunContext) -> Iterator[SourceItem]: ...
    def healthcheck(self) -> HealthResult: ...
```

`SourceItem` contém identidade externa, payload normalizado, payload bruto sanitizado, URL, data observada e metadados de proveniência.

Cada adapter define capacidades declarativas, por exemplo: filtros suportados, volume máximo, necessidade de browser, custo estimado e janela mínima entre chamadas. A interface desabilita combinações que a fonte não suporta.

## Jobs

Estados:

```text
PENDING → RUNNING → SUCCEEDED
                  ↘ RETRY_SCHEDULED → RUNNING
                  ↘ FAILED
PENDING/RUNNING → CANCELLED
```

Cada job possui tipo, payload versionado, prioridade, tentativas, `run_after`, lock com expiração, heartbeat e idempotency key.

Regras operacionais:

- claim atômico;
- idempotência por consulta, fonte, competência e alvo;
- timeout por tipo;
- retry somente para falhas transitórias;
- exponential backoff com jitter;
- dead-letter lógico após o limite;
- mensagem de erro sanitizada para UI e detalhe técnico protegido para admin;
- heartbeat para recuperar jobs abandonados.

## Deduplicação

Correspondências fortes são automáticas:

1. CNPJ exato;
2. domínio registrável exato;
3. telefone normalizado exato, quando não compartilhado;
4. identificador estável da mesma fonte.

Razão social/nome + endereço e proximidade geográfica geram candidatos de mesclagem. Não haverá fuzzy merge destrutivo automático no MVP.

Toda mesclagem conserva os `SourceRecord` originais e registra empresa origem, empresa destino, usuário/regra e data.

## Segurança da coleta

O crawler de websites é uma superfície de SSRF e deverá:

- aceitar apenas `http` e `https`;
- resolver DNS e bloquear loopback, link-local, redes privadas e metadados de nuvem;
- revalidar cada redirect;
- limitar redirects, bytes, duração e content types;
- não executar JavaScript no primeiro corte;
- usar user-agent identificável;
- respeitar rate limit por domínio e política configurada;
- não enviar cookies nem credenciais;
- sanitizar texto e URLs antes de exibir.

Dados sensíveis e secrets nunca entram em logs. Conteúdo coletado é tratado como entrada não confiável.

O mesmo parser extrai, com limite próprio, objetos JSON-LD `JobPosting` das respostas já
baixadas. Eles são normalizados em `JobPosting`, ligados ao `SourceRecord` da página e
oferecidos ao detector pelos campos `job_title` e `job_description`; nenhum link de vaga é
visitado automaticamente. O detector gera uma evidência por vaga e regra, usando a data de
publicação para decay e a validade/idade máxima para expiração.

## Observabilidade

- logs JSON com `request_id`, `query_run_id`, `job_id`, `source` e `company_id`;
- métricas de duração, volume, retries, taxa de erro e novos/atualizados;
- healthcheck separado para web, banco, worker e adapters;
- painel de jobs e saúde das fontes no admin;
- timestamps armazenados em UTC e apresentados em `America/Sao_Paulo`.

## Decisões adiadas

- Redis/Celery;
- API pública;
- multi-tenancy;
- Elasticsearch;
- browser genérico para todos os websites;
- changedetection.io;
- réplica nacional completa de CNPJ;
- LLM ou classificação sem regras explícitas.
