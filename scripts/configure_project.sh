#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SENSORS_DIR="$ROOT_DIR/sensor/config/sensors"
PROM_FILE="$ROOT_DIR/server/docker/prometheus.yml"
CONFIG_TEMPLATE="$ROOT_DIR/sensor/config/template.yaml"
BASIC_MODE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --basic)
      BASIC_MODE=1
      shift
      ;;
    --template)
      CONFIG_TEMPLATE="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1"
      exit 1
      ;;
  esac
done

if [ "$BASIC_MODE" -eq 1 ] && [ ! -f "$CONFIG_TEMPLATE" ]; then
  echo "Template config not found: $CONFIG_TEMPLATE"
  exit 1
fi

prompt_default() {
  local prompt="$1"
  local default="$2"
  local value=""
  read -r -p "$prompt [$default]: " value
  if [ -z "$value" ]; then
    value="$default"
  fi
  printf "%s" "$value"
}

prompt_yes_no() {
  local prompt="$1"
  local default="$2"
  local value=""
  read -r -p "$prompt [$default]: " value
  if [ -z "$value" ]; then
    value="$default"
  fi
  case "$value" in
    y|Y|yes|YES) return 0 ;;
    n|N|no|NO) return 1 ;;
    *) return 0 ;;
  esac
}

