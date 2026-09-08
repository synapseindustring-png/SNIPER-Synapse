Quero que você projete e implemente um novo sistema chamado **Synapse Sniper**.

O Synapse Sniper será uma plataforma interna de inteligência comercial B2B focada no mercado industrial brasileiro.

O sistema deve localizar, enriquecer, classificar, pontuar e acompanhar dois tipos diferentes de entidades:

1. **Indústrias de pequeno e médio porte**, potenciais clientes dos produtos Synapse.
2. **Consultorias, engenharias, integradores e empresas de serviços industriais**, potenciais parceiros comerciais e canais de distribuição.

O objetivo não é criar um CRM genérico nem simplesmente raspar listas de empresas.

O objetivo é construir um **radar comercial industrial** capaz de responder:

### Para indústrias

- Esta empresa pertence ao nosso ICP?
- Qual é seu porte?
- Qual seu segmento industrial?
- Onde está localizada?
- Existem sinais públicos de necessidade de MES, CMMS ou Pulse?
- Existem sinais de expansão, contratação, manutenção, PCM, OEE, produção, digitalização ou melhoria operacional?
- Qual produto Synapse possui maior aderência?
- Por que o sistema atribuiu determinado score?
- Esta empresa deve ser prospectada agora, observada ou descartada?

### Para parceiros

- Esta empresa trabalha dentro de indústrias?
- Qual é sua especialidade?
- Atua com PCM, manutenção, Lean, OEE, engenharia, produção, automação, ERP, confiabilidade, Indústria 4.0 etc.?
- Possui clientes industriais?
- Possui software próprio concorrente?
- Revende soluções concorrentes?
- Poderia incorporar MES, CMMS ou Pulse aos seus projetos?
- Qual é seu potencial como parceiro Synapse?
- Por que recebeu determinado Partner Score?

---

# PRINCÍPIOS DO PRODUTO

O sistema deve ser:

- determinístico;
- auditável;
- simples;
- modular;
- orientado a dados;
- preparado para automação futura;
- fácil de operar;
- fácil de alterar regras;
- preparado para grande volume de empresas.

**Não utilizar LLM/IA para decidir score, ICP, classificação ou prioridade.**

Scores devem ser calculados através de regras explícitas armazenadas no sistema.

Se futuramente IA for adicionada para interpretação de texto, ela nunca poderá ser a única responsável pela decisão comercial.

---

# INFRAESTRUTURA

O sistema será hospedado em:

- Coolify
- PostgreSQL
- Docker

A aplicação deve ser completamente containerizada.

Não criar dependências desnecessárias de serviços externos.

Preferir tecnologias open source e componentes que possam ser executados dentro da nossa própria infraestrutura.

---

# REPOSITÓRIOS OPEN SOURCE DE REFERÊNCIA

Antes de implementar os coletores, examine os seguintes projetos.

O objetivo NÃO é necessariamente incorporar integralmente esses repositórios.

Analise:

- arquitetura;
- componentes reutilizáveis;
- dependências;
- licença;
- manutenção;
- interface disponível;
- capacidade de execução em Docker;
- possibilidade de integração por subprocesso, biblioteca, API ou serviço separado.

O Synapse Sniper deve possuir sua própria arquitetura e banco de dados.

Os projetos externos devem ficar atrás de adapters para que possam ser substituídos no futuro.

---

## 1. RICTOM / CNPJ-SQLITE

Repository:

**rictom/cnpj-sqlite**

Função no Sniper:

Criar e manter uma base local consultável dos dados públicos de CNPJ da Receita Federal.

Este será potencialmente um dos principais mecanismos de descoberta inicial de empresas.

Usos esperados:

- CNPJ;
- razão social;
- nome fantasia;
- situação cadastral;
- CNAE principal;
- CNAEs secundários;
- porte;
- natureza jurídica;
- capital social;
- município;
- UF;
- endereço;
- data de abertura.

Queremos conseguir descobrir:

- indústrias;
- consultorias;
- engenharias;
- integradores;
- prestadores de serviços industriais.

A base não deve obrigatoriamente ser misturada ao PostgreSQL principal do Sniper.

Avalie a melhor estratégia.

Pode existir, por exemplo:

CNPJ SQLite
      ↓
CNPJ Adapter
      ↓
Sniper PostgreSQL

O PostgreSQL do Sniper deve armazenar somente empresas relevantes ou selecionadas, evitando replicar desnecessariamente toda a base pública brasileira se não houver benefício técnico.

