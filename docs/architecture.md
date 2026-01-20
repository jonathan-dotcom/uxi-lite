# UXI-Lite Architecture

## Overview

UXI-Lite adalah solusi monitoring User Experience yang kompatibel dengan Aruba UXI. Sistem terdiri dari dua komponen utama:

```
┌─────────────────────────────────────────────────────────────────┐
│                    SENSOR (Raspberry Pi)                        │
│                                                                 │
│   ┌─────────────┐     ┌─────────────────────────────────────┐  │
│   │ config.yaml │────►│     uxi_core_exporter.py            │  │
│   └─────────────┘     │                                     │  │
│                       │  - WiFi Association Test            │  │
│                       │  - DHCP Test                        │  │
│                       │  - DNS Test                         │  │
│                       │  - ICMP Ping Test                   │  │
│                       │  - HTTP GET Test                    │  │
│                       │  - TCP Connect Test                 │  │
│                       │  - VoIP MOS Calculation             │  │
│                       │  - Throughput Test                  │  │
│                       │  - WiFi Environment Scan            │  │
│                       └──────────────┬──────────────────────┘  │
│                                      │                          │
│                      ┌───────────────┼───────────────┐          │
│                      │               │               │          │
│                      ▼               ▼               ▼          │
│              ┌───────────┐   ┌───────────┐   ┌───────────┐     │
│              │  CSV File │   │ Prometheus│   │   JSONL   │     │
│              │  (Aruba)  │   │  Metrics  │   │   Logs    │     │
│              └───────────┘   └─────┬─────┘   └───────────┘     │
│                    │               │                            │
│                    ▼               │                            │
│            Upload to               │                            │
│            Aruba Central           │                            │
└────────────────────────────────────┼────────────────────────────┘
                                     │ :9105
                                     ▼ scrape
┌─────────────────────────────────────────────────────────────────┐
│                    SERVER (Docker)                              │
│                                                                 │
│   ┌─────────────────┐          ┌─────────────────────────────┐ │
│   │   Prometheus    │─────────►│         Grafana             │ │
│   │     :9090       │          │          :3000              │ │
│   └─────────────────┘          │                             │ │
│                                │   ┌─────────────────────┐   │ │
│                                │   │  UXI-Lite Dashboard │   │ │
│                                │   │    (52 panels)      │   │ │
│                                │   └─────────────────────┘   │ │
│                                └─────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Sensor (Raspberry Pi)

**uxi_core_exporter.py** - Single Python script yang menjalankan semua test:

| Test | Description | Output |
|------|-------------|--------|
| WiFi Association | Konek ke WiFi, ukur waktu | association_time_ms |
| DHCP | Request IP address | dhcp_time_ms |
| DNS | Resolve domain | dns_time_ms |
| ICMP Ping | Ping target 10x | rtt_avg, jitter, packet_loss |
| HTTP GET | Download webpage | http_time_ms, status_code |
| TCP Connect | Connect ke port | tcp_time_ms |
| VoIP MOS | Calculate MOS score | mos (1.0-4.5) |
| Throughput | Download/Upload test | download_mbps, upload_mbps |
| WiFi Scan | Scan nearby APs | ap_count, channel_usage |

**Output Formats:**

1. **Prometheus Metrics** (`:9105/metrics`)
   - Real-time metrics untuk Grafana
   - ~40 unique metric types

2. **Aruba CSV** (`aruba-uxi-raw-data-report.csv`)
   - Format identik dengan Aruba UXI sensor
   - Bisa di-upload ke Aruba Central

3. **JSONL Logs** (`results.jsonl`)
   - Raw test results untuk debugging

### 2. Server (Docker)

**Prometheus** - Time-series database:
- Scrape sensor setiap 30 detik
- Simpan data 15 hari (configurable)

**Grafana** - Visualization:
- Auto-provisioned dashboard
- 52 panels dalam 7 kategori
- Real-time updates

## Test Cycle (Aruba Compatible)

UXI-Lite mengikuti urutan test yang sama dengan Aruba UXI:

```
1. WiFi Association (connect to SSID)
      ↓