write_sensor_config() {
  local config_path="$1"
  local sensor_name="$2"
  local wifi_enabled="$3"
  local wifi_name="$4"
  local wifi_iface="$5"
  local wifi_ssid="$6"
  local wifi_password="$7"
  local wired_enabled="$8"
  local wired_name="$9"
  local wired_iface="${10}"
  local external_http_name="${11}"
  local external_http_url="${12}"
  local location_auto="${13}"
  local location_provider="${14}"
  local location_refresh="${15}"
  local location_notes="${16}"
  local location_google_key="${17}"
  local location_lat="${18}"
  local location_lon="${19}"

  {
    echo "sensor_name: ${sensor_name}"
    echo "metrics_port: 9105"
    echo ""
    echo "# DNS domain for testing"
    echo "dns_domain: its.ac.id"
    echo ""
    echo "# Logs"
    echo "log_path: /opt/uxi-lite-sensor/logs/results.jsonl"
    echo ""
    echo "# Aruba UXI compatible mode"
    echo "export_aruba_csv: true"
    echo "aruba_csv_path: /opt/uxi-lite-sensor/logs/aruba-uxi-raw-data-report.csv"
    echo ""
    echo "# Optional delay between test cycles (seconds)"
    echo "# Aruba agents use 300 (5 min), sensors use 0 (continuous)"
    echo "inter_cycle_delay_seconds: 0"
    echo ""
    if [ "$wifi_enabled" = "yes" ]; then
      echo "wifi:"
      echo "  - name: \"${wifi_name}\""
      echo "    iface: \"${wifi_iface}\""
      echo "    ssid: \"${wifi_ssid}\""
      echo "    password: \"${wifi_password}\""
    else
      echo "wifi: []"
    fi
    echo ""
  if [ "$wired_enabled" = "yes" ]; then
    echo "wired:"
    echo "  - name: \"${wired_name}\""
    echo "    iface: \"${wired_iface}\""
  else
    echo "wired: []"
  fi
  echo ""
  cat <<EOF
# Service frequency options: fastest, 10min, 20min, 30min, 1hr, 2hr, 4hr, 6hr, 12hr
services:
  internal:
    - name: AD03
      target: ad03.its.ac.id
      tests: [icmp]
      frequency: fastest
    - name: AD07
      target: ad07.its.ac.id
      tests: [icmp]
      frequency: fastest
    - name: ClearPass
      target: 103.94.198.45
      tests: [icmp]
      frequency: fastest
    - name: CS4 Ruckus
      target: 10.0.0.1
      tests: [icmp]
      frequency: fastest
    - name: WLC10
      target: 10.24.0.10
      tests: [icmp]
      frequency: fastest
    - name: WLC11
      target: 10.24.0.11
      tests: [icmp]
      frequency: fastest
    - name: WLC12
      target: 10.24.0.12
      tests: [icmp]
      frequency: fastest
    - name: WLC13
      target: 10.24.0.13
      tests: [icmp]
      frequency: fastest
    - name: WLC14
      target: 10.24.0.14
      tests: [icmp]
      frequency: fastest
    - name: Portal ITS
      target: portal.its.ac.id
      tests: [icmp, http, tcp_80, tcp_443]
      frequency: fastest
  external:
    - name: ${external_http_name}
      target: ${external_http_url}
      tests: [icmp, http, tcp_80, tcp_443]
      frequency: fastest
    - name: Box
      target: www.box.com
      tests: [icmp, http, tcp_80, tcp_443]
      frequency: fastest
    - name: Docusign
      target: www.docusign.com
      tests: [icmp, http, tcp_80, tcp_443]
      frequency: fastest
    - name: Facebook
      target: www.facebook.com
      tests: [icmp, http, tcp_80, tcp_443]
      frequency: fastest
    - name: Google Drive
      target: drive.google.com
      tests: [icmp, http, tcp_80, tcp_443]
      frequency: fastest
    - name: Jira
      target: jira.com
      tests: [icmp, http, tcp_80, tcp_443]
      frequency: fastest
    - name: Youtube
      target: www.youtube.com
      tests: [icmp, http, tcp_80, tcp_443]
      frequency: fastest
    - name: Zoom
      target: zoom.us
      tests: [icmp, http, tcp_80, tcp_443]
      frequency: fastest
    # Throughput test - target not needed (uses throughput_test.url)
    - name: Speedtest
      tests: [throughput]
      frequency: 1hr

wifi_environment:
  enabled: true
  max_aps: 40
  min_rssi_dbm: -90
  ttl_seconds: 300
EOF
    echo ""
    if [ "$location_auto" = "yes" ]; then
      echo "location:"
      echo "  auto: true"
      echo "  provider: ${location_provider}"
      echo "  refresh_hours: ${location_refresh}"
      echo "  address_notes: \"${location_notes}\""
      if [ "$location_provider" = "google" ]; then
        echo "  google_api_key: \"${location_google_key}\""
      fi
    else
      echo "location:"
      echo "  lat: ${location_lat}"
      echo "  lon: ${location_lon}"
      echo "  address_notes: \"${location_notes}\""
    fi
    cat <<EOF

incident_thresholds:
  dns_ms: 200
  dhcp_ms: 1500
  packet_loss_pct: 5
  latency_ms: 100
  jitter_ms: 50
  association_ms: 10000
  http_ms: 3000
  rssi_dbm: -75

throughput_test:
  enabled: true
  url: "https://speed.cloudflare.com/__down?bytes=10000000"
  upload_url: "https://speed.cloudflare.com/__up"
EOF
  } > "$config_path"
}

write_sensor_config_from_template() {
  local template_path="$1"
  local config_path="$2"
  local sensor_name="$3"
  local metrics_port="$4"

  python3 - "$template_path" "$config_path" "$sensor_name" "$metrics_port" <<'PY'
import sys

try:
    import yaml
except ImportError as exc:
    raise SystemExit(f"PyYAML required for template mode: {exc}")

template_path = sys.argv[1]
config_path = sys.argv[2]
sensor_name = sys.argv[3]
metrics_port = sys.argv[4]

with open(template_path, "r", encoding="utf-8") as handle:
    data = yaml.safe_load(handle) or {}

data["sensor_name"] = sensor_name
if metrics_port:
    try:
        data["metrics_port"] = int(metrics_port)
    except ValueError:
        pass

with open(config_path, "w", encoding="utf-8") as handle:
    yaml.safe_dump(data, handle, sort_keys=False, default_flow_style=False)
PY
}

