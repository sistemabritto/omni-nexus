#!/usr/bin/env bash
set -Eeuo pipefail
exec 9>/run/lock/sb-backup-retention.lock
flock -n 9 || exit 0
exec ionice -c3 nice -n 15 python3 /usr/local/lib/vps-backup-retention.py --apply
