#!/usr/bin/env bash
# =============================================================================
# UXI-Lite Sensor - Deploy from PC/Laptop to Raspberry Pi
# 
# Usage:
#   Fresh install:  ./deploy_from_server.sh pi@192.168.1.100
#   Quick update:   ./deploy_from_server.sh pi@192.168.1.100 --update
#   Custom config:  ./deploy_from_server.sh pi@192.168.1.100 --config sensor/config/sensors/sensor-a.yaml
#   Force default:  ALLOW_DEFAULT_CONFIG=1 ./deploy_from_server.sh pi@192.168.1.100 --update
# =============================================================================
set -euo pipefail

SENSOR_HOST=""
UPDATE_ONLY=0
CONFIG_PATH=""
HOST_FOR_CURL=""
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEST="/opt/uxi-lite-sensor"
REMOTE_STAGE="/tmp/uxi-lite-sensor"
CONFIG_DIR="$ROOT_DIR/sensor/config/sensors"
ALLOW_DEFAULT_CONFIG="${ALLOW_DEFAULT_CONFIG:-0}"

while [ $# -gt 0 ]; do
  case "$1" in
    --update)
      UPDATE_ONLY=1
      shift
      ;;
    --config)
      CONFIG_PATH="${2:-}"
      shift 2
      ;;
    *)
      if [ -z "$SENSOR_HOST" ]; then
        SENSOR_HOST="$1"
        shift
      else
        echo "Unknown argument: $1"
        exit 1
      fi
      ;;
  esac
done

if [ -z "$SENSOR_HOST" ]; then
  echo "Usage: $0 <user@sensor_ip> [--update] [--config path]"
  echo ""
  echo "Examples:"
  echo "  Fresh install:  $0 pi@192.168.1.100"
  echo "  Quick update:   $0 pi@192.168.1.100 --update"
  echo "  Custom config:  $0 pi@192.168.1.100 --config sensor/config/sensors/sensor-a.yaml"
  exit 1
fi
HOST_FOR_CURL="${SENSOR_HOST##*@}"

sanitize_sensor_name() {
  printf "%s" "$1" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//; s/^\"//; s/\"$//'
}

fetch_remote_sensor_name() {
  ssh "$SENSOR_HOST" "if [ -f /opt/uxi-lite-sensor/config/config.yaml ]; then grep -m1 '^sensor_name:' /opt/uxi-lite-sensor/config/config.yaml; fi" \
    2>/dev/null | sed -E 's/^sensor_name:[[:space:]]*//'
}

match_config_by_sensor_name() {
  local name="$1"
  python3 - "$name" "$CONFIG_DIR" <<'PY'
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit(1)

sensor_name = sys.argv[1].strip()
configs_dir = Path(sys.argv[2])
matches = []
for path in configs_dir.glob("*.yaml"):
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        continue
    if str(data.get("sensor_name", "")).strip() == sensor_name:
        matches.append(str(path))
if len(matches) == 1:
    print(matches[0])
PY
}

resolve_config_path() {
  if [ -n "$CONFIG_PATH" ] || [ ! -d "$CONFIG_DIR" ]; then
    return 0
  fi

  mapfile -t configs < <(find "$CONFIG_DIR" -maxdepth 1 -type f -name '*.yaml' | sort)
  if [ "${#configs[@]}" -eq 0 ]; then
    return 0
  fi

  if [ "${#configs[@]}" -eq 1 ]; then
    CONFIG_PATH="${configs[0]}"
    echo "Auto-selected config: $CONFIG_PATH"
    return 0
  fi

  remote_name="$(sanitize_sensor_name "$(fetch_remote_sensor_name)")"
  if [ -n "$remote_name" ]; then
    matched="$(match_config_by_sensor_name "$remote_name" || true)"
    if [ -n "$matched" ]; then
      CONFIG_PATH="$matched"
      echo "Auto-selected config for sensor '$remote_name': $CONFIG_PATH"
      return 0
    fi
  fi

  if [ "$ALLOW_DEFAULT_CONFIG" != "0" ]; then
    return 0
  fi

  echo "Multiple sensor configs found in $CONFIG_DIR."
  echo "Use --config <path> (or set ALLOW_DEFAULT_CONFIG=1 to force config.yaml)."
  exit 1
}

resolve_config_path

if [ -n "$CONFIG_PATH" ] && [ ! -f "$CONFIG_PATH" ]; then
  echo "Config not found: $CONFIG_PATH"
  exit 1
fi

remote_sudo() {
  local cmd="$*"
  if [ -n "${SUDO_PASS:-}" ]; then
    ssh -tt "$SENSOR_HOST" "printf '%s\n' \"$SUDO_PASS\" | sudo -S $cmd"
  else
    ssh -tt "$SENSOR_HOST" "sudo $cmd"
  fi
}

