#!/bin/sh
set -eu

mkdir -p /data/assets
if [ ! -f /data/drafts.db ] && [ -f /legacy/drafts.db ]; then
  cp /legacy/drafts.db /data/drafts.db
  echo "已将旧版 drafts.db 迁移到 Docker 数据目录"
fi

exec python /app/server.py
