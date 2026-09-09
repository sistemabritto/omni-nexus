#!/bin/bash
# ============================================================
# vps-backup.sh — Backup Completo VPS → Cloudflare R2
# ============================================================

set -Eeuo pipefail
umask 077
exec 9>/run/lock/vps-backup.lock
flock -n 9 || { echo 'Backup already running; skipping overlap'; exit 0; }
renice 15 -p $$ >/dev/null
ionice -c3 -p $$

BACKUP_BASE="/opt/backups"
R2_BUCKET="r2:swissnode-backups"
RETENTION_DAYS=3
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$BACKUP_BASE/$TIMESTAMP"
LOG_FILE="/var/log/vps-backup.log"
[ ! -f /etc/vps-backup-notify.env ] || source /etc/vps-backup-notify.env
TOTAL_UPLOADED_BYTES=0
WARNINGS=0


log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

notify() {
    [ "${BACKUP_NOTIFY:-1}" = 1 ] && [ -n "${EVO_TOKEN:-}" ] || return 0
    local title="$1"
    local message="$2"
    local emoji="$3"
    local full_msg="${emoji} *${title}*\n\n${message}\n\n📅 $(date '+%d/%m/%Y %H:%M') UTC"
    curl --max-time 15 -s -X POST "${EVO_API_URL}/send/text" \
        -H "apikey: ${EVO_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"instanceId\":\"${EVO_INSTANCE}\",\"number\":\"${ADMIN_NUMBER}\",\"text\":\"${full_msg}\"}" \
        > /dev/null 2>&1 || true
}

error_exit() {
    log "ERRO FATAL: $1"
    notify "BACKUP FALHOU — swissnode" "Erro: $1" "🚨"
    exit 1
}

cleanup() {
    # The only recursive target is this invocation's validated staging folder.
    if [[ "$BACKUP_DIR" =~ ^/opt/backups/[0-9]{8}_[0-9]{6}$ ]] && [ -d "$BACKUP_DIR" ]; then
        rm -rf -- "$BACKUP_DIR"
    fi
}
trap cleanup EXIT
trap 'error_exit "line $LINENO failed"' ERR

upload_artifact() {
    local file="$1" rel bytes remote_bytes
    rel="${file#"$BACKUP_DIR/"}"
    bytes=$(stat -c %s "$file")
    rclone copyto "$file" "$R2_BUCKET/$TIMESTAMP/$rel" \
        --transfers=1 --checkers=2 --retries=3 --bwlimit=12M \
        --log-level=ERROR
    remote_bytes=$(rclone lsjson --stat "$R2_BUCKET/$TIMESTAMP/$rel" |
        python3 -c 'import json,sys; print(json.load(sys.stdin)["Size"])')
    [ "$bytes" = "$remote_bytes" ] || error_exit "Remote size mismatch: $rel"
    TOTAL_UPLOADED_BYTES=$((TOTAL_UPLOADED_BYTES + bytes))
    rm -f -- "$file"
    log "  Verified and uploaded: $rel ($bytes bytes); staging released"
}

archive_directory() {
    local source="$1" output="$2" member="${3:-.}" rc=0
    # Never archive backups of backups or reproducible dependency caches.
    tar czf "$output" --exclude='./backups' --exclude='*/backups' \
        --exclude='./.cache' --exclude='*/.cache' --exclude='*/node_modules' \
        --exclude='*/__pycache__' --exclude='*/.npm' --exclude='*/.venv' \
        --exclude='*/request_dump*' -C "$source" "$member" || rc=$?
    if [ "$rc" -gt 1 ]; then error_exit "Archive failed: $source"; fi
    if [ "$rc" -eq 1 ]; then
        WARNINGS=$((WARNINGS + 1))
        log "  WARN: files changed during archive: $source"
    fi
    upload_artifact "$output"
}

[ "$(df -PB1 /opt | awk 'NR==2 {print $4}')" -gt 10737418240 ] || error_exit 'Less than 10 GiB free; refusing backup staging'

log "=========================================="
log "BACKUP INICIADO — $TIMESTAMP"
log "=========================================="

mkdir -p "$BACKUP_DIR/volumes" \
         "$BACKUP_DIR/docker-volumes-gfs" \
         "$BACKUP_DIR/stacks" \
         "$BACKUP_DIR/databases" \
         "$BACKUP_DIR/system"

