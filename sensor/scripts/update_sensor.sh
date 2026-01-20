#!/usr/bin/env bash
# =============================================================================
# UXI-Lite Sensor - Quick Update Script
# Jalankan di Raspberry Pi: ./update_sensor.sh
# Hanya update code, tidak reinstall dependencies
# Opsi: ./update_sensor.sh --config /path/to/sensor.yaml
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
echo "  UXI-Lite Sensor - Quick Update"
echo "========================================"

SUDO=""
if [ "${EUID}" -ne 0 ]; then
  SUDO="sudo"
fi

# Check if already installed
if [ ! -d "$DEST/core" ]; then
  echo "❌ Error: UXI-Lite not installed. Run install_sensor.sh first."
  exit 1
fi

sanitize_sensor_name() {
  printf "%s" "$1" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//; s/^\"//; s/\"$//'
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

  active_name="$(sanitize_sensor_name "$(grep -m1 '^sensor_name:' "$DEST/config/config.yaml" | sed -E 's/^sensor_name:[[:space:]]*//')")"
  if [ -n "$active_name" ]; then
    matched="$(match_config_by_sensor_name "$active_name" || true)"
    if [ -n "$matched" ]; then
      CONFIG_PATH="$matched"
      echo "Auto-selected config for sensor '$active_name': $CONFIG_PATH"
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

echo "[1/3] Stopping service..."
$SUDO systemctl stop uxi-core.service || true

echo "[2/3] Updating files..."
$SUDO cp -r "$ROOT_DIR/sensor/core/"* "$DEST/core/"
$SUDO cp -r "$ROOT_DIR/sensor/config/"* "$DEST/config/"
$SUDO cp -r "$ROOT_DIR/sensor/scripts/"* "$DEST/scripts/"
if [ -n "$CONFIG_PATH" ]; then
  $SUDO install -m 644 "$CONFIG_PATH" "$DEST/config/config.yaml"
fi

echo "[3/3] Restarting service..."
$SUDO systemctl start uxi-core.service

echo ""
echo "========================================"
echo "  ✅ Update Complete!"
echo "========================================"
echo ""
echo "Check status: sudo systemctl status uxi-core"
echo "View logs:    journalctl -u uxi-core -f"
echo ""
