#!/usr/bin/env bash
# =============================================================================
# UXI-Lite - Master Setup Script
# 
# Script ini membantu setup UXI-Lite sensor dan server
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETUP_CONFIG_FILE="$ROOT_DIR/.setup_config"

# Load saved config if exists
LAST_SENSOR_HOST=""
LAST_SERVER_HOST=""
if [ -f "$SETUP_CONFIG_FILE" ]; then
  source "$SETUP_CONFIG_FILE"
fi

save_config() {
  cat > "$SETUP_CONFIG_FILE" << EOF
LAST_SENSOR_HOST="$LAST_SENSOR_HOST"
LAST_SERVER_HOST="$LAST_SERVER_HOST"
EOF
}

show_menu() {
  clear 2>/dev/null || true
  echo "========================================"
  echo "  UXI-Lite Setup Menu"
  echo "========================================"
  echo ""
  echo "SENSOR (Raspberry Pi):"
  echo "  1) Deploy sensor ke Raspberry Pi (dari PC ini)"
  echo "  2) Update sensor (code only, dari PC ini)"
  echo ""
  echo "SERVER (Prometheus + Grafana):"
  echo "  3) Deploy server ke remote machine (dari PC ini)"
  echo "  4) Update dashboard (local/remote)"
  echo "  5) Install server di mesin ini (local)"
  echo ""
  echo "CONFIG:"
  echo "  6) Edit konfigurasi sensor (config.yaml)"
  echo "  7) Edit konfigurasi prometheus (prometheus.yml)"
  echo "  8) Configure project (multi-sensor)"
  echo "  9) Configure project (basic template)"
  echo "  0) Exit"
  echo ""
  if [ -n "$LAST_SENSOR_HOST" ] || [ -n "$LAST_SERVER_HOST" ]; then
    echo "Saved addresses:"
    [ -n "$LAST_SENSOR_HOST" ] && echo "  Sensor: $LAST_SENSOR_HOST"
    [ -n "$LAST_SERVER_HOST" ] && echo "  Server: $LAST_SERVER_HOST"
    echo ""
  fi
}

ask_sensor_host() {
  local default_hint=""
  local input_host=""
  if [ -n "$LAST_SENSOR_HOST" ]; then
    default_hint=" [Enter=$LAST_SENSOR_HOST]"
  fi
  read -p "SSH address Raspberry Pi (contoh: dti@100.123.214.125)$default_hint: " input_host
  
  if [ -z "$input_host" ] && [ -n "$LAST_SENSOR_HOST" ]; then
    echo "$LAST_SENSOR_HOST"
  elif [ -z "$input_host" ]; then
    echo ""
  else
    LAST_SENSOR_HOST="$input_host"
    save_config
    echo "$input_host"
  fi
}

ask_server_host() {
  local default_hint=""
  local input_host=""
  if [ -n "$LAST_SERVER_HOST" ]; then
    default_hint=" [Enter=$LAST_SERVER_HOST]"
  fi
  read -p "SSH address Server (contoh: user@192.168.1.50)$default_hint: " input_host
  
  if [ -z "$input_host" ] && [ -n "$LAST_SERVER_HOST" ]; then
    echo "$LAST_SERVER_HOST"
  elif [ -z "$input_host" ]; then
    echo ""
  else
    LAST_SERVER_HOST="$input_host"
    save_config
    echo "$input_host"
  fi
}

choose_sensor_config() {
  local config_dir="$ROOT_DIR/sensor/config/sensors"
  local -a configs=()
  local choice=""

  if [ -d "$config_dir" ]; then
    mapfile -t configs < <(find "$config_dir" -maxdepth 1 -type f -name '*.yaml' | sort)
  fi

  if [ "${#configs[@]}" -eq 0 ]; then
    return 0
  fi

  if [ "${#configs[@]}" -eq 1 ]; then
    printf "%s" "${configs[0]}"
    return 0
  fi

  echo "Multiple sensor configs found:" >&2
  for idx in "${!configs[@]}"; do
    echo "  $((idx + 1))) ${configs[$idx]}" >&2
  done
  read -p "Choose config [1-${#configs[@]}] or Enter to skip: " choice
  if [ -z "$choice" ]; then
    return 0
  fi
  if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "${#configs[@]}" ]; then
    printf "%s" "${configs[$((choice - 1))]}"
    return 0
  fi
}

