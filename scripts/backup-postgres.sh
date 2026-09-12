#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
backup_dir=${BACKUP_DIR:-"$project_dir/backups"}
database_name=${POSTGRES_DB:-sniper}
database_user=${POSTGRES_USER:-sniper}
retention_days=${BACKUP_RETENTION_DAYS:-14}

case "$backup_dir" in
    ""|/|.) echo "Diretório de backup inseguro: $backup_dir" >&2; exit 2 ;;
esac
case "$retention_days" in
    *[!0-9]*|"") echo "BACKUP_RETENTION_DAYS deve ser um inteiro não negativo." >&2; exit 2 ;;
esac

mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
backup_dir=$(CDPATH= cd -- "$backup_dir" && pwd)
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
final_path="$backup_dir/sniper-$timestamp.dump"
partial_path="$final_path.partial"
checksum_path="$final_path.sha256"
umask 077

cleanup_partial() {
    rm -f -- "$partial_path"
}
trap cleanup_partial EXIT HUP INT TERM

cd "$project_dir"
docker compose exec -T db pg_dump \
    --username "$database_user" \
    --dbname "$database_name" \
    --format custom \
    --compress 6 \
    --no-owner \
    --no-privileges > "$partial_path"

test -s "$partial_path"
docker compose exec -T db pg_restore --list < "$partial_path" > /dev/null
mv -- "$partial_path" "$final_path"
(cd "$backup_dir" && sha256sum "$(basename -- "$final_path")" > "$(basename -- "$checksum_path")")
trap - EXIT HUP INT TERM

find "$backup_dir" -maxdepth 1 -type f \
    \( -name 'sniper-*.dump' -o -name 'sniper-*.dump.sha256' \) \
    -mtime "+$retention_days" -delete

printf '%s\n' "$final_path"
