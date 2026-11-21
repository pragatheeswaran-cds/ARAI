#!/bin/bash
# Nightly: the database and the artifact root to the bucket (section 2.9: PostgreSQL lives on the VM, so the dump is
# the recovery path). Called from /etc/cron.d/arai-backup with BUCKET and APP_DIR set. Restore: RUNBOOK 8.6.
set -euo pipefail
cd "$APP_DIR"
COMPOSE="docker compose -f docker-compose.yml -f deploy/aws/compose.vm.yml"
stamp=$(date -u +%Y%m%d-%H%M)
mkdir -p /data/backup
for db in arai; do
  $COMPOSE exec -T db pg_dump -U arai --no-owner "$db" | gzip -6 > "/data/backup/${db}-${stamp}.sql.gz"
  aws s3 cp "/data/backup/${db}-${stamp}.sql.gz" "s3://${BUCKET}/backup/db/${db}-${stamp}.sql.gz" --only-show-errors
done
find /data/backup -name '*.sql.gz' -mtime +7 -delete
# datasets, bundles, runs and the published experiment; never the private truth (it is not on this VM)
aws s3 sync /data/artifacts "s3://${BUCKET}/backup/artifacts/" --only-show-errors
echo "$(date -Is) backup ${stamp} done"
