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

Uma cobertura só é registrada por uma execução `SUCCEEDED` que o orquestrador declara ter
percorrido todo o escopo. A chave combina fonte, competência, tipo de entidade, versão e
filtros normalizados. Em um cache hit válido, os `QueryResult` são copiados de forma limitada
para uma nova execução; `SourceRecord`, observações e empresas não são duplicados, e nenhum
job de coleta é criado. Cobertura expirada, parcial ou de outra competência é ignorada.

O staging é delimitado pelo teto do job e pertence ao `QueryRun`. A complementação aceita
no máximo dez partes de Empresas e uma de Simples, processadas sequencialmente; cada leitor
mantém em memória apenas o conjunto de CNPJs básicos candidatos e encerra cedo quando todos
forem encontrados. Para URLs remotas, o context manager apaga cada ZIP antes de abrir o
seguinte. Complementos solicitados e não encontrados deixam a execução como parcial.
O modo `PREVIEW` nunca aceita complementos; URLs remotas precisam constar no manifesto
`READY` da mesma competência informada pelo job.

O modo `FULL` remoto aceita somente o conjunto exato das dez partes de Estabelecimentos,
dez de Empresas e uma de Simples do manifesto. A UI é restrita a staff, exige confirmação
e permanece bloqueada por `CNPJ_FULL_ENABLED=false`. A estimativa mostra o tráfego total,
mas a autorização de disco considera o maior arquivo individual, pois os contextos de
download não se sobrepõem. Se o teto de candidatos for atingido, não há cobertura completa.

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

Durante a execução, cada worker renova o heartbeat e a expiração do lock em uma conexão
separada. A conclusão ou falha só pode ser gravada pelo worker que ainda possui o lock;
resultados de processos atrasados são descartados se outro worker já tiver recuperado o job.

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

O primeiro JobsAdapter executável usa somente fixtures JSON locais e implementa o mesmo
contrato previsto para fontes futuras. Limites configurados são tetos: um job pode reduzi-los,
mas não ampliá-los. `PREVIEW` não cria `SourceRecord`, vaga ou revisão. `FULL` persiste apenas
correspondências fortes; coleta truncada nunca desativa vagas ausentes, pois a ausência não é
conclusiva. O registro da fonte e um kill switch global começam desabilitados.

A resolução de candidatos é restrita a usuários staff e ocorre apenas por POST com CSRF.
Aprovação e descarte exigem justificativa e são transacionais. A aprovação aceita UUID,
CNPJ ou nome exato único, persiste a vaga e enfileira a detecção; decisões resolvidas são
imutáveis para o fluxo de coleta e somente leitura no admin.

## Painel operacional

O painel de jobs/fontes é restrito a staff e somente leitura. Lista jobs paginados e
filtráveis, tentativas, contadores, métricas e erros; fontes mostram configuração, estado e
última atividade local. Chaves sensíveis, parâmetros de URLs e padrões de credenciais são
ocultados antes da renderização. Capacidade de disco é consultada no ancestral existente de
`TEMP_DATA_DIR`, sem criar diretórios ou percorrer arquivos.

O ranking de indústrias é calculado por subqueries sobre o snapshot mais recente e o override
ativo, sem materializar cópias. Sinais expirados não atendem ao filtro. A exportação reutiliza
os mesmos filtros/ordenação, limita a consulta a 500 linhas, transmite CSV diretamente e
escapa prefixos interpretáveis como fórmulas por planilhas.

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
