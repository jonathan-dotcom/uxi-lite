#!/usr/bin/env bash
# =============================================================================
# UXI-Lite Server - Fresh Install Script
# Jalankan di Server: ./install_server.sh
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "========================================"
echo "  UXI-Lite Server - Fresh Install"
echo "========================================"

SUDO=""
if [ "${EUID}" -ne 0 ]; then
  SUDO="sudo"
fi

echo "[1/3] Checking Docker installation..."
if ! command -v docker >/dev/null 2>&1; then
  echo "Installing Docker..."
  curl -fsSL https://get.docker.com | $SUDO sh
fi

if ! $SUDO docker compose version >/dev/null 2>&1; then
  echo "Installing docker-compose-plugin..."
  $SUDO apt update
  $SUDO apt install -y docker-compose-plugin
fi

echo "[2/3] Starting containers..."
$SUDO docker compose -f "$ROOT_DIR/server/docker/docker-compose.yml" up -d

echo "[3/3] Waiting for services to start..."
sleep 5

echo ""
echo "========================================"
echo "  ✅ Installation Complete!"
echo "========================================"
echo ""
echo "Services:"
echo "  Prometheus: http://localhost:9090"
echo "  Grafana:    http://localhost:3000 (admin/admin)"
echo ""
echo "Dashboard: UXI-Lite (auto-provisioned)"
echo ""
echo "Next steps:"
echo "  1. Update prometheus.yml with sensor IP:port"
echo "     Run: $ROOT_DIR/scripts/configure_project.sh"
echo "     Or manually edit: $ROOT_DIR/server/docker/prometheus.yml"
echo ""
echo "  2. Restart Prometheus after config changes:"
echo "     docker compose -f $ROOT_DIR/server/docker/docker-compose.yml restart prometheus"
echo ""
