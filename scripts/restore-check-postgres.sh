#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "Uso: $0 /caminho/para/sniper-AAAA.dump" >&2
    exit 2
fi

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
backup_path=$(CDPATH= cd -- "$(dirname -- "$1")" && pwd)/$(basename -- "$1")
database_name=${POSTGRES_DB:-sniper}
database_user=${POSTGRES_USER:-sniper}
restore_database="sniper_restore_check_$(date -u +%Y%m%d%H%M%S)_$$"

test -f "$backup_path"
test -s "$backup_path"
case "$restore_database" in
    *[!a-z0-9_]*) echo "Nome de banco temporário inválido." >&2; exit 2 ;;
esac

checksum_path="$backup_path.sha256"
if [ -f "$checksum_path" ]; then
    (cd "$(dirname -- "$backup_path")" && sha256sum --check "$(basename -- "$checksum_path")")
fi

cd "$project_dir"
docker compose exec -T db pg_restore --list < "$backup_path" > /dev/null

source_bytes=$(docker compose exec -T db psql \
    --username "$database_user" --dbname "$database_name" --tuples-only --no-align \
    --command "SELECT pg_database_size(current_database());")
free_kilobytes=$(docker compose exec -T db df -Pk /var/lib/postgresql/data | awk 'NR == 2 {print $4}')
required_kilobytes=$((source_bytes / 1024 * 2 + 102400))
if [ "$free_kilobytes" -lt "$required_kilobytes" ]; then
    echo "Espaço insuficiente para restauração isolada." >&2
    exit 1
fi

cleanup_database() {
    docker compose exec -T db dropdb \
        --username "$database_user" --if-exists "$restore_database" > /dev/null
}
trap cleanup_database EXIT HUP INT TERM

docker compose exec -T db createdb --username "$database_user" "$restore_database"
docker compose exec -T db pg_restore \
    --username "$database_user" \
    --dbname "$restore_database" \
    --exit-on-error \
    --no-owner \
    --no-privileges < "$backup_path"

migration_count=$(docker compose exec -T db psql \
    --username "$database_user" --dbname "$restore_database" --tuples-only --no-align \
    --command "SELECT count(*) FROM django_migrations;")
essential_tables=$(docker compose exec -T db psql \
    --username "$database_user" --dbname "$restore_database" --tuples-only --no-align \
    --command "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('companies_company','sources_sourcerecord','scoring_scoresnapshot','jobs_job');")

if [ "$migration_count" -le 0 ] || [ "$essential_tables" -ne 4 ]; then
    echo "Restauração incompleta: migrations=$migration_count, tabelas essenciais=$essential_tables." >&2
    exit 1
fi

cleanup_database
trap - EXIT HUP INT TERM
printf 'restore-check=ok migrations=%s essential_tables=%s\n' "$migration_count" "$essential_tables"
