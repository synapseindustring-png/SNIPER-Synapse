# Plano de implementação

## Estratégia

Entregar fatias verticais verificáveis. Cada etapa termina com testes e uma demonstração observável, evitando construir todos os modelos antes do primeiro fluxo real.

## Fase 0 — decisões e prova de fonte

Status: concluída para início da fundação. A prova seletiva está documentada em `docs/cnpj-selective-spike.md`.

### Entregáveis

- auditoria dos repositórios externos;
- arquitetura, modelo, scoring, fontes, deploy e plano;
- prova seletiva do layout CNPJ com arquivo/amostra controlada — concluída;
- medição de memória, disco temporário e tempo de varredura — concluída;
- lista final de dependências com versões.

### Saída esperada

Um script/protótipo descartável ou teste de domínio demonstra que estabelecimentos podem ser filtrados em chunks antes de persistência. Ele não vira automaticamente código de produção.

## Fase 1 — fundação executável

Status: concluída para o escopo da fundação. Scaffold Django/Docker, autenticação,
layout-base, healthchecks, logs estruturados e fila PostgreSQL foram implementados. A
concorrência foi validada com dois workers processando o mesmo job uma única vez. O painel
operacional persistente do worker permanece como evolução da Fase 7.

### Entregáveis

- projeto Django;
- configuração por ambiente;
- Dockerfile, compose local e healthchecks;
- PostgreSQL e migrations;
- autenticação ADMIN;
- layout visual base;
- fila de jobs no PostgreSQL e worker;
- logs estruturados.

### Aceite

- stack inicia com um comando;
- admin autentica;
- web e worker reportam saúde;
- job de teste é processado uma única vez mesmo com dois workers;
- testes rodam sem rede.

## Fase 2 — consulta e empresa curada

Status: iniciada. Os modelos Company, CompanyCnae, Source, SourceRecord,
FieldObservation, DiscoveryQuery, QueryRun, QueryResult e SourceCoverage, suas restrições,
admin e migrations estão implementados. Fingerprint determinístico e ingestão idempotente
por CNPJ possuem testes. Formulário, listagem, detalhe, estimativa segura, disparo de prévia
e tela de execução estão implementados. A listagem paginada de indústrias, seus filtros e o
detalhe com CNAEs e proveniência também estão disponíveis. Edição e fluxo completo de
múltiplas partes ainda estão pendentes.

### Entregáveis

- Company, CNAE, Source, SourceRecord e FieldObservation;
- DiscoveryQuery, QueryRun, QueryResult e SourceCoverage;
- formulário de consulta;
- validação/fingerprint;
- deduplicação forte;
- telas de execução e resultados;
- cadastro/edição administrativa para correções.

### Aceite

- consultas equivalentes geram o mesmo fingerprint;
- empresa repetida por CNPJ não duplica;
- observações conflitantes preservam ambas as fontes;
- consulta pode terminar parcial.

## Fase 3 — CNPJ seletivo

Status: em andamento. O leitor de estabelecimentos em ZIP, os filtros antecipados e
fixtures pequenas estão implementados e testados. A descoberta WebDAV do manifesto oficial
e a seleção da competência mais recente estão implementadas; staging e complementação por
Empresas/Simples continuam pendentes. A integração do ZIP local ou remoto com o job
`DISCOVER_CNPJ` e a base curada já está implementada. O downloader remoto
possui allowlist HTTPS, quota, reserva de disco, lock global, validação do ZIP e limpeza.
O modo de prévia e os limites de persistência impedem consultas abertas ilimitadas.

### Entregáveis

- descoberta da competência e manifesto de arquivos;
- downloader sequencial com checksum e quota;
- parser streaming/chunked;
- filtros de situação, UF, município, CNAE e datas;
- complementação por empresas e Simples apenas para candidatos;
- limpeza/retomada segura;
- coverage cache.

### Cenário de validação

```text
UF = MG
Situação = ATIVA
CNAE/segmento = fabricação de alimentos
Entity = Industry
```

### Aceite

- nenhuma base SQLite nacional é criada;
- somente registros correspondentes chegam ao PostgreSQL;
- competência e arquivo de origem são auditáveis;
- interrupção não deixa resultado marcado como completo;
- arquivos temporários são removidos após sucesso;
- consulta repetida usa cobertura válida.

## Fase 4 — regras, sinais e scoring

Status: iniciada. Signal, RuleSet, ScoringRule, ScoreSnapshot, ScoreContribution e
ScoreOverride estão persistidos e disponíveis no admin. O motor determinístico calcula
indústrias e parceiros, aplica condições compostas, decay, caps, regra crítica, fórmula e
thresholds. O cálculo assíncrono e o Explain Score já aparecem no detalhe da empresa. O
detector determinístico analisa payloads já persistidos, conserva evidências, deduplica e
desativa sinais obsoletos. Coleta de conteúdo para alimentar o detector,
publicação/simulação avançada e fluxo completo de parceiros continuam pendentes.

### Entregáveis

- catálogo de sinais;
- Rule Set, regras, fórmula, thresholds e decay;
- seeds iniciais;
- detector determinístico;
- snapshots e contribuições;
- scores Industry e Partner;
- Explain Score;
- overrides e histórico;
- editor administrativo com validação.

### Aceite

