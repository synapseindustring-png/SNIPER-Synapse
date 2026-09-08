# Synapse Sniper

Radar comercial industrial B2B para descobrir, enriquecer e priorizar indústrias e parceiros no Brasil com regras determinísticas e evidências auditáveis.

## Estado atual

A fundação Django/Docker, autenticação, healthchecks e fila persistida de jobs estão
operacionais. O pipeline CNPJ possui descoberta do manifesto oficial, leitor seletivo que
percorre o CSV diretamente dentro do ZIP e filtros aplicados antes da persistência.

A primeira fatia de domínio também está disponível: empresas, CNAEs, fontes, registros
imutáveis, observações por campo, consultas, execuções, resultados e cobertura. O job
`DISCOVER_CNPJ` já integra uma fixture/ZIP local a essas entidades com deduplicação por CNPJ.

Downloads CNPJ operam com quota e reserva de disco, um arquivo por vez, validação integral
e exclusão após uso. O modo padrão é `PREVIEW`, limitado e explicitamente marcado como
parcial; `FULL` também possui teto de persistência.

A interface de Consultas permite cadastrar filtros por UF, município e CNAE, visualizar a
estimativa de download/espaço e solicitar uma prévia somente quando existe manifesto atual
validado e capacidade de disco suficiente.

A interface de Indústrias lista somente a base curada local, com busca, filtros e paginação
de 50 registros. Abrir essa lista ou o detalhe de uma empresa não executa coleta nem baixa
arquivos. O detalhe expõe CNAEs, registros-fonte e observações por campo, e o dashboard usa
contagens reais do banco.

O motor de scoring determinístico já possui conjuntos de regras versionados, fórmulas,
thresholds, decay, snapshots imutáveis, contribuições explicáveis e overrides. O detalhe da
empresa permite solicitar o cálculo ao worker e exibe o score sem acessar fontes externas.
Os pesos seed estão identificados como hipóteses até a validação comercial.

O detector de sinais percorre somente registros-fonte já armazenados, aplica regras de
palavras-chave com limites de palavra, preserva o trecho de evidência e agenda o recálculo
do score. Onze regras seed cobrem temas iniciais como PCM, manutenção, OEE, MES, produção,
telemetria, automação, expansão, contratação, ERP e uso de planilhas.

Decisões centrais:

- descoberta iniciada por consultas, sem upload manual de listas;
- base curada no PostgreSQL, sem réplica persistente de todo o CNPJ brasileiro;
- scores separados para estrutura, produto e intenção;
- Explain Score obrigatório;
- Django server-rendered, PostgreSQL, Docker e Coolify;
- adapters substituíveis para todas as fontes;
- nenhuma decisão comercial por LLM ou machine learning.

## Fluxo alvo

```text
consulta → coleta → normalização → deduplicação → enriquecimento
        → sinais → scoring → ranking → evidências
```

## Documentação

- [Especificação consolidada](./ESPECIFICACAO-SYNAPSE-SNIPER-MVP.md)
- [Arquitetura](./docs/architecture.md)
- [Modelo de dados](./docs/data-model.md)
- [Motor de scoring](./docs/scoring-engine.md)
- [Fontes e repositórios avaliados](./docs/sources.md)
- [Prova de processamento seletivo do CNPJ](./docs/cnpj-selective-spike.md)
- [Deploy e operação](./docs/deployment.md)
- [Plano de implementação](./docs/implementation-plan.md)

O prompt original permanece em `Prompt — Synapse Sniper MVP.md` como registro de origem. A especificação consolidada incorpora as decisões posteriores e prevalece em caso de ambiguidade.

## Desenvolvimento

Suba a stack local:

```bash
cp .env.example .env
docker compose up --build
```

Se a porta `8000` já estiver em uso, ajuste `WEB_PORT` no `.env` antes de subir a stack.
Para habilitar a fonte CNPJ, configure no `.env` a URL WebDAV pública atual e seu token
de compartilhamento em `CNPJ_SOURCE_BASE_URL` e `CNPJ_WEBDAV_TOKEN`. A aplicação permanece
bloqueada quando qualquer um deles estiver ausente.

Execute os testes sem depender de fontes externas:

```bash
docker compose run --rm --no-deps -e DATABASE_URL= web python manage.py test
```

Crie o primeiro administrador com a stack ativa:

```bash
docker compose exec web python manage.py createsuperuser
```

Remova temporários CNPJ abandonados por uma interrupção abrupta:

```bash
docker compose run --rm worker python manage.py cleanup_cnpj_temp
```

Não existem credenciais de Git ou Coolify necessárias para o desenvolvimento local.

## Licenciamento

A licença do Synapse Sniper ainda será definida pelo proprietário. Componentes externos não serão copiados ou incorporados antes do inventário de licença por versão. Consulte `docs/sources.md`.
