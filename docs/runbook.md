# Runbook de produção

## Objetivo e responsabilidades

Este runbook cobre deploy, observabilidade, backup, restauração e incidentes do Synapse
Sniper. O operador executa o diagnóstico e registra horários/evidências; o dono do produto
autoriza rollback, restauração e alterações em fontes pagas ou coletas amplas.

Metas propostas para o primeiro uso real, ainda sujeitas à aprovação do proprietário:

- RPO: até 24 horas, correspondente ao backup diário;
- RTO: até 2 horas após disponibilizar infraestrutura e backup íntegro;
- retenção: 14 backups diários e 3 mensais em armazenamento externo criptografado.

## Checklist antes do primeiro tráfego

- domínio, HTTPS, `DJANGO_ALLOWED_HOSTS` e `DJANGO_CSRF_TRUSTED_ORIGINS` conferidos;
- `DJANGO_SECRET_KEY` exclusivo e credenciais armazenadas somente no Coolify;
- PostgreSQL sem porta pública e volume persistente identificado;
- web, worker e migration usando a mesma imagem/commit;
- `/health/live` e `/health/ready` respondendo 200;
- backup automático diário configurado fora do mesmo host/volume do banco;
- restauração testada e horário, duração, checksum e resultado registrados;
- `CNPJ_FULL_ENABLED=false` até autorização operacional explícita.

## Deploy normal

1. Confirmar suíte verde e worktree publicado no GitHub.
2. Criar backup antes de migrations que alterem schema ou dados.
3. Fazer o Coolify construir uma única imagem para web, worker e migration.
4. Executar `python manage.py migrate --noinput` uma única vez.
5. Iniciar web e worker com a mesma imagem.
6. Conferir readiness, logs de boot e heartbeat do worker em `/operations/jobs/`.
7. Fazer smoke test autenticado em dashboard, Indústrias, Parceiros e Regras.

Não publicar duas versões de aplicação que esperem schemas incompatíveis. Mudanças grandes
de schema devem usar expansão/contração em releases separados.

## Backup local verificável

Os scripts abaixo são destinados ao Compose local ou a uma instalação autogerenciada com
o serviço `db`. O backup do Coolify deve continuar sendo o mecanismo primário em produção.

```bash
./scripts/backup-postgres.sh
```

O comando cria `backups/sniper-<UTC>.dump` no formato custom do PostgreSQL e seu `.sha256`.
O arquivo parcial é removido em caso de falha. O catálogo é validado antes da promoção e
arquivos com o padrão do Sniper mais antigos que `BACKUP_RETENTION_DAYS` (padrão 14) são
apagados. O diretório e os arquivos usam permissões restritas e não entram no Git/Docker.

Para escolher outro destino e retenção:

```bash
BACKUP_DIR=/mnt/backup-sniper BACKUP_RETENTION_DAYS=30 ./scripts/backup-postgres.sh
```

O destino real deve ser criptografado, monitorado e replicado para outro host/região. Um
backup existente somente no mesmo disco do PostgreSQL não atende recuperação de desastre.

## Teste de restauração

```bash
./scripts/restore-check-postgres.sh backups/sniper-<UTC>.dump
```

O script verifica checksum e catálogo, checa margem de disco, cria um banco temporário com
nome gerado, restaura com `--exit-on-error`, valida migrations e quatro tabelas essenciais,
e remove somente esse banco temporário. Ele nunca aponta `pg_restore` para o banco `sniper`.

Registre a cada teste: commit, nome/checksum do backup, início/fim, tamanho, resultado e
operador. Execute mensalmente e depois de mudanças relevantes de PostgreSQL ou estratégia
de backup. Monitore o espaço: a checagem exige aproximadamente duas vezes o tamanho lógico
do banco, mais 100 MB, para não pressionar o volume em uso.

## Restauração real

1. Declarar incidente e interromper web/worker para congelar novas escritas.
2. Preservar o banco/volume com problema para análise; não sobrescrevê-lo.
3. Validar checksum e executar o teste de restauração do artefato escolhido.
4. Provisionar um novo PostgreSQL vazio e compatível, preferencialmente isolado.
5. Restaurar com `pg_restore --exit-on-error --no-owner --no-privileges`.
6. Executar `python manage.py migrate --check` usando a imagem do commit correspondente.
7. Conferir contagens de empresas, fontes, jobs, snapshots e usuário administrador.
8. Apontar primeiro uma instância web isolada, fazer smoke test e só então trocar tráfego.
9. Reiniciar um worker, conferir heartbeat/fila e aumentar réplicas gradualmente.
10. Registrar perda de dados estimada (RPO), duração (RTO), causa e ações corretivas.

Nunca restaure diretamente sobre o banco de produção existente.

## Diagnóstico de incidentes

### Readiness 503

- manter a instância fora do balanceador;
- verificar conectividade e espaço do PostgreSQL;
- comparar `showmigrations` com o commit implantado;
- conferir falha da etapa única de migration;
- não reiniciar em loop se o banco estiver sem espaço.

### Worker sem heartbeat

- conferir container, logs e locks na tela de Jobs;
- validar conexão ao banco e `JOB_LOCK_SECONDS`;
- reiniciar apenas o worker afetado;
- não iniciar muitos workers para compensar uma fonte bloqueada.

### Disco próximo do limite

- desabilitar `CNPJ_FULL_ENABLED` e não iniciar novas consultas completas;
- conferir painel de capacidade e temporários identificados do CNPJ;
- executar `cleanup_cnpj_temp` somente para temporários abandonados reconhecidos;
- não apagar o volume PostgreSQL, backups sem cópia externa ou arquivos desconhecidos.

### Fonte externa falhando

- preservar o erro sanitizado e o histórico de tentativas;
- manter backoff/kill switch e reduzir concorrência;
- não contornar rate limit nem trocar credenciais em logs/comandos compartilhados;
- resultados locais e telas continuam disponíveis sem nova coleta.

## Rollback

Se o schema continuar compatível, reimplantar a imagem anterior e repetir health/smoke
tests. Se houve migration incompatível, não executar downgrade destrutivo automaticamente:
seguir expansão/contração ou restaurar em um novo banco após aprovação. Jobs iniciados pela
versão defeituosa devem ser identificados e auditados antes de retry/cancelamento.
