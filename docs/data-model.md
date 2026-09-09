# Modelo de dados

## Princípios

- UUID como chave pública das entidades do Sniper;
- CNPJ armazenado normalizado, preservando compatibilidade futura com formato alfanumérico;
- dados canônicos separados das observações de fonte;
- eventos e snapshots imutáveis quando necessários para auditoria;
- `JSONB` somente para payloads externos e condições variáveis, não para substituir colunas centrais;
- datas em UTC;
- exclusão lógica para entidades comerciais relevantes.

## Relações principais

```text
DiscoveryQuery 1 ── N QueryRun 1 ── N Job
                         │
                         └── N QueryResult N ── 1 Company

Source 1 ── N SourceRecord N ── 1 Company
                         └── N FieldObservation

Company 1 ── N CompanyCnae
        1 ── N WebsitePage
        1 ── N JobPosting
        1 ── N Signal
        1 ── N ScoreSnapshot 1 ── N ScoreContribution
        1 ── N StatusHistory
        1 ── N ManualOverride
```

## Descoberta

### `discovery_query`

Definição reutilizável criada pelo usuário.

Campos principais: `id`, `name`, `entity_target`, `filters_json`, `normalized_filters_json`, `fingerprint`, `active`, `created_by`, `created_at`, `updated_at`.

O fingerprint é calculado sobre filtros normalizados e versão do schema da consulta.

### `query_run`

Execução de uma consulta.

Campos: `id`, `query_id`, `status`, `dataset_reference`, `started_at`, `finished_at`, contadores, `coverage_json`, `created_by`.

Status: `PENDING`, `RUNNING`, `SUCCEEDED`, `PARTIAL`, `FAILED`, `CANCELLED`.

### `query_result`

Liga uma execução a uma empresa.

Campos: `query_run_id`, `company_id`, `source_id`, `rank`, `matched_filters_json`, `is_new_company`, `created_at`.

Restrição única: `(query_run_id, company_id)`.

### `source_coverage`

Registra quais filtros/competências já estão materializados localmente. Permite decidir se o cache atende uma nova consulta.

Campos: `source`, `dataset_reference`, `scope_json`, `scope_hash`, `record_count`, `completed_at`, `expires_at`.

## Empresa canônica

### `company`

Campos centrais:

- `id` UUID;
- `cnpj` varchar com unique parcial quando preenchido;
- `legal_name`, `trade_name`;
- `company_type`;
- `registration_status`;
- `size_code`, `legal_nature_code`, `share_capital`;
- `opened_on`;
- `segment`;
- endereço estruturado, município, código IBGE, UF e CEP;
- latitude/longitude;
- telefone, e-mail, website e `website_domain`;
- LinkedIn e Google Maps URL;
- estimativa de funcionários e fonte da estimativa;
- `commercial_status`;
- `created_at`, `updated_at`, `last_enriched_at`, `deleted_at`.

`company_type`:

```text
INDUSTRY
CONSULTANCY
INTEGRATOR
ENGINEERING
SERVICE_PROVIDER
OTHER
```

Índices: CNPJ, domínio, tipo, UF+município, status cadastral, status comercial, segmento e busca textual em nomes.

### `company_cnae`

Campos: `company_id`, `code`, `description`, `is_primary`, `source_record_id`, `observed_at`.

Único por `(company_id, code)`; no máximo um CNAE principal atual por empresa.

### `company_specialty`

Especialidades de parceiros, com código configurável, evidência e estado atual.

### `company_note`

Nota manual: autor, conteúdo, criação e atualização. Não participa do score sem regra explícita.

## Fontes e proveniência

### `source`

Catálogo: `key`, `name`, `adapter_path`, `enabled`, `capabilities_json`, política de rate limit e timestamps.

Secrets ficam no ambiente, nunca nesta tabela.

### `cnpj_dataset` e `cnpj_dataset_file`

O manifesto de cada competência CNPJ é persistido antes de qualquer execução. O dataset
registra fonte, referência, estado, descoberta/verificação e qual competência é atual.
Cada arquivo registra tipo, parte, URL, tamanho declarado, ETag e checksum quando houver.

Apenas um dataset atual pode existir por fonte. A interface usa o tamanho do menor arquivo
de estabelecimentos para calcular a prévia e bloqueia o job se a quota ou a reserva mínima
de disco não forem atendidas.

### `source_record`

Observação imutável recebida de uma fonte.

Campos: `id`, `source_id`, `external_id`, `company_id`, `query_run_id`, `source_url`, `payload_json`, `payload_hash`, `dataset_reference`, `observed_at`, `collected_at`.

Único por `(source_id, external_id, payload_hash)` quando existir identificador externo.

### `field_observation`

Proveniência por campo: `company_id`, `source_record_id`, `field_name`, `value_json`, `normalized_value`, `confidence`, `observed_at`, `is_current`, `selected_at`.

Uma rotina determinística de precedência escolhe o valor canônico. A escolha não apaga observações anteriores.

