# Synapse Sniper — Especificação consolidada do MVP

> Documento-base anterior à implementação  
> Atualizado em: 05/09/2026  
> Status: requisitos de produto e arquitetura inicial aprovados para planejamento

## 1. Visão do produto

O **Synapse Sniper** é uma plataforma interna de inteligência comercial B2B para o mercado industrial brasileiro.

Sua finalidade não é ser um CRM genérico nem apenas exibir listas de empresas. O sistema deve localizar, enriquecer, classificar, pontuar e acompanhar:

1. indústrias de pequeno e médio porte com potencial para os produtos Synapse;
2. consultorias, engenharias, integradores e prestadores de serviços industriais com potencial para atuar como parceiros e canais.

A pergunta central do produto é:

> **Quem deve ser abordado comercialmente agora e por quê?**

Para indústrias, o sistema deve identificar **fit estrutural + dor aderente a um produto + momento comercial**.

Para parceiros, deve identificar **aderência estratégica + capacidade de canal + atividade atual - conflitos comerciais**.

## 2. Decisões confirmadas para a primeira entrega

- A aplicação será utilizada por uma única organização.
- Apenas o papel `ADMIN` precisa estar completamente funcional no MVP.
- Não haverá upload ou importação manual de CSV na primeira entrega.
- Não será necessário cadastrar manualmente todas as empresas.
- O sistema deverá descobrir e enriquecer empresas automaticamente a partir de consultas iniciadas pela interface.
- A manutenção automática de uma base pública de CNPJ é uma operação interna da fonte, e não uma importação feita pelo usuário.
- Segmentos não serão limitados a uma lista fechada inicialmente.
- A descoberta deverá aceitar filtros estruturados, CNAEs e palavras-chave configuráveis.
- Ainda não existem regras comerciais reais validadas; os pesos iniciais serão seeds configuráveis e explicitamente tratados como hipóteses.
- Não existe identidade visual obrigatória. O Sniper terá uma interface própria, profissional e orientada à análise.
- A infraestrutura será Coolify, Docker e PostgreSQL.
- A interface será construída com HTML e CSS, com JavaScript apenas onde necessário.
- Não usar LLM, machine learning ou decisões probabilísticas opacas para classificar, pontuar ou priorizar.

## 3. Primeiro fluxo vertical funcional

```text
Usuário cria uma consulta
        ↓
Define tipo, região, CNAE, segmento e palavras-chave
        ↓
Sniper executa fontes e coletores autorizados
        ↓
Descobre empresas candidatas
        ↓
Normaliza e deduplica os resultados
        ↓
Enriquece cadastro, localização e website
        ↓
Extrai sinais públicos pertinentes
        ↓
Classifica como Industry ou Partner
        ↓
Calcula scores determinísticos
        ↓
Exibe ranking, evidências e Explain Score
```

O usuário não deverá preparar arquivos. Ele iniciará a pesquisa pela aplicação e acompanhará a execução como um job.

## 4. Escopo funcional do MVP

### 4.1 Consultas e descoberta

O formulário de consulta deverá permitir, quando aplicável:

- entidade: indústria ou parceiro;
- UF e município;
- CNAE principal e secundário;
- segmento e especialidade;
- porte;
- situação cadastral;
- capital social;
- palavras-chave livres;
- limite de resultados;
- fontes a consultar.

Consultas deverão ser persistidas, repetíveis e auditáveis. Cada execução deverá registrar parâmetros, fonte, horários, volume processado, sucessos e erros.

### 4.2 Empresas

A entidade central `Company` deverá suportar, no mínimo:

- CNPJ, razão social e nome fantasia;
- tipo da empresa;
- situação cadastral;
- CNAEs principal e secundários;
- porte, capital social e data de abertura;
- endereço, município, UF e CEP;
- latitude e longitude;
- telefone, e-mail, website, domínio, LinkedIn e Google Maps;
- número estimado de funcionários, quando houver fonte;
- segmento e especialidades;
- origem, criação e última atualização.

Tipos iniciais:

```text
INDUSTRY
CONSULTANCY
INTEGRATOR
ENGINEERING
SERVICE_PROVIDER
OTHER
```

### 4.3 Proveniência

Nenhum dado enriquecido deve perder sua origem. Para cada valor relevante, registrar:

- valor normalizado;
- fonte;
- URL ou identificador externo;
- data da coleta;
- confiança, quando aplicável;
- status atual ou substituído.

O dado consolidado da empresa deve apontar para a evidência que o originou.

### 4.4 Deduplicação

Prioridade de correspondência:

1. CNPJ normalizado;
2. domínio do website;
3. telefone normalizado;
4. razão social ou nome fantasia + endereço.

Correspondências não determinísticas deverão ser enviadas para revisão, sem mesclagem destrutiva automática.

## 5. Fontes e adapters

Toda fonte externa ficará atrás de um adapter. Nenhum coletor poderá escrever diretamente nas regras de negócio.

```text
Fonte externa
    ↓
SourceAdapter
    ↓
Normalização
    ↓
Registro bruto + proveniência
    ↓
Signal Engine
    ↓
Scoring Engine
    ↓
Industry / Partner
```

Interfaces previstas:

- `CNPJAdapter`
- `MapsAdapter`
- `WebsiteAdapter`
- `JobsAdapter`
- `MonitoringAdapter`

Todos os adapters deverão suportar timeout, rate limit, retry com exponential backoff, logs estruturados e execução assíncrona.

### 5.1 CNPJ

Estratégia preferencial:

```text
Consulta criada no Sniper
        ↓
Dados abertos da Receita Federal
        ↓ download/processamento temporário das partes necessárias
CNPJAdapter aplica filtros da consulta durante o processamento
        ↓
Base curada no PostgreSQL
        ↓
Arquivos brutos temporários são descartados
```

O Sniper **não deverá manter uma réplica integral da base brasileira de CNPJ**. A base persistente será construída progressivamente a partir do que a organização efetivamente pesquisar.

O PostgreSQL deverá guardar:

- os parâmetros e o fingerprint de cada consulta;
- empresas que correspondam aos filtros executados;
- o conjunto mínimo de campos cadastrais necessário para classificação, deduplicação e scoring;
- dados normalizados, proveniência e data de referência da Receita;
- resultados já avaliados para reaproveitamento em pesquisas futuras.

Quando uma consulta não puder ser atendida pelo cache local, o adapter deverá buscar ou processar a fonte novamente. Arquivos nacionais poderão ser baixados e lidos em partes, mas serão tratados como artefatos temporários. O processamento deverá filtrar cedo por situação, UF, município, CNAE, porte e demais parâmetros aplicáveis, persistindo somente o subconjunto pertinente.

Uma base SQLite nacional completa será apenas uma alternativa futura e opcional, caso o volume e a frequência das consultas comprovem que o custo operacional compensa.

### 5.2 Google Maps

O Maps será fonte de descoberta complementar e enriquecimento, nunca a fonte cadastral principal. Poderá fornecer:

- nome e categoria;
- endereço e coordenadas;
- telefone;
- website;
- link do estabelecimento;
- presença e avaliações, quando úteis.

O scraper deverá rodar como serviço isolado e ser acionado por API/job. A concorrência deve ser conservadora e configurável.

### 5.3 Website crawler

Será desenvolvido um crawler próprio, restrito às empresas candidatas e aos domínios conhecidos.

Páginas prioritárias:

```text
/
/sobre
/empresa
/servicos
/solucoes
/produtos
/segmentos
/setores
/clientes
/cases
/projetos
/noticias
/blog
/carreiras
/trabalhe-conosco
```

Guardar URL, título, texto extraído, hash e data da coleta. HTML bruto não deverá ser mantido indefinidamente sem necessidade.

O crawler deverá respeitar limites por domínio, timeout, tamanho máximo, tipos de conteúdo aceitos e políticas aplicáveis do site.

### 5.4 Vagas

Vagas são evidências de momento, não um produto do sistema. O `JobsAdapter` deverá normalizar empresa, cargo, descrição, local, data e URL antes de gerar sinais.

Exemplos relevantes:

- planejador ou gerente de manutenção;
- PCM e confiabilidade;
- supervisor de produção;
- engenharia de processos;
- melhoria contínua e OEE;
- SAP PM, automação e Indústria 4.0.

### 5.5 Monitoramento

O monitoramento recorrente de páginas poderá usar changedetection.io em fase posterior, por webhook. Não é requisito obrigatório do primeiro corte funcional, mas o contrato do `MonitoringAdapter` deverá existir no desenho.

## 6. Conhecimento dos produtos Synapse

### 6.1 Synapse MES

Foco: execução e visibilidade da produção.

Capacidades e dores relacionadas:

- ordens e apontamentos de produção;
- máquinas, turnos e metas;
- OEE, disponibilidade, performance e qualidade;
- paradas, motivos, perdas, refugo e gargalos;
- controles em planilhas e dados disponíveis tarde demais;
- início manual ou semiautomático, sem exigir CLP;
- evolução posterior para automação e Pulse.