if [ "${VPS_BACKUP_SMOKE:-0}" = 1 ]; then
    # Exercise the real uploader and restoration checksum in a separate prefix.
    R2_BUCKET="$R2_BUCKET/checks"
    cp /etc/hostname /etc/hosts "$BACKUP_DIR/system/"
    tar czf "$BACKUP_DIR/volumes/smoke.tar.gz" -C "$BACKUP_DIR/system" .
    expected=$(sha256sum "$BACKUP_DIR/volumes/smoke.tar.gz" | cut -d' ' -f1)
    upload_artifact "$BACKUP_DIR/volumes/smoke.tar.gz"
    actual=$(rclone cat "$R2_BUCKET/$TIMESTAMP/volumes/smoke.tar.gz" | sha256sum | cut -d' ' -f1)
    [ "$expected" = "$actual" ] || error_exit 'Smoke restore checksum mismatch'
    log "SMOKE PASS: upload, remote size, restore checksum, staging cleanup"
    exit 0
fi

notify "BACKUP INICIADO — swissnode" "Backup diário começou.\nTimestamp: ${TIMESTAMP}" "🔄"

log "--- [1/6] Exportando stacks do Swarm..."
docker stack ls --format '{{.Name}}' | while read -r stack; do
    log "  Stack: $stack"
    docker stack services "$stack" --format '{{json .}}' \
        > "$BACKUP_DIR/stacks/${stack}_services.json" 2>/dev/null || true
done
docker service ls --format '{{json .}}' > "$BACKUP_DIR/stacks/all_services.json" 2>/dev/null || true
mapfile -t service_ids < <(docker service ls -q)
if [ "${#service_ids[@]}" -gt 0 ]; then
    docker service inspect "${service_ids[@]}" > "$BACKUP_DIR/stacks/service_specs.json"
fi
docker config ls --format '{{.Name}}' | while read -r cfg; do
    docker config inspect "$cfg" > "$BACKUP_DIR/stacks/config_${cfg}.json" 2>/dev/null || true
done
log "  Stacks OK"

log "--- Consistent SQLite snapshots for OmniRoute and Hermes..."
sqlite_source=/var/lib/docker/volumes/evonexus_omniroute_data/_data/storage.sqlite
if [ -f "$sqlite_source" ]; then
    python3 /usr/local/lib/vps-sqlite-snapshot.py "$sqlite_source" "$BACKUP_DIR/databases/omniroute-storage.sqlite"
    upload_artifact "$BACKUP_DIR/databases/omniroute-storage.sqlite"
fi
for profile_dir in /mnt/docker-volumes/hermes-unified /mnt/docker-volumes/hermes-unified/profiles/*; do
    [ -f "$profile_dir/config.yaml" ] || continue
    profile_name="${profile_dir##*/}"
    for dbname in state.db response_store.db kanban.db projects.db; do
        [ -f "$profile_dir/$dbname" ] || continue
        target="$BACKUP_DIR/databases/hermes-${profile_name}-${dbname}"
        python3 /usr/local/lib/vps-sqlite-snapshot.py "$profile_dir/$dbname" "$target"
        upload_artifact "$target"
    done
done

log "--- [2/6] Backup volumes Docker..."
while read -r vol; do
    [[ "$vol" == *"_tmp"* ]] && continue
    [[ "$vol" == *_backups ]] && { log "  Skipping backup-only volume: $vol"; continue; }
    vol_safe=$(echo "$vol" | tr '/' '_')
    log "  Volume: $vol"
    mountpoint=$(docker volume inspect "$vol" --format '{{.Mountpoint}}')
    archive_directory "$mountpoint" "$BACKUP_DIR/volumes/${vol_safe}.tar.gz"
done < <(docker volume ls --format '{{.Name}}')
log "  Volumes Docker OK"

