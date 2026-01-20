#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG="$ROOT_DIR/sensor/config/config.yaml"
LOG_PATH="${UXI_LOG_PATH:-$ROOT_DIR/sensor/logs/results.jsonl}"

if [ "${EUID}" -ne 0 ]; then
  sudo -E python3 "$ROOT_DIR/sensor/core/uxi_core_exporter.py" --config "$CONFIG" --log-path "$LOG_PATH"
else
  python3 "$ROOT_DIR/sensor/core/uxi_core_exporter.py" --config "$CONFIG" --log-path "$LOG_PATH"
fi