---

## 2. RICTOM / CNPJ_CONSULTA

Repository:

**rictom/cnpj_consulta**

Função:

Servir como referência para consultas e filtros sobre a base CNPJ.

Estudar principalmente lógica de:

- CNAE;
- município;
- UF;
- porte;
- situação cadastral;
- capital social;
- filtros combinados;
- exportação de resultados.

Não precisamos necessariamente utilizar a interface original.

Queremos incorporar ao Sniper a capacidade de fazer consultas como:

UF = MG

CNAE = indústria de alimentos

Situação = ativa

Porte = pequeno/médio

Resultado:

lista de empresas candidatas ao ICP.

---

## 3. RICTOM / CNPJ_API

Repository:

**rictom/cnpj_api**

Analisar como alternativa ou complemento ao acesso direto à base CNPJ.

Objetivo:

Criar uma abstração:

CNPJAdapter

que possa futuramente trabalhar com:

- SQLite local;
- API local;
- outro serviço;
- banco próprio.

O restante do Sniper não deve saber qual implementação está sendo utilizada.

---

## 4. GOSOM / GOOGLE-MAPS-SCRAPER

Repository:

**gosom/google-maps-scraper**

Função esperada:

Enriquecimento das empresas previamente identificadas.

Possíveis informações:

- website;
- telefone;
- endereço;
- localização;
- categoria;
- descrição;
- coordenadas;
- presença no Google Maps.

O Maps NÃO deve ser usado como banco principal de empresas.

Fluxo preferencial:

CNPJ
→ empresa candidata
→ Maps
→ enriquecimento

Criar:

MapsAdapter

Não espalhar código específico do scraper dentro do domínio principal.

O adapter deverá suportar:

- rate limiting;
- timeout;
- retry;
- logging;
- processamento assíncrono.

---

## 5. SPEEDYAPPLY / JOBSPY

Repository:

**speedyapply/JobSpy**

Função esperada:

Encontrar vagas públicas associadas às empresas e transformar essas vagas em **sinais comerciais**.

O Sniper NÃO será um agregador de vagas.

Uma vaga será uma evidência sobre o momento da empresa.

Exemplos:

Planejador de Manutenção
→ possível estruturação/expansão de PCM

Gerente de Manutenção
→ movimento na gestão de manutenção

Engenheiro de Processos
→ melhoria operacional

Analista de Melhoria Contínua
→ Lean/OEE

Especialista SAP PM
→ transformação dos processos de manutenção

Supervisor de Produção
→ crescimento ou reorganização operacional

Criar:

JobsAdapter

A saída deve ser normalizada antes de entrar no Signal Engine.

---

## 6. DGTLMOON / CHANGEDETECTION.IO

Repository:

**dgtlmoon/changedetection.io**

Não é obrigatório para o primeiro MVP, mas deve ser estudado para a etapa de monitoramento.

Função futura:

Monitorar páginas específicas de empresas já classificadas como relevantes.

Exemplo:

/carreiras
/noticias
/imprensa
/blog
/investimentos

Detectar mudanças relacionadas a:

- nova fábrica;
- expansão;
- nova linha;
- contratação;
- digitalização;
- manutenção;
- produção;
- investimento;
- automação.

Pode funcionar como serviço separado conectado ao Sniper através de webhook.

Fluxo futuro:

changedetection
→ webhook
→ Sniper
→ análise
→ Signal
→ recálculo de score

Não implementar obrigatoriamente nesta primeira fase.

---

## 7. DUKOTAH / LEADGEN

Repository:

**Dukotah/leadgen**

Este projeto deve ser analisado principalmente como **referência arquitetural de pipeline de leads**.

Estudar particularmente conceitos como:

collect
→ deduplicate
→ enrich
→ suppress
→ score
→ export

Não quero simplesmente instalar o Leadgen e transformar o Synapse Sniper em uma interface sobre ele.

Avalie quais conceitos, padrões ou componentes podem ser aproveitados.

Nosso domínio é muito mais específico:

**industrial B2B brasileiro.**

O nosso diferencial estará no:

- ICP industrial;
- Signal Engine;
- Industry Score;
- Product Fit;
- Partner Score;
- Partner Fit;
- histórico dos sinais;
- evidência;
- inteligência comercial.

---

# ARQUITETURA DE ADAPTERS