log "--- [3/6] Backup GlusterFS /mnt/docker-volumes..."
for dir in /mnt/docker-volumes/*/; do
    name=$(basename "$dir")
    [ "$name" = "hermes-profiles-restructured" ] && continue
    log "  Comprimindo: $name"
    archive_directory /mnt/docker-volumes "$BACKUP_DIR/docker-volumes-gfs/${name}.tar.gz" "$name"
done
log "  GlusterFS OK"

# These active persistent binds are outside /mnt and were missed by the old job.
archive_directory /opt "$BACKUP_DIR/docker-volumes-gfs/opt-plausible.tar.gz" plausible
if [ -f /opt/evo-nexus/patches/api_controller.rb ]; then
    cp /opt/evo-nexus/patches/api_controller.rb "$BACKUP_DIR/system/"
fi

log "--- [4/6] Logical database dumps for all PostgreSQL and MySQL containers..."
while read -r cid image cname; do
    service="${cname%%.*}"
    case "$image" in
        postgres:*|pgvector/*)
            docker exec "$cid" sh -c 'export PGPASSWORD="${POSTGRES_PASSWORD:-}"; exec pg_dumpall -U "${POSTGRES_USER:-postgres}"' |
                gzip -1 > "$BACKUP_DIR/databases/${service}.sql.gz"
            upload_artifact "$BACKUP_DIR/databases/${service}.sql.gz"
            ;;
        mysql:*)
            docker exec "$cid" sh -c 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; exec mysqldump -uroot --single-transaction --quick --all-databases --routines --events' |
                gzip -1 > "$BACKUP_DIR/databases/${service}.sql.gz"
            upload_artifact "$BACKUP_DIR/databases/${service}.sql.gz"
            ;;
    esac
done < <(docker ps --format '{{.ID}} {{.Image}} {{.Names}}')

log "--- [5/6] Configs do sistema..."
for path in /etc/sysctl.conf /etc/hosts /etc/hostname /etc/docker/daemon.json; do
    [ -f "$path" ] && cp "$path" "$BACKUP_DIR/system/" 2>/dev/null || true
done
docker info > "$BACKUP_DIR/system/docker_info.txt" 2>/dev/null || true
docker node ls > "$BACKUP_DIR/system/swarm_nodes.txt" 2>/dev/null || true
docker network ls > "$BACKUP_DIR/system/networks.txt" 2>/dev/null || true
crontab -l > "$BACKUP_DIR/system/crontab_root.txt" 2>/dev/null || true
log "  Configs OK"

log "--- [6/6] Upload para Cloudflare R2..."
BACKUP_SIZE="$(numfmt --to=iec "$TOTAL_UPLOADED_BYTES")"
log "  Tamanho local: $BACKUP_SIZE"

rclone copy "$BACKUP_DIR" "${R2_BUCKET}/${TIMESTAMP}/" \
    --transfers=1 \
    --checkers=2 \
    --bwlimit=12M \
    --retries=3 \
    --log-level=INFO \
    --log-file="$LOG_FILE" || error_exit "rclone upload falhou"

log "  Upload R2 OK"
printf '{"complete":true,"timestamp":"%s","archive_bytes":%s,"warnings":%s}\n' \
    "$TIMESTAMP" "$TOTAL_UPLOADED_BYTES" "$WARNINGS" | \
    rclone rcat "$R2_BUCKET/$TIMESTAMP/COMPLETE.json"
cleanup
log "  Temporario local removido"

log "--- Limpando backups antigos no R2..."
CUTOFF=$(date -d "${RETENTION_DAYS} days ago" +%Y%m%d)
rclone lsd "${R2_BUCKET}/" 2>/dev/null | awk '{print $NF}' | while read -r folder; do
    folder_date=$(echo "$folder" | cut -c1-8)
    if [[ "$folder" =~ ^[0-9]{8}_[0-9]{6}$ ]] && [ "$folder_date" -lt "$CUTOFF" ]; then
        log "  Removendo antigo: $folder"
        rclone purge "${R2_BUCKET}/${folder}/" 2>/dev/null || true
    fi
done

R2_TOTAL=$(rclone size "${R2_BUCKET}/" --json 2>/dev/null | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(f\"{d['bytes']//1024//1024}MB\")" 2>/dev/null || echo "N/A")

log "=========================================="
log "BACKUP CONCLUIDO COM SUCESSO"
log "  Timestamp : $TIMESTAMP"
log "  Tamanho   : $BACKUP_SIZE"
log "  R2 Total  : $R2_TOTAL"
log "=========================================="

notify "BACKUP CONCLUIDO — swissnode" \
    "Backup diário finalizado!\n\n📦 Tamanho: *${BACKUP_SIZE}*\n☁️ R2 total: *${R2_TOTAL}*\n🗓️ Retenção: ${RETENTION_DAYS} dias" \
    "✅"

exit 0
