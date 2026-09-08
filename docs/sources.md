# Fontes externas e avaliação dos projetos de referência

## Método

A avaliação foi feita sobre os repositórios oficiais baixados em 05/09/2026, observando código, dependências, licença, execução, interfaces e aderência ao domínio. Antes de incorporar código, o commit/tag escolhido e sua licença deverão ser fixados no inventário de dependências.

Licença do software não concede automaticamente direito sobre os dados obtidos. Termos das fontes, atribuições e legislação aplicável continuam válidos.

## Resumo de decisões

| Projeto | Licença observada | Decisão |
|---|---|---|
| rictom/cnpj-sqlite | MIT | referência de download/layout; não usar para materializar a base nacional |
| rictom/cnpj_consulta | MIT | aproveitar conceitos de filtros e SQL, reimplementar no domínio |
| rictom/cnpj_api | MIT | não executar no MVP; depende da base completa |
| gosom/google-maps-scraper | MIT | serviço isolado por REST API, versão fixada |
| speedyapply/JobSpy | MIT | biblioteca atrás do JobsAdapter, fontes habilitadas gradualmente |
| dgtlmoon/changedetection.io | Apache-2.0 + arquivo de licença comercial | adiado; revisar termos antes de hospedar/integrar |
| Dukotah/leadgen | MIT | referência e possível adaptação pontual de coletores/padrões |

## rictom/cnpj-sqlite

Repositório: <https://github.com/rictom/cnpj-sqlite>

### O que oferece

- descoberta da competência mais recente via WebDAV da Receita;
- download paralelo dos arquivos ZIP;
- layouts de empresas, estabelecimentos, sócios e Simples;
- carga completa em SQLite usando pandas/Dask;
- índices para consultas posteriores.

### Limitações encontradas

- fluxo interativo e orientado a execução manual;
- espera o conjunto completo de arquivos;
- extrai os ZIPs antes da carga;
- cria tabelas e índices nacionais, consumindo muito disco;
- caminhos/configuração locais e pouca separação em biblioteca;
- não há Dockerfile, API, testes ou abstração de adapter;
- download possui pontos sem timeout explícito;
- dependências mais pesadas que o necessário para filtragem seletiva.

### Decisão

Usar como referência do layout, competência e correções de formato. Criar um downloader/processador próprio, não interativo, com checksum, streaming em chunks, filtros antecipados e limpeza segura de temporários.

Não incluir sócios no MVP.

### Situação da origem oficial

Em 08/09/2026, o caminho Apache histórico de `dados_abertos_cnpj` respondeu `404`. O
recurso oficial apontado pelo catálogo da Receita está disponível como compartilhamento
público Nextcloud/WebDAV em `arquivos.receitafederal.gov.br`. O Sniper usa a URL WebDAV e
o token somente por configuração, pois o identificador do compartilhamento pode ser
rotacionado.

A listagem real confirmou a competência `2026-08`, com 10 partes de Estabelecimentos,
10 de Empresas e um arquivo Simples. A sincronização do manifesto faz apenas `PROPFIND`;
nenhum ZIP é transferido nessa etapa. Uma competência incompleta nunca substitui o
manifesto atual válido.

## rictom/cnpj_consulta

Repositório: <https://github.com/rictom/cnpj_consulta>

### O que oferece

Filtros por CNPJ, UF, município, CEP, bairro, natureza jurídica, CNAE principal/secundário, situação, porte, Simples, MEI, datas e capital social. Usa parâmetros SQL para valores e uma UI PyWebIO.

### Limitações

- exige `cnpj.db` completo e índices adicionais custosos;
- aplicação e query builder estão fortemente acoplados num script;
- exportação/GUI não interessam ao Sniper;
- parte da construção dinâmica deverá ser substituída por filtros tipados;
- classificação de porte da Receita não separa médio de grande no código `05`.

### Decisão

Reimplementar filtros com objetos validados. Aproveitar o entendimento dos joins e códigos, mantendo testes próprios.

## rictom/cnpj_api

Repositório: <https://github.com/rictom/cnpj_api>

### O que oferece

FastAPI/aiosqlite para consulta por CNPJ e parâmetros, em cima do mesmo `cnpj.db` completo.

### Limitações

- o processo de startup pode criar índices/tabelas que levam horas;
- carrega metadados globais no import;
- configuração por INI e dependência rígida de arquivo local;
- inclui pandas, PyWebIO e código legado além do necessário;
- não resolve a necessidade de base curada.

### Decisão

Não executar como serviço no MVP. O contrato HTTP é uma referência para uma futura implementação do `CNPJAdapter`, não uma dependência imediata.

## gosom/google-maps-scraper

