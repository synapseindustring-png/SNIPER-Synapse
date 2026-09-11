# Deploy e operação

## Topologia no Coolify

O repositório produzirá uma única imagem da aplicação, usada com comandos diferentes:

```text
web     → gunicorn config.wsgi
worker  → python manage.py run_worker
```

Serviços:

- aplicação web;
- worker;
- etapa de release/migration executada uma única vez antes de web e worker;
- PostgreSQL gerenciado pelo Coolify ou recurso dedicado;
- google-maps-scraper opcional e privado;
- volume temporário controlado para processamento de fontes.

O Maps não deverá ficar exposto publicamente. Apenas a rede interna do projeto poderá acessá-lo.

## Build

- Dockerfile reproduzível;
- dependências Python travadas por versão e hashes quando o fluxo for estabilizado;
- usuário não-root no runtime;
- arquivos estáticos coletados no build ou startup controlado;
- migrations executadas como etapa explícita de release; web e worker aguardam sua conclusão;
- imagem sem credenciais, dados coletados ou ferramentas de desenvolvimento;
- healthcheck HTTP em `/health/live` e `/health/ready`.

## Variáveis de ambiente previstas

```text
DJANGO_SECRET_KEY
DJANGO_ALLOWED_HOSTS
DJANGO_CSRF_TRUSTED_ORIGINS
DJANGO_SECURE_SSL_REDIRECT
DJANGO_SECURE_HSTS_SECONDS
DATABASE_URL
APP_BASE_URL
APP_TIME_ZONE=America/Sao_Paulo
LOG_LEVEL=INFO
WORKER_POLL_SECONDS
JOB_LOCK_SECONDS
TEMP_DATA_DIR
CNPJ_SOURCE_BASE_URL
CNPJ_MAX_TEMP_BYTES
CNPJ_MIN_FREE_BYTES
CNPJ_DOWNLOAD_TIMEOUT_SECONDS
CNPJ_PREVIEW_MAX_RESULTS
CNPJ_MAX_PERSISTED_MATCHES
CNPJ_TEMP_MAX_AGE_SECONDS
CRAWLER_USER_AGENT
CRAWLER_CONTACT
CRAWLER_TIMEOUT_SECONDS
CRAWLER_MAX_BYTES
CRAWLER_MAX_TEXT_CHARS
CRAWLER_MAX_REDIRECTS
CRAWLER_MAX_PAGES
MAPS_BASE_URL
MAPS_CONCURRENCY
```

`WORKER_ID` é opcional. Quando ausente, cada container usa seu hostname, evitando que
réplicas diferentes compartilhem a mesma identidade de lock. Durante cada execução, o
worker renova `heartbeat_at` e `lock_expires_at` a cada terço de `JOB_LOCK_SECONDS`; use um
lock maior que o pior atraso esperado do banco. Um worker que perdeu o lock não pode gravar
sucesso nem falha sobre a tentativa assumida por outra réplica.

O arquivo `.env.example` documentará nomes e valores seguros de exemplo. Secrets reais existem somente no Coolify/ambiente.

## Volumes

- PostgreSQL: persistente e com backup;
- temporários CNPJ: volume com quota/limite e política de limpeza;
- Maps/Playwright: cache opcional do browser;
- arquivos estáticos: conforme estratégia do proxy/Coolify.

Downloads CNPJ não são backup nem dado permanente. Um job interrompido deve poder retomar ou limpar somente seu diretório isolado.

O downloader mantém no máximo uma parte, usa extensão `.part`, exige `Content-Length`,
verifica quota e espaço livre antes de gravar, valida o ZIP e promove o arquivo
atomicamente. O lock global impede dois downloads CNPJ simultâneos. O arquivo pronto é
apagado em `finally`; `cleanup_cnpj_temp` remove somente `.zip`/`.zip.part` antigos em
diretórios isolados e preserva qualquer conteúdo desconhecido.

## Healthchecks

`/health/live`: processo responde, sem dependências externas.

`/health/ready`: valida conexão ao PostgreSQL e migrations compatíveis. Não chama fontes externas a cada request.

