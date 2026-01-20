#!/usr/bin/env bash
# =============================================================================
# UXI-Lite Sensor - Fresh Install Script
# Jalankan di Raspberry Pi: ./install_sensor.sh
# Opsi: ./install_sensor.sh --config /path/to/sensor.yaml
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEST="/opt/uxi-lite-sensor"
CONFIG_PATH=""
CONFIG_DIR="$ROOT_DIR/sensor/config/sensors"
ALLOW_DEFAULT_CONFIG="${ALLOW_DEFAULT_CONFIG:-0}"

while [ $# -gt 0 ]; do
  case "$1" in
    --config)
      CONFIG_PATH="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1"
      exit 1
      ;;
  esac
done

if [ -n "$CONFIG_PATH" ] && [ ! -f "$CONFIG_PATH" ]; then
  echo "Config not found: $CONFIG_PATH"
  exit 1
fi

echo "========================================"
echo "  UXI-Lite Sensor - Fresh Install"
echo "========================================"

SUDO=""
if [ "${EUID}" -ne 0 ]; then
  SUDO="sudo"
fi

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

  if [ "$ALLOW_DEFAULT_CONFIG" != "0" ]; then
    return 0
  fi

  echo "Multiple sensor configs found in $CONFIG_DIR."
  echo "Use --config <path> (or set ALLOW_DEFAULT_CONFIG=1 to force config.yaml)."
  exit 1
}

resolve_config_path

echo "[1/6] Creating directories..."
$SUDO mkdir -p "$DEST"
$SUDO rm -rf "$DEST/core" "$DEST/config" "$DEST/systemd" "$DEST/scripts"
$SUDO cp -r "$ROOT_DIR/sensor/core" "$ROOT_DIR/sensor/config" "$ROOT_DIR/sensor/systemd" "$ROOT_DIR/sensor/scripts" "$DEST/"
$SUDO mkdir -p "$DEST/logs" "$DEST/state"
if [ -n "$CONFIG_PATH" ]; then
  $SUDO install -m 644 "$CONFIG_PATH" "$DEST/config/config.yaml"
fi

echo "[2/6] Installing system dependencies..."
$SUDO apt update
$SUDO apt install -y network-manager iw dnsutils iproute2 iputils-ping curl traceroute python3-venv

echo "[3/6] Creating Python virtual environment..."
$SUDO python3 -m venv "$DEST/.venv"
$SUDO "$DEST/.venv/bin/pip" install --upgrade pip

echo "[4/6] Installing Python dependencies..."
$SUDO "$DEST/.venv/bin/pip" install -r "$DEST/core/requirements.txt"

echo "[5/6] Setting up systemd service..."
$SUDO cp "$DEST/systemd/uxi-core.service" /etc/systemd/system/uxi-core.service
$SUDO systemctl daemon-reload
$SUDO systemctl enable uxi-core.service

echo "[6/6] Starting UXI-Lite service..."
$SUDO systemctl start uxi-core.service

echo ""
echo "========================================"
echo "  ✅ Installation Complete!"
echo "========================================"
echo ""
echo "Useful commands:"
echo "  Status:   sudo systemctl status uxi-core"
echo "  Logs:     journalctl -u uxi-core -f"
echo "  Metrics:  curl http://localhost:9105/metrics"
echo ""
echo "Config file: $DEST/config/config.yaml"
echo "Edit this file to configure your Wi-Fi networks and services!"
echo ""