2. DHCP (get IP address)
      ↓
3. DNS (resolve domain)
      ↓
4. For each service:
   ├── ICMP Ping (if tests include 'icmp')
   ├── HTTP GET (if tests include 'http')
   ├── TCP 80 (if tests include 'tcp_80')
   ├── TCP 443 (if tests include 'tcp_443')
   ├── VoIP MOS (if tests include 'voip_mos')
   └── Throughput (if tests include 'throughput')
      ↓
5. WiFi Environment Scan
      ↓
6. [Optional] inter_cycle_delay_seconds
      ↓
7. Repeat from step 1
```

## Frequency Scheduling

Setiap service bisa punya frequency berbeda:

```yaml
services:
  external:
    - name: Google
      target: www.google.com
      tests: [icmp, http]
      frequency: fastest     # Setiap cycle

    - name: Speedtest
      target: speed.cloudflare.com
      tests: [throughput]
      frequency: 1hr         # Setiap 1 jam
```

| Frequency | Seconds | Description |
|-----------|---------|-------------|
| fastest | 0 | Setiap cycle |
| 10min | 600 | 10 menit |
| 20min | 1200 | 20 menit |
| 30min | 1800 | 30 menit |
| 1hr | 3600 | 1 jam |
| 2hr | 7200 | 2 jam |
| 4hr | 14400 | 4 jam |
| 6hr | 21600 | 6 jam |
| 12hr | 43200 | 12 jam |

## Ports

| Service | Port | Protocol |
|---------|------|----------|
| uxi_core_exporter | 9105 | HTTP (Prometheus) |
| Prometheus | 9090 | HTTP |
| Grafana | 3000 | HTTP |

## File Locations

### Sensor (Raspberry Pi)

```
/opt/uxi-lite-sensor/
├── config/
│   └── config.yaml          # Active configuration
├── core/
│   └── uxi_core_exporter.py # Main exporter
├── logs/
│   ├── results.jsonl        # Test results log
│   └── aruba-uxi-raw-data-report.csv  # Aruba format CSV
├── state/
│   └── last_run_times.json  # Frequency tracking
└── .venv/                   # Python virtual environment
```

### Server

```
/opt/uxi-lite-server/
└── server/
    └── docker/
        ├── docker-compose.yml
        ├── prometheus.yml
        └── grafana/
            ├── provisioning/
            │   ├── datasources/
            │   └── dashboards/
            └── dashboards/
                └── uxi-lite-dashboard.json
```

## Metrics Reference

### Core Metrics
- `uxi_core_ok` - Test cycle success (1=ok, 0=fail)
- `uxi_core_time_ms` - Total cycle time
- `uxi_connection_quality_score` - Overall quality (0-100)

### WiFi Metrics
- `uxi_wifi_rssi_dbm` - Signal strength
- `uxi_wifi_channel` - WiFi channel number
- `uxi_wifi_rx_bitrate_mbps` - RX bitrate
- `uxi_wifi_band` - Band indicator (2.4GHz/5GHz)
- `uxi_wifi_channel_busy_pct` - Channel utilization

### Service Metrics
- `uxi_service_rtt_avg_ms` - Average latency
- `uxi_service_packet_loss_pct` - Packet loss percentage
- `uxi_service_jitter_ms` - Jitter
- `uxi_service_up` - Service reachability (1=up, 0=down)

### Performance Metrics
- `uxi_throughput_download_mbps` - Download speed
- `uxi_throughput_upload_mbps` - Upload speed
- `uxi_voip_mos` - VoIP MOS score (1.0-4.5)

### Real-time Tracking
- `uxi_current_test` - Currently running test
- `uxi_cycle_number` - Current cycle number
- `uxi_cycle_progress_pct` - Cycle completion percentage