Repositório: <https://github.com/gosom/google-maps-scraper>

### O que oferece

- implementação ativa em Go;
- Dockerfile com Chromium/Playwright;
- CLI, Web UI e REST API de jobs;
- dados de nome, categoria, endereço, telefone, website, coordenadas e outros;
- concorrência, proxies, timeouts, JSON/CSV e PostgreSQL;
- componentes de filas e rate limit na edição ampliada.

### Decisão

Executar a edição open source mínima em container separado. O Sniper cria jobs, acompanha o estado e importa programaticamente o resultado pelo `MapsAdapter`. Não acoplar ao banco interno do scraper nem usar sua edição SaaS.

Começar com concorrência baixa e volume limitado. Fixar imagem por digest/tag, não `latest`.

### Riscos

- consumo de CPU/RAM pelo navegador;
- bloqueios e mudanças na interface da fonte;
- termos do Google Maps não são substituídos pela licença MIT do scraper;
- resultados não possuem a autoridade cadastral do CNPJ.

## speedyapply/JobSpy

Repositório: <https://github.com/speedyapply/JobSpy>

### O que oferece

- biblioteca Python 3.10+;
- LinkedIn, Indeed, Glassdoor, Google e outros;
- execução concorrente entre fontes;
- localização, data, empresa, cargo, URL e descrição;
- Brasil disponível no enum usado pelo Indeed;
- proxies, timeout e retry em partes da implementação.

### Limitações

- políticas de delay/retry variam entre scrapers;
- APIs e HTML das plataformas mudam frequentemente;
- correspondência do nome da vaga com a Company precisa ser feita pelo Sniper;
- DataFrame/pandas adiciona custo ao worker;
- fontes podem bloquear datacenters ou proibir automação.

### Decisão

Usar como biblioteca isolada pelo `JobsAdapter`, preferencialmente em job próprio. Habilitar uma fonte por vez após teste brasileiro. Normalizar imediatamente e conservar URL/evidência. Crawler direto de `/carreiras` da empresa é a alternativa prioritária quando existir.

## dgtlmoon/changedetection.io

Repositório: <https://github.com/dgtlmoon/changedetection.io>

### O que oferece

- projeto maduro, Docker e API;
- fetch simples ou por browser;
- histórico de alterações e notificações/webhooks;
- controle de workers e intervalo mínimo;
- opção de desabilitar recursos de LLM.

### Licenciamento

O repositório contém Apache-2.0 e também `COMMERCIAL_LICENCE.md`, que declara condições para atividade comercial envolvendo hosting para terceiros. Como o MVP é interno e a integração está adiada, não há dependência agora. Antes de qualquer oferta externa ou incorporação, obter revisão jurídica/confirmar interpretação com o mantenedor.

### Decisão

Não integrar no MVP. Manter apenas o `MonitoringAdapter` conceitual. Avaliar serviço separado e webhook em fase posterior, com `LLM_FEATURES_DISABLED=true`.

## Dukotah/leadgen

Repositório: <https://github.com/Dukotah/leadgen>

### O que oferece

- pipeline collect, dedupe, enrich, suppress, score e export;
- fontes Overture, OpenStreetMap/Overpass, Wikidata e outras;
- leitura remota do Overture via DuckDB/httpfs com bounding box;
- fallback entre endpoints Overpass e retry básico;
- normalização, proximidade geográfica, merge e qualidade;
- verticais configuráveis e scoring explicável;
- testes offline.

### Limitações

- verticais e normalização telefônica atuais são orientadas aos EUA;
- pipeline em memória e saída para arquivos não atendem persistência/auditoria do Sniper;
- deduplicação por nome pode gerar falso positivo;
- licenças dos dados variam: Overture é CC-BY; OSM é ODbL;
- fontes municipais Socrata/NPI são pouco relevantes ao Brasil.

### Decisão

Usar arquitetura como referência. Avaliar adaptação isolada dos coletores Overture/OSM e algoritmos geométricos, com atribuição e testes brasileiros. Não reutilizar seu score nem transformar o Sniper em frontend do projeto.

## Ordem de adoção das fontes

1. CNPJ seletivo;
2. Overture/OSM para descoberta complementar;
3. website institucional;
4. Google Maps com limite conservador;
5. páginas de carreiras e JobSpy;
6. changedetection.io, se aprovado posteriormente.

## Checklist para habilitar uma fonte

- licença do commit/tag registrada;
- termos dos dados revisados;
- adapter e DTO normalizado;
- timeout, limites, retry e idempotência;
- user-agent e atribuição adequados;
- teste pequeno em ambiente controlado;
- healthcheck e kill switch;
- política de retenção;
- fixtures offline para testes;
- nenhuma fonte decide score diretamente.