deploy_sensor() {
  echo ""
  SENSOR_HOST=$(ask_sensor_host)
  if [ -z "$SENSOR_HOST" ]; then
    echo "❌ Address tidak boleh kosong!"
    return
  fi
  echo ""
  read -p "Fresh install atau update only? (1=fresh, 2=update): " INSTALL_TYPE
  
  local config_path
  local -a config_args
  config_path="$(choose_sensor_config)"
  config_args=()
  if [ -n "$config_path" ]; then
    config_args=(--config "$config_path")
  fi

  if [ "$INSTALL_TYPE" = "2" ]; then
    bash "$ROOT_DIR/sensor/scripts/deploy_from_server.sh" "$SENSOR_HOST" --update "${config_args[@]}"
  else
    bash "$ROOT_DIR/sensor/scripts/deploy_from_server.sh" "$SENSOR_HOST" "${config_args[@]}"
  fi
}

deploy_server() {
  echo ""
  SERVER_HOST=$(ask_server_host)
  if [ -z "$SERVER_HOST" ]; then
    echo "❌ Address tidak boleh kosong!"
    return
  fi
  echo ""
  read -p "Fresh install atau update dashboard only? (1=fresh, 2=update): " INSTALL_TYPE
  
  if [ "$INSTALL_TYPE" = "2" ]; then
    bash "$ROOT_DIR/server/scripts/deploy_server.sh" "$SERVER_HOST" --update
  else
    bash "$ROOT_DIR/server/scripts/deploy_server.sh" "$SERVER_HOST"
  fi
}

install_server_local() {
  echo ""
  echo "Installing server on this machine..."
  bash "$ROOT_DIR/server/scripts/install_server.sh"
}

edit_sensor_config() {
  local cfg="$ROOT_DIR/sensor/config/config.yaml"
  if command -v nano >/dev/null 2>&1; then
    nano "$cfg"
  elif command -v vim >/dev/null 2>&1; then
    vim "$cfg"
  else
    echo "File: $cfg"
    echo "Gunakan text editor untuk mengedit file ini."
  fi
}

edit_prometheus_config() {
  local cfg="$ROOT_DIR/server/docker/prometheus.yml"
  if command -v nano >/dev/null 2>&1; then
    nano "$cfg"
  elif command -v vim >/dev/null 2>&1; then
    vim "$cfg"
  else
    echo "File: $cfg"
    echo "Gunakan text editor untuk mengedit file ini."
  fi
}

# Main loop
while true; do
  show_menu
  read -p "Pilih opsi [0-9]: " choice
  
  case $choice in
    1) deploy_sensor ;;
    2) 
      echo ""
      SENSOR_HOST=$(ask_sensor_host)
      if [ -z "$SENSOR_HOST" ]; then
        echo "❌ Address tidak boleh kosong!"
      else
        config_path="$(choose_sensor_config)"
        if [ -n "$config_path" ]; then
          bash "$ROOT_DIR/sensor/scripts/deploy_from_server.sh" "$SENSOR_HOST" --update --config "$config_path"
        else
          bash "$ROOT_DIR/sensor/scripts/deploy_from_server.sh" "$SENSOR_HOST" --update
        fi
      fi
      ;;
    3) deploy_server ;;
    4)
      echo ""
      echo "Update dashboard:"
      echo "  1) Local machine"
      echo "  2) Remote server (SSH)"
      read -p "Pilih opsi [1-2]: " update_choice
      if [ "$update_choice" = "1" ]; then
        bash "$ROOT_DIR/server/scripts/update_server.sh"
      elif [ "$update_choice" = "2" ]; then
        SERVER_HOST=$(ask_server_host)
        if [ -z "$SERVER_HOST" ]; then
          echo "❌ Address tidak boleh kosong!"
        else
          bash "$ROOT_DIR/server/scripts/deploy_server.sh" "$SERVER_HOST" --update
        fi
      else
        echo "❌ Opsi tidak valid"
      fi
      ;;
    5) install_server_local ;;
    6) edit_sensor_config ;;
    7) edit_prometheus_config ;;
    8) bash "$ROOT_DIR/scripts/configure_project.sh" ;;
    9) bash "$ROOT_DIR/scripts/configure_project.sh" --basic ;;
    0) echo "Bye!"; exit 0 ;;
    *) echo "❌ Opsi tidak valid" ;;
  esac
  
  echo ""
  read -p "Tekan Enter untuk melanjutkan..."
done
