#!/usr/bin/env bash
# =============================================================================
# UXI-Lite Server - Quick Update Script
# Jalankan di Server: ./update_server.sh
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "========================================"
echo "  UXI-Lite Server - Quick Update"
echo "========================================"

SUDO=""
if [ "${EUID}" -ne 0 ]; then
  SUDO="sudo"
fi

echo "[1/2] Updating files..."
# Dashboard will be auto-reloaded by Grafana

echo "[2/2] Restarting Grafana to reload dashboard..."
$SUDO docker compose -f "$ROOT_DIR/server/docker/docker-compose.yml" restart grafana

echo ""
echo "========================================"
echo "  ✅ Update Complete!"
echo "========================================"
echo ""
echo "Grafana: http://localhost:3000"
echo ""
