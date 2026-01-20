#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

SUDO=""
if [ "${EUID}" -ne 0 ]; then
  SUDO="sudo"
fi

$SUDO docker compose -f "$ROOT_DIR/server/docker/docker-compose.yml" up -d
