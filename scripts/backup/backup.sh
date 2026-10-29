#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="${BACKUP_DIR:-$ROOT/backups}/$STAMP"
mkdir -p "$OUT"
echo "==> Postgres dump"
docker compose -f "$ROOT/docker-compose.yml" exec -T postgres \
  pg_dump -U earlywarn -d earlywarn --format=custom > "$OUT/earlywarn.dump"
echo "==> Redis BGSAVE"
docker compose -f "$ROOT/docker-compose.yml" exec -T redis redis-cli BGSAVE || true
sleep 2
RID=$(docker compose -f "$ROOT/docker-compose.yml" ps -q redis)
if [ -n "$RID" ]; then
  docker cp "$RID:/data/dump.rdb" "$OUT/dump.rdb" 2>/dev/null || true
fi
cp -a "$ROOT/config/cells.json" "$OUT/cells.json"
echo "==> Done: $OUT"
ls -lh "$OUT"