echo "========================================"
echo "  UXI-Lite Sensor - Remote Deploy"
echo "========================================"
echo "Target: $SENSOR_HOST"
echo ""

# Quick update mode
if [ "$UPDATE_ONLY" -eq 1 ]; then
  echo "[UPDATE MODE] Only updating code files..."
  
  echo "[1/3] Copying files to sensor..."
  ssh "$SENSOR_HOST" "rm -rf $REMOTE_STAGE && mkdir -p $REMOTE_STAGE"
  scp -r "$ROOT_DIR/sensor/core" "$ROOT_DIR/sensor/scripts" "$SENSOR_HOST:$REMOTE_STAGE/"
  if [ -n "$CONFIG_PATH" ]; then
    scp "$CONFIG_PATH" "$SENSOR_HOST:$REMOTE_STAGE/config.yaml"
  else
    scp -r "$ROOT_DIR/sensor/config" "$SENSOR_HOST:$REMOTE_STAGE/"
  fi
  
  echo "[2/3] Installing files..."
  remote_sudo "systemctl stop uxi-core.service || true"
  remote_sudo "cp -r $REMOTE_STAGE/core/* $DEST/core/"
  remote_sudo "cp -r $REMOTE_STAGE/scripts/* $DEST/scripts/"
  if [ -n "$CONFIG_PATH" ]; then
    remote_sudo "install -m 644 $REMOTE_STAGE/config.yaml $DEST/config/config.yaml"
  else
    remote_sudo "cp -r $REMOTE_STAGE/config/* $DEST/config/"
  fi
  
  echo "[3/3] Restarting service..."
  remote_sudo "systemctl start uxi-core.service"
  
  echo ""
  echo "========================================"
  echo "  ✅ Update Complete!"
  echo "========================================"
  echo "Metrics: curl http://$HOST_FOR_CURL:9105/metrics"
  exit 0
fi

# Full install mode
echo "[1/7] Preparing staging directory..."
ssh "$SENSOR_HOST" "rm -rf $REMOTE_STAGE && mkdir -p $REMOTE_STAGE"

echo "[2/7] Copying files to sensor..."
scp -r \
  "$ROOT_DIR/sensor/core" \
  "$ROOT_DIR/sensor/config" \
  "$ROOT_DIR/sensor/systemd" \
  "$ROOT_DIR/sensor/scripts" \
  "$SENSOR_HOST:$REMOTE_STAGE/"
if [ -n "$CONFIG_PATH" ]; then
  scp "$CONFIG_PATH" "$SENSOR_HOST:$REMOTE_STAGE/config.yaml"
fi

echo "[3/7] Installing files..."
remote_sudo "mkdir -p $DEST && rm -rf $DEST/core $DEST/config $DEST/systemd $DEST/scripts"
remote_sudo "cp -r $REMOTE_STAGE/core $REMOTE_STAGE/config $REMOTE_STAGE/systemd $REMOTE_STAGE/scripts $DEST/"
remote_sudo "mkdir -p $DEST/logs $DEST/state"
if [ -n "$CONFIG_PATH" ]; then
  remote_sudo "install -m 644 $REMOTE_STAGE/config.yaml $DEST/config/config.yaml"
fi

echo "[4/7] Installing system dependencies..."
remote_sudo "apt update"
remote_sudo "apt install -y network-manager iw dnsutils iproute2 iputils-ping curl traceroute python3-venv"

echo "[5/7] Creating Python virtual environment..."
remote_sudo "python3 -m venv $DEST/.venv"
remote_sudo "$DEST/.venv/bin/pip install --upgrade pip"

echo "[6/7] Installing Python dependencies..."
remote_sudo "$DEST/.venv/bin/pip install -r $DEST/core/requirements.txt"

echo "[7/7] Setting up and starting service..."
remote_sudo "cp $DEST/systemd/uxi-core.service /etc/systemd/system/uxi-core.service"
remote_sudo "systemctl daemon-reload"
remote_sudo "systemctl enable uxi-core.service"
remote_sudo "systemctl restart uxi-core.service"

echo ""
echo "========================================"
echo "  ✅ Deployment Complete!"
echo "========================================"
echo ""
echo "Metrics:"
echo "  curl http://$HOST_FOR_CURL:9105/metrics"
echo ""
echo "SSH to sensor: ssh $SENSOR_HOST"
echo "Check status:  ssh $SENSOR_HOST 'sudo systemctl status uxi-core'"
echo "View logs:     ssh $SENSOR_HOST 'journalctl -u uxi-core -f'"
echo ""
