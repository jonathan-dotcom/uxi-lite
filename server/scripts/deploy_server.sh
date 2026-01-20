#!/usr/bin/env bash
# =============================================================================
# UXI-Lite Server - Deploy from PC/Laptop to Server
# 
# Usage:
#   Fresh install:      ./deploy_server.sh user@192.168.1.50
#   Update dashboard:   ./deploy_server.sh user@192.168.1.50 --update
#   Update Prometheus:  ./deploy_server.sh user@192.168.1.50 --update-config
# =============================================================================
set -euo pipefail

SERVER_HOST=""
UPDATE_ONLY=0
UPDATE_CONFIG=0
PROM_CONFIG_PATH=""
HOST_FOR_CURL=""
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REMOTE_DEST="/opt/uxi-lite-server"
REMOTE_STAGE="/tmp/uxi-lite-server"

while [ $# -gt 0 ]; do
  case "$1" in
    --update)
      UPDATE_ONLY=1
      shift
      ;;
    --update-config)
      UPDATE_CONFIG=1
      shift
      ;;
    --config)
      PROM_CONFIG_PATH="${2:-}"
      shift 2
      ;;
    *)
      if [ -z "$SERVER_HOST" ]; then
        SERVER_HOST="$1"
        shift
      else
        echo "Unknown argument: $1"
        exit 1
      fi
      ;;
  esac
done

if [ -z "$SERVER_HOST" ]; then
  echo "Usage: $0 <user@server_ip> [--update] [--update-config] [--config path]"
  echo ""
  echo "Examples:"
  echo "  Fresh install:    $0 user@192.168.1.50"
  echo "  Update dashboard: $0 user@192.168.1.50 --update"
  echo "  Update config:    $0 user@192.168.1.50 --update-config"
  exit 1
fi
HOST_FOR_CURL="${SERVER_HOST##*@}"

remote_sudo() {
  local cmd="$*"
  if [ -n "${SUDO_PASS:-}" ]; then
    ssh -t "$SERVER_HOST" "printf '%s\n' \"$SUDO_PASS\" | sudo -S $cmd"
  else
    ssh -t "$SERVER_HOST" "sudo $cmd"
  fi
}

echo "========================================"
echo "  UXI-Lite Server - Remote Deploy"
echo "========================================"
echo "Target: $SERVER_HOST"
echo ""

# Quick update mode - only update dashboard
if [ "$UPDATE_ONLY" -eq 1 ]; then
  echo "[UPDATE MODE] Only updating dashboard..."
  
  echo "[1/2] Copying dashboard to server..."
  scp "$ROOT_DIR/server/docker/grafana/dashboards/uxi-lite-dashboard.json" \
      "$SERVER_HOST:/tmp/uxi-lite-dashboard.json"
  remote_sudo "cp /tmp/uxi-lite-dashboard.json $REMOTE_DEST/server/docker/grafana/dashboards/"
  
  echo "[2/2] Restarting Grafana..."
  remote_sudo "docker compose -f $REMOTE_DEST/server/docker/docker-compose.yml restart grafana"
  
  echo ""
  echo "========================================"
  echo "  ✅ Dashboard Update Complete!"
  echo "========================================"
  echo "Grafana: http://$HOST_FOR_CURL:3000"
  exit 0
fi

if [ "$UPDATE_CONFIG" -eq 1 ]; then
  echo "[UPDATE MODE] Updating Prometheus config..."

  config_path="${PROM_CONFIG_PATH:-$ROOT_DIR/server/docker/prometheus.yml}"
  if [ ! -f "$config_path" ]; then
    echo "Config not found: $config_path"
    exit 1
  fi

  echo "[1/2] Copying prometheus.yml..."
  scp "$config_path" "$SERVER_HOST:/tmp/uxi-prometheus.yml"
  remote_sudo "cp /tmp/uxi-prometheus.yml $REMOTE_DEST/server/docker/prometheus.yml"

  echo "[2/2] Restarting Prometheus..."
  remote_sudo "docker compose -f $REMOTE_DEST/server/docker/docker-compose.yml restart prometheus"

  echo ""
  echo "========================================"
  echo "  ✅ Prometheus Config Update Complete!"
  echo "========================================"
  echo "Prometheus: http://$HOST_FOR_CURL:9090"
  exit 0
fi

# Full install mode
echo "[1/6] Preparing staging directory..."
ssh "$SERVER_HOST" "rm -rf $REMOTE_STAGE && mkdir -p $REMOTE_STAGE"

echo "[2/6] Copying files to server..."
scp -r "$ROOT_DIR/server" "$SERVER_HOST:$REMOTE_STAGE/"

echo "[3/6] Installing files..."
remote_sudo "mkdir -p $REMOTE_DEST"
remote_sudo "rm -rf $REMOTE_DEST/server"
remote_sudo "cp -r $REMOTE_STAGE/server $REMOTE_DEST/"

echo "[4/6] Checking Docker installation..."
ssh -t "$SERVER_HOST" "command -v docker >/dev/null 2>&1 || (curl -fsSL https://get.docker.com | sudo sh)"
remote_sudo "docker compose version >/dev/null 2>&1 || (apt update && apt install -y docker-compose-plugin)"

echo "[5/6] Starting containers..."
remote_sudo "docker compose -f $REMOTE_DEST/server/docker/docker-compose.yml up -d"

echo "[6/6] Waiting for services..."
sleep 5

echo ""
echo "========================================"
echo "  ✅ Deployment Complete!"
echo "========================================"
echo ""
echo "Services:"
echo "  Prometheus: http://$HOST_FOR_CURL:9090"
echo "  Grafana:    http://$HOST_FOR_CURL:3000 (admin/admin)"
echo ""
echo "⚠️  IMPORTANT: Update Prometheus targets/services."
echo "    Run:  $ROOT_DIR/scripts/configure_project.sh"
echo "    Or edit markers in: $REMOTE_DEST/server/docker/prometheus.yml"
echo ""