- score é reproduzível;
- toda contribuição tem regra e evidência;
- regra crítica prevalece;
- alteração publicada não muda snapshots antigos;
- override permanece após recálculo.

## Fase 5 — descoberta aberta e enriquecimento

Status: iniciada. O WebsiteAdapter coleta a página inicial e um conjunto limitado de páginas
internas prioritárias de domínios já conhecidos, com proteção SSRF, DNS/IP fixado,
redirects revalidados, `robots.txt`, timeouts, limite de bytes e tipos de conteúdo. Links
externos e URLs parametrizadas são descartados. Texto visível é extraído sem JavaScript,
versionado por hash e conectado automaticamente à detecção de sinais e scoring. Descoberta
mais ampla/recorrente, Overture/OSM e Maps permanecem pendentes.

### Entregáveis

- Overture/OSM atrás de adapter;
- normalização brasileira de telefone/endereço;
- MapsAdapter e serviço isolado;
- WebsiteAdapter com proteção SSRF;
- seleção de páginas relevantes;
- proveniência por campo;
- atualização e deduplicação cross-source.

### Aceite

- consulta por palavras-chave/localidade produz candidatos;
- fonte Maps indisponível não derruba a consulta inteira;
- crawler não acessa IPs privados;
- conteúdo repetido por hash não gera sinais duplicados;
- canonicalização nunca apaga observações.

## Fase 6 — intenção por vagas

Status: iniciada. Páginas prioritárias já são coletadas e vagas em JSON-LD `JobPosting`
são normalizadas, deduplicadas, desativadas quando removidas/expiradas e integradas ao
detector local como evidências individuais. Decay usa a data de publicação; regras cobrem
PCM, manutenção, produção, processos, melhoria contínua e automação. Adapters externos de
vagas permanecem pendentes. O contrato substituível, fixture local, preview sem escrita,
limites, kill switch, handler `FIND_JOBS`, deduplicação cross-source e fila de revisão já
estão implementados; o worker fornece tentativas e backoff. A fila possui tela staff,
aprovação/descarte transacionais, justificativa e auditoria, e a aprovação aciona o pipeline.

### Entregáveis

- páginas de carreiras no crawler;
- JobsAdapter/JobSpy;
- normalização e deduplicação de vagas;
- regras para PCM, manutenção, produção, processos, melhoria contínua e automação;
- decay e recálculo.

### Aceite

- vaga recente gera sinal com URL/data;
- vaga antiga recebe decay correto;
- nome ambíguo de empresa vai para revisão;
- falha/bloqueio da plataforma respeita backoff e kill switch.

## Fase 7 — produto operacional

Status: iniciada. O ranking de indústrias possui prioridade efetiva, filtros de score,
classificação, produto, sinal e recência, ordenação e CSV limitado. O detalhe, dashboard e
revisões de vagas já estão operacionais; ranking de parceiros, painel completo de jobs/fontes
e gestão visual de regras permanecem pendentes.

### Entregáveis

- Dashboard;
- rankings Industry e Partner;
- filtros e ordenação;
- Company Detail completo;
- painel de sinais, regras, fontes e jobs;
- acessibilidade e responsividade;
- backup, deploy e runbook.

### Aceite de produto

O admin consegue responder, com evidências:

1. qual empresa tem prioridade agora;
2. qual produto tem melhor aderência;
3. se a prioridade veio de fit ou intent;
4. quais regras e fontes produziram o resultado;
5. quando um sinal perderá relevância;
6. quais parceiros têm canal e quais têm conflito.

## Ordem técnica imediata

1. persistir candidatos em staging e complementar Empresas/Simples;
2. registrar cobertura/cache por competência e escopo;
3. implementar processamento sequencial das dez partes no modo completo;
4. adicionar painel detalhado do manifesto e saúde da fonte;
5. adicionar heartbeat persistente e painel operacional do worker;
6. permitir correções administrativas preservando a proveniência.

## Dependências candidatas

Manter a lista curta:

- Django;
- psycopg;
- Gunicorn;
- requests ou httpx para HTTP controlado;
- BeautifulSoup/lxml para extração HTML;
- phonenumbers para normalização internacional;
- tldextract ou biblioteca equivalente com snapshot local da public suffix list;
- pytest, pytest-django e factory_boy no desenvolvimento.

Pandas/Dask não são obrigatórios no runtime. O protótipo CNPJ decidirá entre biblioteca `csv`, PyArrow e leitura chunked conforme medições.

## Riscos prioritários

| Risco | Mitigação |
|---|---|
| formato/URL da Receita muda | manifesto versionado, adapter e fixtures |
| consulta ampla exige varredura demorada | limites, estimativa, jobs e coverage cache |
| falso positivo em palavras-chave | contexto, evidência e regras revisáveis |
| score inflado por conteúdo duplicado | hashes, dedupe keys e caps |
| bloqueio de Maps/jobs | baixa taxa, fonte opcional e circuit breaker |
| merge incorreto | apenas chaves fortes automáticas; revisão no restante |
| regra administrativa inválida | draft, validação, simulação e publicação versionada |
| SSRF no crawler | validação DNS/IP/redirect e sandbox de rede |

## Definição de pronto

Uma tarefa só está pronta quando possui migration quando aplicável, testes, logs úteis, tratamento de falha, documentação operacional e interface coerente. Coleta que funciona apenas no caminho feliz não está pronta.