Todos os coletores externos devem seguir uma interface conceitual comum.

Exemplo:

SourceAdapter

- CNPJAdapter
- MapsAdapter
- WebsiteAdapter
- JobsAdapter
- MonitoringAdapter

Uma fonte nunca deve escrever diretamente nas regras de negócio.

Fluxo:

EXTERNAL SOURCE

        ↓

SOURCE ADAPTER

        ↓

NORMALIZATION

        ↓

RAW / SOURCE DATA

        ↓

SIGNAL ENGINE

        ↓

SCORING ENGINE

        ↓

COMPANY / PARTNER

---

# PRIMEIRO MÓDULO: EMPRESAS

Toda organização deve possuir uma entidade central.

Estrutura conceitual:

Company

- id
- cnpj
- razão social
- nome fantasia
- tipo
- situação cadastral
- CNAE principal
- CNAEs secundários
- porte
- capital social
- data de abertura
- endereço
- município
- UF
- CEP
- latitude
- longitude
- telefone
- email
- website
- LinkedIn
- Google Maps
- número estimado de funcionários
- segmento
- origem
- data de criação
- última atualização

Tipos principais:

INDUSTRY
CONSULTANCY
INTEGRATOR
ENGINEERING
SERVICE_PROVIDER
OTHER

Não duplicar empresas caso apareçam em fontes diferentes.

CNPJ deve ser o identificador preferencial quando disponível.

---

# DATA PROVENANCE

Toda informação enriquecida deve saber sua origem.

Exemplo:

website

value:
empresa.com.br

source:
google_maps

collected_at:
...

O sistema deve distinguir:

valor atual
origem
data da coleta
confiança quando aplicável.

---

# WEBSITE CRAWLER

O Sniper deverá conseguir visitar websites das empresas selecionadas.

Não fazer crawler indiscriminado da internet.

Fluxo:

empresa identificada
→ website descoberto
→ crawler visita páginas relevantes

Priorizar:

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

Guardar:

- URL;
- título;
- texto extraído;
- data da coleta;
- hash do conteúdo.

Não armazenar HTML bruto indefinidamente quando não for necessário.

---

# SIGNAL ENGINE

Esta é uma das partes centrais do produto.

Criar entidade:

Signal

Campos conceituais:

- id
- company_id
- signal_type
- product
- source
- source_url
- title
- evidence
- detected_at
- weight
- active
- expires_at

Exemplos:

PCM
MAINTENANCE
OEE
LEAN
TPM
RELIABILITY
ASSET_MANAGEMENT
PRODUCTION
PCP
MES
CMMS
ERP
SAP
TOTVS
INDUSTRY_4_0
AUTOMATION
DIGITALIZATION
EXPANSION
NEW_FACTORY
NEW_PRODUCTION_LINE
HIRING
ENERGY
DOWNTIME
PREVENTIVE_MAINTENANCE
PREDICTIVE_MAINTENANCE
SPREADSHEET_PROCESS

Todo Signal precisa possuir evidência e fonte.

---

# SCORE DE INDÚSTRIA

Criar motor configurável.

Nunca hardcodar pesos exclusivamente no código.

Exemplo inicial:

CNAE compatível: +30
porte compatível: +15
capital social compatível: +5
website: +5
vaga manutenção: +10
vaga PCM: +20
vaga gerente manutenção: +15
OEE: +15
digitalização: +15
expansão: +15
nova linha: +15
estruturação PCM: +25
processo em planilhas: +20

Exclusões:

empresa inativa: descarte
MEI: -50
comércio puro: -50
sem atividade industrial: -40

Os números são seeds iniciais e deverão ser configuráveis.

---

# SCORE POR PRODUTO

Toda indústria deverá possuir:

ICP Score
MES Score
CMMS Score
Pulse Score

Exemplo:

ABC Alimentos

ICP: 88
MES: 76
CMMS: 94
Pulse: 51

Todo score precisa ser explicável.

---

# CONSULTORIAS E PARCEIROS

Criar pipeline independente.

Tipos:

CONSULTING_PROCESS
MAINTENANCE_CONSULTING
LEAN_CONSULTING
RELIABILITY
ENGINEERING
AUTOMATION_INTEGRATOR
ERP_INTEGRATOR
INDUSTRY_4_0
ENERGY
OTHER

Não limitar a pesquisa à palavra "consultoria".

Também procurar empresas de:

- engenharia;
- automação;
- integração;
- manutenção;
- confiabilidade;
- Lean;
- melhoria contínua;
- ERP;
- Indústria 4.0;
- produtividade.

---

# PARTNER SIGNAL ENGINE

Detectar:

- atende indústrias;
- cases industriais;
- PCM;
- manutenção;
- Lean;
- OEE;
- melhoria contínua;
- confiabilidade;
- engenharia de produção;
- automação;
- ERP;
- SAP;
- TOTVS;
- Indústria 4.0;
- equipe técnica;
- múltiplos estados;
- PMEs industriais.

Também detectar conflitos:

- CMMS próprio;
- MES próprio;
- produto concorrente;
- revenda concorrente.

---

# PARTNER SCORE

Exemplo inicial:

atende indústrias: +20
PCM/manutenção: +15
Lean/OEE: +15
engenharia industrial: +10
cases industriais: +10
vários estados: +10
equipe técnica: +10
ERP sem MES: +10
consultoria sem software próprio: +20
PMEs industriais: +15

Conflitos:

CMMS próprio: -40
MES próprio: -40
revenda concorrente: -30
enterprise-only: -15

Gerar:

Partner Score
MES Partner Fit
CMMS Partner Fit
Pulse Partner Fit

---

# STATUS

Industry:

HOT
WARM
WATCH
COLD
DISQUALIFIED

Prospect:

NEW
REVIEWED
CONTACT_PENDING
CONTACTED
MEETING
OPPORTUNITY
CUSTOMER
LOST
DO_NOT_CONTACT

Partner:

NEW
REVIEWED
CONTACT_PENDING
CONTACTED
MEETING
PARTNERSHIP_DISCUSSION
PARTNER
REJECTED
CONFLICT

---

# INTERFACE

Criar:

Dashboard
Industries
Partners
Company Detail
Signals
Rules
Imports
Jobs

---

# DASHBOARD

Mostrar:

- empresas totais;
- indústrias;
- parceiros;
- ICP válido;
- Hot Leads;
- Warm Leads;
- parceiros prioritários;
- sinais detectados;
- novos sinais;
- empresas adicionadas.

---

# INDUSTRIES

Tabela:

Empresa
Cidade
UF
Segmento
Porte
ICP
MES
CMMS
Pulse
Signals
Status
Atualização

Filtros:

UF
cidade
CNAE
segmento
porte
ICP
MES
CMMS
Pulse
signal
status

---

# PARTNERS

Tabela:

Empresa
Cidade
UF
Tipo
Especialidade
Partner Score
MES Fit
CMMS Fit
Pulse Fit
Conflitos
Status

---

# COMPANY DETAIL

Mostrar:

- cadastro;
- localização;
- website;
- CNAE;
- segmento;
- porte;
- scores;
- signals;
- evidências;
- fontes;
- histórico;
- status comercial;
- notas.

---

# EXPLAIN SCORE

Obrigatório.

Exemplo:

CMMS SCORE: 91

+25 Estruturação PCM  
Fonte: vaga publicada

+20 Planejador de manutenção  
Fonte: vaga publicada

+15 Médio porte  
Fonte: CNPJ

+15 Manutenção preventiva  
Fonte: website

+10 Segmento prioritário  
Fonte: CNAE

O usuário precisa sempre entender por que determinada empresa está no topo.

---

# RULE ENGINE

Criar configuração persistida.

Campos:

name
entity_type
product
signal_type
condition
weight
active
valid_from
valid_until

Permitir recalcular scores.

---

# JOB SYSTEM

Criar arquitetura para:

IMPORT_CNPJ
ENRICH_MAPS
CRAWL_WEBSITE
FIND_JOBS
DETECT_SIGNALS
CALCULATE_SCORE
REFRESH_COMPANY

Cada job:

status
started_at
finished_at
records_processed
records_success
records_failed
error_log

---

# RATE LIMIT E RESILIÊNCIA

Adapters precisam suportar:

- rate limit;
- retry;
- exponential backoff;
- timeout;
- logging.

Nunca criar scraping agressivo.

---

# DEDUPLICAÇÃO

Prioridade:

1. CNPJ
2. domínio
3. telefone
4. razão social + endereço

---

# HISTÓRICO

Manter evolução de scores e sinais.

Exemplo:

01/09
CMMS 58

15/09
vaga PCM
CMMS 78

02/10
expansão
CMMS 88

