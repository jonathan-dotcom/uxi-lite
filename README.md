# UXI-Lite

Open-source User Experience Insight (UXI) monitoring solution menggunakan Raspberry Pi sebagai sensor dan Prometheus + Grafana untuk visualisasi. **100% kompatibel dengan Aruba UXI** dengan **91% cost savings**.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    SENSOR (Raspberry Pi)                        │
│                                                                 │
│   config.yaml ──► uxi_core_exporter.py                         │
│                          │                                      │
│                          ├──► CSV File (Aruba format)          │
│                          │    └── Upload to Aruba Central      │
│                          │                                      │
│                          └──► Prometheus Metrics (:9105)       │
│                               └── Real-time monitoring         │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ scrape
┌─────────────────────────────────────────────────────────────────┐
│                    SERVER (Docker)                              │
│                                                                 │
│   Prometheus (:9090) ──► Grafana (:3000)                       │
│                              │                                  │
│                              ▼                                  │
│                    Dashboard (52 panels)                        │
│                    - Real-time test status                      │
│                    - WiFi metrics                               │
│                    - Service latency/jitter                     │
│                    - Throughput & VoIP MOS                      │
└─────────────────────────────────────────────────────────────────┘
```

## ✨ Features

- **Aruba UXI Compatible** - Same test order, CSV format, and metrics as real Aruba UXI sensors
- **Dual Output** - CSV for Aruba Central + Prometheus metrics for Grafana
- **Real-time Dashboard** - 52 panels showing current test, progress, and all metrics
- **Frequency Scheduling** - Per-service frequency (fastest, 10min, 1hr, etc.)
- **All-in-One Exporter** - No Blackbox Exporter needed, everything in one Python script

## 📊 Metrics yang Dikumpulkan

| Kategori | Metrics |
|----------|---------|
| **Wi-Fi Signal** | RSSI, Band, Channel, TX/RX Bitrate, Channel Busy % |
| **Connection** | AP Association Time, DHCP Response, DNS Lookup |
| **Services** | Latency (RTT), Packet Loss, Jitter, HTTP Response |
| **Performance** | Throughput Download/Upload, VoIP MOS Score |
| **Environment** | Nearby APs, Channel Occupancy, Client Count |
| **Status** | Current Test, Cycle Progress, Connection Quality Score |

## 🚀 Quick Start

### 1. Interactive Setup (Recommended)

```bash
# Extract dan jalankan
unzip uxi-lite-fixed.zip
cd uxi-lite
chmod +x setup.sh
./setup.sh
```

### 2. Menu Options

```
========================================
  UXI-Lite Setup Menu
========================================

SENSOR (Raspberry Pi):
  1) Deploy sensor ke Raspberry Pi
  2) Update sensor (code only)

SERVER (Prometheus + Grafana):
  3) Deploy server ke remote machine
  4) Update dashboard
  5) Install server di mesin ini

CONFIG:
  6) Edit konfigurasi sensor
  7) Edit konfigurasi prometheus
  8) Configure project (multi-sensor)
  9) Configure project (basic template)
```

### 3. Typical Workflow

```bash
# Step 1: Edit config
nano sensor/config/config.yaml

# Step 2: Deploy sensor
./setup.sh  # Pilih opsi 1

# Step 3: Deploy server
./setup.sh  # Pilih opsi 3 atau 5

# Step 4: Access dashboard
# http://<SERVER_IP>:3000 (admin/admin)
```

## ⚙️ Configuration

### Sensor Config (`sensor/config/config.yaml`)

```yaml
sensor_name: TW-2-DPTSI
metrics_port: 9105

# DNS domain for testing
dns_domain: its.ac.id

# Logs
log_path: /opt/uxi-lite-sensor/logs/results.jsonl

# ============================================
# ARUBA UXI COMPATIBLE MODE
# ============================================
export_aruba_csv: true
aruba_csv_path: /opt/uxi-lite-sensor/logs/aruba-uxi-raw-data-report.csv

# Delay between test cycles (seconds)
# Aruba agents: 300 (5 min), Sensors: 0 (continuous)
inter_cycle_delay_seconds: 0

# ============================================
# NETWORK CONFIGURATION
# ============================================

# OPTION 1: WPA Enterprise (802.1X) - University/Corporate WiFi
wifi:
  - name: myITS-WiFi
    iface: wlan0
    ssid: myITS-WiFi
    # 802.1X Configuration
    eap_method: PEAP           # Options: PEAP, TTLS, TLS
    phase2_auth: MSCHAPv2      # Options: MSCHAPv2, PAP, CHAP, GTC
    identity: "user@student.its.ac.id"
    password: "your_password"
    # anonymous_identity: ""   # Optional

# OPTION 2: WPA-PSK (Personal) - Home/Simple WiFi
# wifi:
#   - name: Home-WiFi
#     iface: wlan0
#     ssid: MyHomeNetwork
#     password: wifi_password

wired: []