update_prometheus_targets() {
  local block_file
  block_file="$(mktemp)"
  {
    echo "      - targets:"
    for target in "${SENSOR_TARGETS[@]}"; do
      echo "          - \"${target}\""
    done
  } > "$block_file"

  if command -v rg >/dev/null 2>&1; then
    marker_found=$(rg -q "BEGIN UXI CORE TARGETS" "$PROM_FILE" && echo "yes" || echo "no")
  else
    marker_found=$(grep -q "BEGIN UXI CORE TARGETS" "$PROM_FILE" && echo "yes" || echo "no")
  fi
  if [ "$marker_found" != "yes" ]; then
    echo "Prometheus file missing UXI CORE markers: $PROM_FILE"
    rm -f "$block_file"
    return 1
  fi

  awk -v block_file="$block_file" '
    BEGIN {in_block=0}
    /# BEGIN UXI CORE TARGETS/ {
      print
      while ((getline line < block_file) > 0) print line
      close(block_file)
      in_block=1
      next
    }
    /# END UXI CORE TARGETS/ {
      in_block=0
      print
      next
    }
    !in_block {print}
  ' "$PROM_FILE" > "$PROM_FILE.tmp"
  mv "$PROM_FILE.tmp" "$PROM_FILE"
  rm -f "$block_file"
}

echo "========================================"
echo "  UXI-Lite Project Configurator"
echo "========================================"
echo ""
echo "NOTE: Blackbox Exporter is no longer used."
echo "      All service tests are done by uxi_core_exporter."
echo ""

sensor_count="$(prompt_default "Number of sensors" "1")"
external_http_url="www.google.com"
external_http_name="Google"
location_auto="yes"
location_provider="ipinfo"
location_refresh="24"
location_notes=""
location_google_key=""
location_lat=""
location_lon=""

if [ "$BASIC_MODE" -eq 0 ]; then
  external_http_url="$(prompt_default "External HTTP target (hostname)" "www.google.com")"
  external_http_name="$(prompt_default "External HTTP name" "Google")"

  if prompt_yes_no "Auto location via public IP?" "y"; then
    location_auto="yes"
    location_provider="$(prompt_default "Location provider (ipinfo/ipapi/google)" "ipinfo")"
    location_provider="$(printf "%s" "$location_provider" | tr '[:upper:]' '[:lower:]')"
    if [ "$location_provider" = "google" ]; then
      read -r -s -p "Google Geolocation API key: " location_google_key
      echo ""
    fi
    location_refresh="$(prompt_default "Location refresh hours" "24")"
    location_notes="$(prompt_default "Location notes (optional)" "")"
    location_lat=""
    location_lon=""
  else
    location_auto="no"
    location_provider=""
    location_refresh=""
    location_notes="$(prompt_default "Location notes (optional)" "")"
    location_lat="$(prompt_default "Latitude" "-7.2575")"
    location_lon="$(prompt_default "Longitude" "112.7521")"
  fi
else
  echo "Basic mode: using template config $CONFIG_TEMPLATE"
fi

mkdir -p "$SENSORS_DIR"

declare -a SENSOR_NAMES
declare -a SENSOR_HOSTS
declare -a SENSOR_TARGETS
declare -a SENSOR_CONFIGS