O worker atualiza heartbeat no banco. A UI considera degradado quando nenhum worker saudável estiver disponível.

Adapters têm healthchecks assíncronos separados, com cache, para não bloquear o deploy.

## Release

```text
git push
  → Coolify build
  → testes/checagens de build
  → migration release command
  → iniciar web e worker
  → readiness
```

Migrations destrutivas ou longas seguirão expansão/contração. Nunca depender da inicialização concorrente de vários containers para aplicar a mesma operação perigosa.

## Backup e recuperação

- backup diário do PostgreSQL;
- retenção definida no Coolify/armazenamento;
- teste de restauração periódico;
- exportar também versão das regras e configurações;
- não depender dos payloads temporários para reconstruir Explain Score já publicado.

Antes do primeiro uso real, executar restauração em ambiente isolado e documentar RPO/RTO aceitos.

## Segurança

- HTTPS obrigatório;
- cookies `Secure`, `HttpOnly` e `SameSite` apropriados;
- CSRF do Django;
- senha forte para admin e rotação inicial;
- painel administrativo não indexável;
- containers de coleta sem acesso desnecessário à rede interna;
- PostgreSQL não exposto à internet;
- limites de upload mesmo que upload não faça parte do MVP;
- headers de segurança e Content Security Policy progressiva;
- proteção SSRF descrita na arquitetura;
- logs sem senhas, tokens, cookies ou payloads pessoais integrais.

## Capacidade inicial

O uso persistente esperado do Sniper é proporcional às empresas efetivamente encontradas, não ao cadastro nacional.

Processamento CNPJ exige espaço temporário por arquivo/parte. O worker verificará espaço livre e quota antes de baixar. Se não houver margem configurada, o job falha de forma segura antes do download.

CPU/RAM do Maps serão medidos com uma única página/browser e baixa concorrência antes de qualquer aumento.

O crawler processa páginas sequencialmente e limita cada execução por
`CRAWLER_MAX_PAGES` (padrão 5). Como cada resposta e o texto extraído também possuem teto,
uma coleta não cresce proporcionalmente ao tamanho total do website.
Dados JSON-LD usam um teto adicional de 200 mil caracteres por página. Apenas até 100
objetos estruturados e 100 vagas são considerados; o HTML bruto continua sendo descartado.
`JOB_POSTING_MAX_AGE_DAYS` define a idade máxima de uma vaga ativa (padrão 365). Uma
`validThrough` anterior também a desativa; a próxima detecção desativa seus sinais e agenda
o scoring pelo fluxo normal do job de coleta/detecção.

O JobsAdapter começa desligado. Para testes controlados com fixtures locais, configure
`JOBS_ADAPTER_ENABLED=true`, habilite a fonte `jobs-fixture` no admin e coloque o JSON
diretamente em `JOBS_FIXTURE_ROOT`. Subdiretórios e traversal são rejeitados. Os tetos são:

- `JOBS_MAX_PAGES` (padrão 2);
- `JOBS_MAX_RESULTS` (padrão 100);
- `JOBS_MAX_RESPONSE_BYTES` (padrão 1 MB).

Somente o adapter local está permitido no handler `FIND_JOBS`; apontar outro `source_key`
falha de forma segura. O worker aplica sua política normal de tentativas/backoff às falhas.

Usuários staff podem acompanhar fila, fontes e capacidade em `/operations/jobs/`. A
capacidade CNPJ segura exibida é o menor valor entre a quota temporária e o espaço livre após
a reserva mínima. O painel não cria o diretório temporário, não calcula tamanho recursivo e
não oferece ações de retry, cancelamento, limpeza ou habilitação de fonte.

A exportação do ranking não grava arquivos no servidor e possui teto fixo de 500 empresas.
Filtros inválidos retornam HTTP 400; nenhuma exportação inicia adapter, job ou download.

## Observação sobre Git

O repositório oficial é `synapseindustring-png/SNIPER-Synapse`. Tokens continuam somente
no ambiente local/Coolify; `.env` e o diretório `env/` nunca entram no Git nem no contexto
de build do Docker.