# ============================================
# SERVICES TO TEST
# ============================================
# Frequency options: fastest, 10min, 20min, 30min, 1hr, 2hr, 4hr, 6hr, 12hr
services:
  internal:
    - name: Gateway
      target: 10.0.0.1
      tests: [icmp]
      frequency: fastest

    - name: Portal
      target: portal.company.com
      tests: [icmp, http, tcp_80, tcp_443]
      frequency: fastest

  external:
    - name: Google
      target: www.google.com
      tests: [icmp, http, tcp_80, tcp_443]
      frequency: fastest

    - name: Microsoft Teams
      target: worldaz.tr.teams.microsoft.com
      tests: [voip_mos]
      frequency: fastest

    # Throughput test - NO target needed (uses throughput_test.url)
    - name: Speedtest
      tests: [throughput]
      frequency: 1hr

# ============================================
# THROUGHPUT TEST CONFIGURATION
# ============================================
# This configures HOW the throughput test works (the URLs to use)
# The service entry above configures WHEN it runs (name & frequency)
throughput_test:
  enabled: true
  url: https://speed.cloudflare.com/__down?bytes=10000000
  upload_url: https://speed.cloudflare.com/__up

# ============================================
# OTHER SETTINGS
# ============================================
wifi_environment:
  enabled: true
  max_aps: 40
  min_rssi_dbm: -90
  ttl_seconds: 300

location:
  auto: true
  provider: ipinfo
  refresh_hours: 24

incident_thresholds:
  dns_ms: 200
  dhcp_ms: 1500
  packet_loss_pct: 5
  latency_ms: 100
  jitter_ms: 50
  association_ms: 10000
  http_ms: 3000
  rssi_dbm: -75
```

### Service Test Types

| Test Type | Description | Target Format |
|-----------|-------------|---------------|
| `icmp` | ICMP Ping | hostname atau IP |
| `http` | HTTP GET | hostname (otomatis https://) |
| `tcp_80` | TCP Connect port 80 | hostname atau IP |
| `tcp_443` | TCP Connect port 443 | hostname atau IP |
| `voip_mos` | VoIP MOS calculation | hostname atau IP |
| `throughput` | Download/Upload speed | hostname (ignored, uses throughput_test.url) |

### Frequency Options

| Frequency | Interval | Use Case |
|-----------|----------|----------|
| `fastest` | Every cycle | Critical services |
| `10min` | 10 minutes | Important services |
| `30min` | 30 minutes | Normal services |
| `1hr` | 1 hour | Throughput tests |
| `6hr` | 6 hours | Background checks |
| `12hr` | 12 hours | Daily checks |

## 📁 File Structure

```
uxi-lite/
├── setup.sh                    # Interactive setup menu
├── scripts/
│   └── configure_project.sh    # Multi-sensor wizard
├── sensor/
│   ├── config/
│   │   ├── config.yaml         # Active config
│   │   ├── template.yaml       # Template for new sensors
│   │   └── sensors/            # Per-sensor configs
│   ├── core/
│   │   └── uxi_core_exporter.py  # Main exporter
│   ├── scripts/
│   │   ├── install_sensor.sh   # Fresh install
│   │   ├── update_sensor.sh    # Quick update
│   │   └── deploy_from_server.sh
│   └── systemd/
│       └── uxi-core.service
└── server/
    ├── docker/
    │   ├── docker-compose.yml
    │   ├── prometheus.yml
    │   └── grafana/
    │       └── dashboards/
    │           └── uxi-lite-dashboard.json
    └── scripts/
        ├── install_server.sh
        ├── update_server.sh
        ├── deploy_server.sh
        ├── up.sh
        └── down.sh
```

## ✅ Verify Installation

```bash
# Check sensor metrics
curl http://<SENSOR_IP>:9105/metrics | grep uxi_

# Check specific metrics
curl -s http://<SENSOR_IP>:9105/metrics | grep -E "uxi_service_rtt|uxi_wifi_rssi|uxi_current_test"

# Check Prometheus targets
curl http://<SERVER_IP>:9090/api/v1/targets

# Check Aruba CSV output
cat /opt/uxi-lite-sensor/logs/aruba-uxi-raw-data-report.csv

# Access Grafana
# http://<SERVER_IP>:3000 (admin/admin)
```

## 🔧 Troubleshooting

| Problem | Solution |
|---------|----------|
| Service tidak jalan | `sudo systemctl status uxi-core` dan `journalctl -u uxi-core -f` |
| Wi-Fi tidak konek | Cek SSID/password, pastikan `nmcli radio wifi on` |
| Prometheus tidak scrape | Cek IP di prometheus.yml, pastikan firewall allow port 9105 |
| Dashboard kosong | Pastikan variable sensor/network dipilih di Grafana |
| No data di dashboard | Pastikan `export_aruba_csv: true` dan metrics di-update |

## 📖 Documentation

- [Architecture Details](docs/architecture.md)
- [Aruba UXI Compatibility](docs/aruba-uxi-compatibility.md)
- [Troubleshooting Guide](docs/troubleshooting.md)

## 🆚 Comparison with Aruba UXI

| Feature | Aruba UXI | UXI-Lite |
|---------|-----------|----------|
| Hardware | Aruba Sensor ($500+) | Raspberry Pi ($35) |
| Subscription | Required ($$$) | Free |
| CSV Format | ✅ | ✅ Compatible |
| Test Order | ✅ | ✅ Same order |
| Dashboard | Aruba Central | Grafana (customizable) |
| Real-time | ❌ (batch upload) | ✅ Prometheus metrics |
| Open Source | ❌ | ✅ |

## 📝 License

MIT License