for i in $(seq 1 "$sensor_count"); do
  echo ""
  echo "Sensor #$i"
  sensor_name="$(prompt_default "Sensor name" "sensor-$i")"
  sensor_host="$(prompt_default "Sensor SSH host (user@ip, optional)" "")"
  host_ip="${sensor_host##*@}"
  default_target=""
  if [ -n "$host_ip" ] && [ "$host_ip" != "$sensor_host" ]; then
    default_target="${host_ip}:9105"
  fi
  metrics_target="$(prompt_default "Metrics target (IP:port)" "${default_target:-:9105}")"

  safe_name="$(echo "$sensor_name" | tr ' /' '__' | tr -cd 'A-Za-z0-9._-')"
  if [ -z "$safe_name" ]; then
    safe_name="sensor-$i"
  fi
  config_path="$SENSORS_DIR/${safe_name}.yaml"

  if [ "$BASIC_MODE" -eq 1 ]; then
    metrics_port=""
    if [[ "$metrics_target" == *":"* ]]; then
      port="${metrics_target##*:}"
      if [[ "$port" =~ ^[0-9]+$ ]]; then
        metrics_port="$port"
      fi
    fi
    write_sensor_config_from_template "$CONFIG_TEMPLATE" "$config_path" "$sensor_name" "$metrics_port"
  else
    wifi_enabled="no"
    wifi_name=""
    wifi_iface=""
    wifi_ssid=""
    wifi_password=""
    if prompt_yes_no "Configure Wi-Fi?" "y"; then
      wifi_iface="$(prompt_default "Wi-Fi interface" "wlan1")"
      wifi_ssid="$(prompt_default "Wi-Fi SSID" "")"
      if [ -n "$wifi_ssid" ]; then
        wifi_enabled="yes"
        wifi_name="$(prompt_default "Wi-Fi name" "$wifi_ssid")"
        read -r -p "Wi-Fi password (empty for open): " wifi_password
      else
        echo "Wi-Fi SSID empty, skipping Wi-Fi config."
      fi
    fi

    wired_enabled="no"
    wired_name=""
    wired_iface=""
    if prompt_yes_no "Configure wired interface?" "n"; then
      wired_enabled="yes"
      wired_iface="$(prompt_default "Wired interface" "eth0")"
      wired_name="$(prompt_default "Wired name" "LAN")"
    fi

    write_sensor_config \
      "$config_path" \
      "$sensor_name" \
      "$wifi_enabled" \
      "$wifi_name" \
      "$wifi_iface" \
      "$wifi_ssid" \
      "$wifi_password" \
      "$wired_enabled" \
      "$wired_name" \
      "$wired_iface" \
      "$external_http_name" \
      "$external_http_url" \
      "$location_auto" \
      "$location_provider" \
      "$location_refresh" \
      "$location_notes" \
      "$location_google_key" \
      "$location_lat" \
      "$location_lon"
  fi

  SENSOR_NAMES+=("$sensor_name")
  SENSOR_HOSTS+=("$sensor_host")
  SENSOR_TARGETS+=("$metrics_target")
  SENSOR_CONFIGS+=("$config_path")

  echo "Config written: $config_path"
done

cp "${SENSOR_CONFIGS[0]}" "$ROOT_DIR/sensor/config/config.yaml"

echo ""
echo "Updating Prometheus targets..."
update_prometheus_targets
echo "Prometheus config updated: $PROM_FILE"

if prompt_yes_no "Apply configs to sensors now?" "y"; then
  for idx in "${!SENSOR_HOSTS[@]}"; do
    host="${SENSOR_HOSTS[$idx]}"
    config="${SENSOR_CONFIGS[$idx]}"
    if [ -z "$host" ]; then
      echo "Skipping sensor #$((idx + 1)) (no SSH host)."
      continue
    fi
    read -r -s -p "Sudo password for $host (leave empty if NOPASSWD): " sudo_pass
    echo ""
    SUDO_PASS="$sudo_pass" "$ROOT_DIR/sensor/scripts/deploy_from_server.sh" "$host" --update --config "$config"
  done
fi

if prompt_yes_no "Apply Prometheus config to server now?" "y"; then
  server_host="$(prompt_default "Server SSH host (empty for local)" "")"
  if [ -z "$server_host" ]; then
    docker compose -f "$ROOT_DIR/server/docker/docker-compose.yml" restart prometheus grafana
  else
    read -r -s -p "Sudo password for $server_host (leave empty if NOPASSWD): " server_pass
    echo ""
    SUDO_PASS="$server_pass" "$ROOT_DIR/server/scripts/deploy_server.sh" "$server_host" --update-config
  fi
fi

echo ""
echo "========================================"
echo "  Configuration Complete"
echo "========================================"
echo ""
echo "Next steps:"
echo "  1. Deploy sensors:  ./setup.sh (option 1)"
echo "  2. Check dashboard: http://<server>:3000"
echo ""