Referência: <https://synapseindustring.com.br/mes>

### 6.2 Synapse CMMS

Foco: manutenção, PCM e confiabilidade.

Capacidades e dores relacionadas:

- cadastro e criticidade de ativos;
- ordens corretivas e preventivas;
- backlog, calendário, responsáveis e prioridades;
- peças, fornecedores, manuais e histórico técnico;
- MTTR, MTBF e reincidência;
- chamados informais por WhatsApp;
- histórico disperso e dependência de conhecimento individual;
- manutenção reativa e indicadores frágeis em planilhas.

Referência: <https://synapseindustring.com.br/cmms>

### 6.3 Synapse Pulse

Foco: observabilidade, dados de processo e decisão industrial.

Capacidades e dores relacionadas:

- historian, séries temporais, eventos e tendências;
- alertas por condição e severidade;
- telemetria, sensores, IoT, gateways, MQTT, OPC-UA e APIs;
- temperatura, pressão, vibração, corrente e outras variáveis;
- análise de desvios por período, turno ou lote;
- confiabilidade, disponibilidade e priorização de reparos;
- excesso de alarmes sem contexto;
- dados de processo armazenados sem gerar ação.

Referência: <https://synapseindustring.com.br/pulse>

### 6.4 Perfil de parceiro

Parceiros prioritários são consultorias e empresas técnicas que:

- já atendem indústrias e possuem carteira ativa;
- atuam em Lean, OEE, PCM, TPM, manutenção, confiabilidade, produção, automação ou excelência operacional;
- participam da execução e da rotina do cliente;
- conseguem identificar oportunidades concretas;
- querem incorporar software sem desenvolver plataforma própria;
- têm potencial para criar uma oferta recorrente.

Referência: <https://synapseindustring.com.br/>

## 7. Signal Engine

Todo `Signal` deverá conter:

- empresa;
- tipo;
- produto relacionado;
- fonte e URL;
- título e evidência textual curta;
- data de detecção;
- peso-base;
- indicação de decay;
- estado ativo;
- expiração, quando aplicável.

Tipos iniciais incluem PCM, manutenção, OEE, Lean, TPM, confiabilidade, gestão de ativos, produção, PCP, MES, CMMS, ERP, SAP, TOTVS, automação, digitalização, expansão, nova fábrica, nova linha, contratação, energia, paradas, preventiva, preditiva, telemetria, sensores, historian e processo em planilhas.

Detecção será feita por regras explícitas de palavras, expressões, campos estruturados e condições. Toda detecção deverá conservar a evidência.

## 8. Scoring de indústrias

Os scores serão independentes e limitados a `0..100`:

- `ICP Score`: fit estrutural estável;
- `MES Fit Score`;
- `CMMS Fit Score`;
- `Pulse Fit Score`;
- `Intent Score`: momento comercial com maior sensibilidade temporal;
- `Priority Score`: prioridade final calculada.

O melhor fit entre MES, CMMS e Pulse será o `Best Product Fit`.

Fórmula inicial configurável:

```text
Priority Score =
    (ICP Score × 0,35) +
    (Best Product Fit × 0,35) +
    (Intent Score × 0,30)
```

Temperaturas iniciais:

| Priority Score | Temperature |
|---:|---|
| 80–100 | HOT |
| 65–79 | WARM |
| 45–64 | WATCH |
| 0–44 | COLD |
| exclusão crítica | DISQUALIFIED |

`DISQUALIFIED` será uma regra independente do valor numérico.

### 8.1 Recência

Decay inicial configurável para sinais conjunturais:

| Idade | Multiplicador |
|---:|---:|
| 0–30 dias | 100% |
| 31–60 dias | 80% |
| 61–90 dias | 60% |
| 91–180 dias | 30% |
| mais de 180 dias | 10% ou expirado |

CNAE, porte, segmento e localização não sofrem decay. Vagas, notícias, expansão, contratação e projetos sofrem decay.

### 8.2 Explain Score

Todo score deverá expor:

- regra aplicada;
- pontos-base;
- multiplicador de recência;
- pontos efetivos;
- fonte e evidência;
- data do sinal ou dado estrutural.

Nunca mostrar somente um score agregado.

## 9. Scoring de parceiros

Parceiros não utilizarão o Industry Priority Score. Calcular:

- `Partner Fit`;
- `Channel Potential`;
- `Partner Activity`;
- `Conflict Score` ou penalidade de conflito;
- `Partner Priority Score`.

Fórmula inicial configurável:

```text
Partner Priority =
    (Partner Fit × 0,45) +
    (Channel Potential × 0,35) +
    (Partner Activity × 0,20) -
    Conflict Penalty
```

Classificação inicial:

| Score | Classification |
|---:|---|
| 80–100 | PRIORITY PARTNER |
| 65–79 | WARM PARTNER |
| 45–64 | WATCH |
| 0–44 | LOW PRIORITY |
| conflito crítico | CONFLICT |

Conflitos incluem CMMS próprio, MES próprio, produto concorrente, revenda concorrente e parceria exclusiva incompatível.

## 10. Estado comercial e override

Temperatura/classificação e estágio comercial são independentes.

Status de indústria:

```text
NEW
REVIEWED
CONTACT_PENDING
CONTACTED
MEETING
OPPORTUNITY
CUSTOMER
LOST
DO_NOT_CONTACT
```

Status de parceiro:

```text
NEW
REVIEWED
CONTACT_PENDING
CONTACTED
MEETING
PARTNERSHIP_DISCUSSION
PARTNER
REJECTED
CONFLICT
```

O override manual deverá guardar valor calculado, valor manual, usuário, data e motivo opcional. Um recálculo nunca apagará silenciosamente o override.

## 11. Rule Engine

Todos estes elementos deverão ser persistidos e editáveis pelo painel administrativo:

- pesos dos sinais;
- condições e palavras-chave;
- produto e dimensão afetados;
- limites mínimo e máximo;
- pesos das fórmulas;
- thresholds de temperatura;
- curvas de decay;
- regras de exclusão;
- conflitos de parceiros;
- vigência e ativação.

Alterações deverão ter histórico. O sistema deverá permitir recalcular uma empresa, uma consulta ou todo o conjunto selecionado.

## 12. Jobs e resiliência

Tipos iniciais:

```text
SYNC_CNPJ_SOURCE
DISCOVER_CNPJ
DISCOVER_MAPS
ENRICH_MAPS
CRAWL_WEBSITE
FIND_JOBS
DETECT_SIGNALS
CALCULATE_SCORE
REFRESH_COMPANY
```

Cada job deverá registrar status, parâmetros, início, término, registros processados, sucessos, falhas e erros sanitizados.

Para evitar dependências prematuras, o MVP poderá usar uma fila persistida no PostgreSQL e um worker separado baseado no mesmo código da aplicação, com bloqueio transacional. Redis só será introduzido se medições demonstrarem necessidade.

## 13. Interface

Telas iniciais:

- Dashboard;
- Consultas;
- Execução e detalhe de jobs;
- Indústrias;
- Parceiros;
- Detalhe da empresa;
- Sinais e evidências;
- Regras e scoring;
- Fontes e saúde dos adapters.

Direção visual inicial:

- produto interno, denso e legível;
- hierarquia clara entre fit, intenção e prioridade;
- cores de temperatura acessíveis e nunca usadas sem rótulo;
- evidência sempre próxima ao score;
- tabelas com filtros salvos e ordenação;
- responsividade para desktop e tablet;
- identidade visual industrial contemporânea, sem copiar o site institucional.

## 14. Stack proposta

- Python 3.12+;
- Django com templates renderizados no servidor;
- PostgreSQL;
- HTML semântico;
- CSS próprio;
- JavaScript vanilla para interações pontuais;
- worker assíncrono usando tabela de jobs no PostgreSQL;
- Docker multi-stage quando trouxer benefício real;
- Coolify para build e deploy;
- healthcheck e variáveis de ambiente para secrets.

Django é recomendado porque entrega autenticação, migrations, ORM, formulários e painel administrativo configurável com pouca infraestrutura adicional.

## 15. Avaliação preliminar dos repositórios de referência

| Projeto | Uso no Sniper | Integração sugerida | Licença observada | Decisão inicial |
|---|---|---|---|---|
| `rictom/cnpj-sqlite` | referência para baixar e interpretar os arquivos públicos | adaptar o processamento para filtrar em partes e descartar os brutos | MIT | não manter a base SQLite nacional no MVP |
| `rictom/cnpj_consulta` | filtros sobre base CNPJ | reutilizar conceitos e SQL validado | MIT | referência e possível adaptação pontual |
| `rictom/cnpj_api` | acesso HTTP à base local | serviço isolado ou contrato de referência | MIT | avaliar custo de manter serviço separado |
| `gosom/google-maps-scraper` | descoberta complementar e enriquecimento | container separado via REST API | MIT | forte candidato a reutilização |
| `speedyapply/JobSpy` | descoberta de vagas | biblioteca atrás do JobsAdapter | MIT | forte candidato, validar fontes no Brasil |
| `dgtlmoon/changedetection.io` | monitoramento de páginas | serviço separado + webhook | Apache-2.0, com documentação comercial adicional | fase posterior; preservar avisos e limites da licença |
| `Dukotah/leadgen` | arquitetura de pipeline e fontes abertas | somente referência inicialmente | MIT; dados das fontes têm licenças próprias | não transformar o Sniper em uma interface sobre ele |