---

# IMPORTAÇÃO CSV

Criar desde a primeira versão.

Fluxo:

Upload
→ mapeamento
→ validação
→ deduplicação
→ importação
→ classificação
→ scoring

Isso permite testar o sistema sem depender dos scrapers.

---

# POSTGRESQL

Usar migrations.

Criar índices apropriados para:

cnpj
company_type
state
city
cnae
website_domain
status
scores

Utilizar PostgreSQL Full Text Search quando adequado.

Não adicionar Elasticsearch agora.

---

# COOLIFY

Deployment esperado:

git push
→ Coolify
→ build
→ deploy

Criar:

Dockerfile
compose quando necessário
healthcheck
env.example

Secrets somente via variáveis de ambiente.

---

# AUTENTICAÇÃO

Sistema interno inicialmente.

Roles previstas:

ADMIN
ANALYST
SALES

Somente ADMIN precisa estar completamente funcional no primeiro MVP.

---

# DOCUMENTAÇÃO

Criar:

docs/architecture.md
docs/data-model.md
docs/scoring-engine.md
docs/sources.md
docs/deployment.md
docs/implementation-plan.md

README.md completo.

---

# NÃO IMPLEMENTAR AGORA

Não implementar nesta primeira etapa:

Meta Ads
Google Ads
LinkedIn automation
WhatsApp
email automation
CRM complexo
LLM
machine learning
Elasticsearch

Apenas preparar arquitetura para integrações futuras.

---

# ORDEM DE IMPLEMENTAÇÃO

Não tente integrar todos os repositórios imediatamente.

## Fase 1 — Core

- aplicação;
- PostgreSQL;
- autenticação;
- Company;
- Industry;
- Partner;
- importação CSV;
- Signal Engine;
- Rule Engine;
- scoring;
- Explain Score;
- dashboard;
- filtros.

## Fase 2 — CNPJ

Estudar e integrar:

- rictom/cnpj-sqlite;
- rictom/cnpj_consulta;
- rictom/cnpj_api se fizer sentido.

Objetivo:

descoberta automática de empresas brasileiras.

## Fase 3 — Enriquecimento

Integrar/avaliar:

- gosom/google-maps-scraper;
- crawler próprio de websites.

## Fase 4 — Intent Signals

Integrar/avaliar:

- speedyapply/JobSpy.

Transformar vagas em signals.

## Fase 5 — Monitoramento

Integrar/avaliar:

- dgtlmoon/changedetection.io.

## Referência arquitetural

Durante o desenho do pipeline estudar:

- Dukotah/leadgen.

---

# PRIMEIRO VERTICAL SLICE REAL

O primeiro fluxo completo que quero ver funcionando é:

CNPJ
    ↓
descobrir empresa
    ↓
importar para Sniper
    ↓
classificar Industry ou Partner
    ↓
gerar sinais básicos
    ↓
calcular score
    ↓
mostrar no ranking
    ↓
abrir Company Detail
    ↓
explicar score

Exemplo:

UF = MG
Entity = Industry
Segmento = Alimentos
CMMS >= 70

Resultado:

ABC Alimentos    91
XYZ Bebidas      84
QWE Laticínios   76

E:

Entity = Partner
Especialidade = PCM
Partner Score >= 80

Consultoria A    94
Engenharia B     89
Lean C           83

---

# ANTES DE CODIFICAR

Faça obrigatoriamente:

1. examine o repositório atual;
2. examine os repositórios open source citados;
3. confirme licença e compatibilidade de cada um;
4. determine o que será reutilizado e o que será apenas referência;
5. escolha a stack específica da aplicação;
6. desenhe o schema PostgreSQL;
7. desenhe os adapters;
8. produza architecture.md;
9. produza data-model.md;
10. produza implementation-plan.md;
11. divida em fases;
12. somente então comece a implementação.

Não copie cegamente código de terceiros.

Não introduza dependência externa sem justificar.

Não faça overengineering.

---

# CRITÉRIO CENTRAL DO SYNAPSE SNIPER

A aplicação não existe simplesmente para mostrar empresas.

Ela precisa responder:

**Quem devo atacar comercialmente agora e por quê?**

Para clientes:

**Qual indústria possui fit + dor + momento?**

Para parceiros:

**Qual consultoria/integrador já possui acesso ao nosso cliente e poderia distribuir nossas soluções?**

Essa é a essência do Synapse Sniper.