## Conteúdo enriquecido

### `website_page`

Campos implementados: empresa, source record, URL canônica, tipo inferido, título, texto
extraído, hash, status HTTP, content type, datas de observação/coleta/última visualização e
estado atual.

O texto possui limite configurável. HTML bruto é descartado após a extração e versões
inalteradas são deduplicadas por empresa, URL e hash.

### `job_posting`

Campos implementados: empresa, source record, fingerprint, ID externo, cargo, descrição
normalizada, local, regime, URL, datas de publicação/validade, primeira/última observação,
estado ativo e metadados.

O fingerprint por empresa prioriza URL canônica, depois ID externo e, como fallback,
cargo+local+data. A recoleta atualiza a observação sem duplicar e desativa vagas que
desapareceram da mesma página-fonte, excederam a idade máxima ou passaram de `valid_through`.
Cada sinal originado de vaga guarda seu ID/fingerprint nos metadados e usa `published_on`
como data observada, permitindo decay e rastreabilidade por vaga.

### `job_posting_review`

Fila implementada para candidatos de fontes de vagas que não possuem correspondência forte
com a empresa consultada. Guarda fonte, fingerprint, identidade declarada, cargo, local,
URL sanitizada, motivo, empresa sugerida, estado da revisão e datas. O payload integral e a
descrição da vaga não são replicados nessa fila.

## Sinais

### `signal`

Campos implementados: `company_id`, `signal_type`, `product`, `source_record_id`,
`source_url`, `title`, `evidence_excerpt`, `evidence_hash`, `observed_at`, `detected_at`,
`expires_at`, `base_weight`, `active`, metadados e timestamps.

Único por `(company_id, signal_type, evidence_hash)`. Um catálogo separado de tipos poderá
ser introduzido quando o detector automático exigir políticas próprias por tipo.

### `signal_detection`

Registra a execução de uma regra que originou ou confirmou um sinal: regra/versionamento,
registro-fonte, campo correspondido, termos, trecho curto de evidência e data.

### `signal_rule`

Regra explícita e versionada do detector: tipo de sinal, produto, termos, modo `ANY`/`ALL`,
campos permitidos do payload, peso-base, expiração, decay e estado ativo. Apenas uma versão
ativa por chave é permitida.

## Regras e scoring

### `rule_set`

Agrupa uma configuração publicável. Estados: `DRAFT`, `PUBLISHED`, `RETIRED`. Fórmula,
thresholds e ordem de desempate fazem parte da versão. Apenas uma versão pode estar ativa
por escopo.

### `scoring_rule`

Campos: rule set, nome, entidade, dimensão, produto, tipo de sinal, condição JSON, peso, teto por regra/grupo, criticidade, decay policy, vigência, ordem e ativo.

Dimensões de indústria: `ICP`, `MES`, `CMMS`, `PULSE`, `INTENT`.

Dimensões de parceiro: `PARTNER_FIT`, `CHANNEL_POTENTIAL`, `PARTNER_ACTIVITY`, `CONFLICT`.

Fórmula, thresholds e ordem de desempate são JSON versionado dentro do RuleSet. Cada regra
guarda sua política de decay (`NONE` ou `AGE_BUCKETS`) e a curva correspondente.

### `score_snapshot`

Resultado imutável de um cálculo: empresa, rule set, scores individuais, melhor produto, prioridade calculada, temperatura calculada, data e motivo do recálculo.

### `score_contribution`

Explicação atômica: snapshot, dimensão, regra, sinal/observação, pontos-base, multiplicador, pontos efetivos, texto explicativo e fonte.

O score exibido deve ser reconstruível pela soma das contribuições e fórmula do snapshot.

## Comercial e auditoria

### `manual_override`

Campos: empresa, campo afetado, valor calculado anterior, valor manual, motivo, autor, início, fim e estado ativo.

### `status_history`

Empresa, tipo de status, valor anterior/novo, origem (`SYSTEM` ou `MANUAL`), usuário, motivo e data.

### `audit_event`

Evento append-only para mudanças administrativas: ator, ação, objeto, antes/depois sanitizado, IP/request ID e timestamp.

## Jobs

### `job`

Campos: UUID, tipo, status, payload JSON, idempotency key, prioridade, tentativa/limite, `run_after`, lock owner/expiry, heartbeat, timestamps, contadores e resumo do erro.

Índices em `(status, run_after, priority)`, `idempotency_key`, tipo e data.

### `job_attempt`

Histórico por tentativa: worker, início/fim, resultado, erro técnico sanitizado e métricas.

## Retenção inicial

- Company, sinais, snapshots, contribuições e auditoria: persistentes;
- payloads de fonte: persistentes enquanto sustentarem evidência, com política posterior de arquivamento;
- HTML bruto e downloads CNPJ: temporários;
- texto extraído: persistente com limite e hash;
- logs técnicos: retenção configurável no ambiente.