Antes de incorporar qualquer código, confirmar a licença no commit/tag fixado e registrar atribuições exigidas. Dados coletados podem ter termos e licenças diferentes do código do coletor.

Referências:

- <https://github.com/rictom/cnpj-sqlite>
- <https://github.com/rictom/cnpj_consulta>
- <https://github.com/rictom/cnpj_api>
- <https://github.com/gosom/google-maps-scraper>
- <https://github.com/speedyapply/JobSpy>
- <https://github.com/dgtlmoon/changedetection.io>
- <https://github.com/Dukotah/leadgen>

## 16. Requisitos não funcionais

- determinístico e auditável;
- modular e substituível por adapters;
- regras alteráveis sem deploy;
- preparado para grande volume sem replicação desnecessária;
- migrations obrigatórias;
- índices para CNPJ, tipo, UF, município, CNAE, domínio, status e scores;
- PostgreSQL Full Text Search quando adequado;
- logs sem secrets nem dados pessoais desnecessários;
- coleta moderada, identificável quando cabível e em conformidade com termos e legislação;
- retenção mínima necessária de conteúdo coletado;
- healthchecks para aplicação e workers.

## 17. Fora do escopo inicial

- upload/importação CSV;
- Meta Ads e Google Ads;
- automação de LinkedIn;
- WhatsApp e e-mail automation;
- CRM complexo;
- LLM e machine learning;
- Elasticsearch;
- multi-tenant;
- automação irrestrita ou scraping agressivo.

## 18. Sequência de implementação

### Etapa 0 — documentação e validação técnica

1. examinar integralmente o repositório local;
2. auditar código, releases, manutenção e licenças dos projetos externos;
3. produzir `docs/architecture.md`;
4. produzir `docs/data-model.md`;
5. produzir `docs/scoring-engine.md`;
6. produzir `docs/sources.md`;
7. produzir `docs/deployment.md`;
8. produzir `docs/implementation-plan.md`.

### Etapa 1 — fundação

- container, PostgreSQL, autenticação e migrations;
- modelo de empresa, proveniência, consulta e jobs;
- painel administrativo e layout-base;
- regras configuráveis e auditoria.

### Etapa 2 — descoberta automática

- `CNPJAdapter` com processamento seletivo orientado pelos filtros da consulta;
- cache/base curada no PostgreSQL, sem réplica nacional integral;
- tela de consulta e resultados;
- persistência seletiva e deduplicação;
- `MapsAdapter` para descoberta complementar e enriquecimento.

### Etapa 3 — inteligência

- crawler de websites;
- Signal Engine;
- scores de indústria e parceiros;
- decay, Explain Score, rankings e filtros;
- histórico e overrides.

### Etapa 4 — intenção e acompanhamento

- `JobsAdapter` com JobSpy;
- sinais de vagas e recálculo;
- avaliação/integração futura do changedetection.io.

## 19. Critérios de aceite do primeiro corte funcional

O MVP inicial estará funcional quando um administrador puder:

1. criar uma consulta sem enviar arquivo;
2. selecionar filtros e palavras-chave;
3. iniciar e acompanhar a coleta automática;
4. receber candidatas deduplicadas com proveniência;
5. abrir uma empresa descoberta;
6. visualizar dados cadastrais e evidências públicas;
7. ver ICP, MES, CMMS, Pulse, Intent e Priority separadamente;
8. entender cada parcela do score;
9. filtrar e ordenar o ranking;
10. alterar regras no admin e recalcular;
11. aplicar override sem perder o valor calculado;
12. consultar o histórico de sinais, scores e decisões.

## 20. Regra fundamental

O Sniper não deve concluir apenas que uma empresa “parece boa”. Deve distinguir:

```text
ALTO FIT + ALTO INTENT   → abordar agora
ALTO FIT + BAIXO INTENT  → observar e nutrir
BAIXO FIT + ALTO INTENT  → analisar antes de investir esforço
BAIXO FIT + BAIXO INTENT → baixa prioridade
```

Toda prioridade precisa ser reproduzível, explicável e sustentada por fonte e evidência.
