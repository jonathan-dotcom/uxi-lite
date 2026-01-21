# Aruba UXI Compatibility Guide

UXI-Lite telah diimplementasikan untuk menjadi **100% compatible** dengan cara kerja Aruba UXI sensor. Hasil test dapat di-upload ke Aruba Central.

## Compatibility Summary

| Feature | Aruba UXI | UXI-Lite | Status |
|---------|-----------|----------|--------|
| CSV Format | ✅ | ✅ | 100% compatible |
| Test Order | ✅ | ✅ | Same order |
| WiFi Data Pattern | ✅ | ✅ | Same pattern |
| Service Frequency | ✅ | ✅ | All options |
| Prometheus Metrics | ❌ | ✅ | **BONUS** |
| Real-time Dashboard | ❌ | ✅ | **BONUS** |
| Open Source | ❌ | ✅ | **BONUS** |

## Test Cycle (Identical to Aruba UXI)

### Dari Dokumentasi Resmi Aruba

> "The sensor will only run one test at a time, but the testing process is **continuous** and runs in a **round-robin** fashion."
> 
> "A test cycle duration on the sensor depends on the **number of internal and external tests** configured on it."

**TIDAK ADA fixed cycle interval** - sensor langsung lanjut ke cycle berikutnya setelah selesai.

### Test Order Per Cycle

```
┌─────────────────────────────────────────────────────────┐
│                    TEST CYCLE                           │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  1. AP ASSOCIATION                                      │
│     └── Connect to WiFi, measure association time       │
│     └── [wifi_data row generated]                       │
│                                                         │
│  2. DHCP                                                │
│     └── Request IP address, measure lease time          │
│     └── [wifi_data row generated]                       │
│                                                         │
│  3. DNS                                                 │
│     └── Resolve configured domain                       │
│     └── [wifi_data row generated]                       │
│                                                         │
│  4. INTERNAL SERVICES (by frequency)                    │
│     └── For each service:                               │
│         ├── HTTP GET (if 'http' in tests)               │
│         ├── TCP Ping :80 (if 'tcp_80' in tests)         │
│         ├── TCP Ping :443 (if 'tcp_443' in tests)       │
│         ├── ICMP Ping (if 'icmp' in tests)              │
│         └── [wifi_data row after each test]             │
│                                                         │
│  5. EXTERNAL SERVICES (by frequency)                    │
│     └── Same as internal                                │
│     └── VoIP MOS (if 'voip_mos' in tests)              │
│     └── Throughput (if 'throughput' in tests)          │
│                                                         │
│  6. WIFI ENVIRONMENT SCAN                               │
│     └── Scan nearby APs                                 │
│                                                         │
│  7. [Optional] inter_cycle_delay_seconds                │
│                                                         │
│  8. REPEAT                                              │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

UXI-Lite juga bisa menambahkan jeda kecil antar test melalui `inter_test_delay_seconds`
(default 5.0). Set ke 0 untuk menonaktifkan.

## Service Frequency

Setiap service dapat memiliki frequency sendiri:

| Frequency | Aruba UXI | UXI-Lite | Interval |
|-----------|-----------|----------|----------|
| Fastest | ✅ | ✅ | Every cycle |
| 10 Min | ✅ | ✅ | 600 seconds |
| 20 Min | ✅ | ✅ | 1200 seconds |
| 30 Min | ✅ | ✅ | 1800 seconds |
| 1 Hour | ✅ | ✅ | 3600 seconds |
| 2 Hours | ✅ | ✅ | 7200 seconds |
| 4 Hours | ✅ | ✅ | 14400 seconds |
| 6 Hours | ✅ | ✅ | 21600 seconds |
| 12 Hours | ✅ | ✅ | 43200 seconds |

### Configuration Example

```yaml
services:
  internal:
    - name: Gateway
      target: 10.0.0.1
      tests: [icmp]
      frequency: fastest    # Every cycle

    - name: Portal
      target: portal.company.com
      tests: [icmp, http, tcp_80, tcp_443]
      frequency: 10min      # Every 10 minutes

  external:
    - name: Google
      target: www.google.com
      tests: [icmp, http, tcp_80, tcp_443]
      frequency: fastest

    - name: Microsoft Teams
      target: worldaz.tr.teams.microsoft.com
      tests: [voip_mos]
      frequency: fastest

    - name: Speedtest
      target: speed.cloudflare.com
      tests: [throughput]
      frequency: 1hr        # Every 1 hour
```

## Service Test Order (100% Aruba Compatible)

Untuk setiap service dengan full tests:

| Step | Test Type | Target Format | Aruba UXI | UXI-Lite |
|------|-----------|---------------|-----------|----------|
| 1 | HTTP GET | http://host:80 | ✅ | ✅ |
| 2 | TCP Ping | host:80 | ✅ | ✅ |
| 3 | HTTP GET | https://host:443 | ✅ | ✅ |
| 4 | TCP Ping | host:443 | ✅ | ✅ |
| 5 | ICMP Ping | host | ✅ | ✅ |

## CSV Schema (100% Compatible)

UXI-Lite menghasilkan CSV dengan format yang **identik** dengan Aruba UXI:

```csv
"timestamp","sensor_uid","sensor_name","network_uid","network_alias","interface_type","test_type_code","target","name","ip_address","elapsed_time_seconds","bssid","channel","channel_utilization","frequency","rssi","latency","jitter","packet_loss","download_speed","upload_speed","service_uid"
```

### Test Type Codes

| Aruba UXI | UXI-Lite | Description |
|-----------|----------|-------------|
| `ap_assoc` | `ap_assoc` | WiFi association time |
| `dhcp` | `dhcp` | DHCP lease time |
| `dns` | `dns` | DNS resolution time |
| `ping` | `ping` | ICMP/TCP ping test |
| `http_get` | `http_get` | HTTP GET latency |
| `wifi_data` | `wifi_data` | WiFi metrics snapshot |

### WiFi Data Pattern

Aruba UXI menghasilkan `wifi_data` row bersamaan dengan setiap test:

```csv
timestamp,test_type,service_name
12:09:15,ap_assoc,""
12:09:15,wifi_data,""              <-- same timestamp
12:09:30,dhcp,""
12:09:30,wifi_data,""              <-- same timestamp
12:10:15,ping,"Google"
12:10:15,wifi_data,"Google"        <-- same timestamp
```

UXI-Lite mengikuti pola yang **sama persis**.

## Configuration Mapping

### Aruba UXI Dashboard → UXI-Lite config.yaml

| Aruba Setting | UXI-Lite Config | Example |
|---------------|-----------------|---------|
| Service Name | `services.*.name` | `"Google"` |
| Target Host | `services.*.target` | `"www.google.com"` |
| Port 80 Test | `tests: [tcp_80]` | - |
| Port 443 Test | `tests: [tcp_443]` | - |
| ICMP Ping | `tests: [icmp]` | - |
| HTTP Status | `tests: [http]` | - |
| VoIP MOS | `tests: [voip_mos]` | - |
| Throughput | `tests: [throughput]` | - |
| Frequency: Fastest | `frequency: fastest` | - |
| Frequency: 10 Min | `frequency: 10min` | - |
| Frequency: 1 Hour | `frequency: 1hr` | - |

### Global Settings

| Aruba Setting | UXI-Lite Config | Default |
|---------------|-----------------|---------|
| Agent Mode Delay | `inter_cycle_delay_seconds` | 300 (5 min) |
| Sensor Mode Delay | `inter_cycle_delay_seconds` | 0 (continuous) |
| CSV Export | `export_aruba_csv` | `true` |
| CSV Path | `aruba_csv_path` | `/opt/uxi-lite-sensor/logs/aruba-uxi-raw-data-report.csv` |

### UXI-Lite-only Settings (Optional)

- `inter_test_delay_seconds`: jeda antar test untuk meniru pacing Aruba (default 5.0, set 0 untuk off)
- `wifi.*.bssid_lock`: kunci ke BSSID AP tertentu untuk mencegah roaming

```yaml
inter_test_delay_seconds: 5.0
wifi:
  - name: "myITS-WiFi"
    iface: "wlan0"
    ssid: "myITS-WiFi"
    bssid_lock: "a0:25:d7:df:3e:70"
```

## UXI-Lite Bonus Features

UXI-Lite menambahkan fitur yang **TIDAK ADA** di Aruba UXI:

### 1. Real-time Prometheus Metrics

```bash
curl http://sensor:9105/metrics | grep uxi_
```

- 40+ metric types
- Real-time updates
- Historical data in Prometheus

### 2. Real-time Dashboard

- Current test indicator
- Cycle progress percentage
- All metrics in one dashboard
- Custom time ranges

### 3. Throughput to Prometheus

Aruba UXI throughput results **tidak** masuk CSV export. UXI-Lite menulisnya ke
Prometheus dan juga menambahkan row throughput ke CSV (untuk kebutuhan lokal).

```
uxi_throughput_download_mbps{sensor="...", network="...", target="..."}
uxi_throughput_upload_mbps{sensor="...", network="...", target="..."}
```

## Throughput Test Configuration

UXI-Lite throughput test has two parts:

### 1. Service Entry (WHEN to run)

```yaml
services:
  external:
    # NO target needed for throughput-only service!
    - name: Speedtest
      tests: [throughput]
      frequency: 1hr
```

- `name`: Label shown in dashboard
- `target`: **NOT NEEDED** for throughput (would be misleading)
- `tests: [throughput]`: Trigger throughput test
- `frequency`: How often to run

### 2. Throughput Config (HOW to run)

```yaml
throughput_test:
  enabled: true
  # Aruba UXI throughput uses Fast.com (headless Chromium).
  # UXI-Lite can use Fast.com backend directly (recommended for Aruba-like results):
  # - method: fastcom
  # Or URL-based testing:
  # - method: http
  method: fastcom
  connections: 5
  upload_connections: 1
  upload_bytes: 5000000
  timeout_s: 20
  url: https://speed.cloudflare.com/__down?bytes=10000000   # Download URL
  upload_url: https://speed.cloudflare.com/__up             # Upload URL
```

- `method`: `fastcom` (Aruba-like) or `http` (custom URL)
- `connections`: parallel download connections (more accurate, more bandwidth)
- `upload_bytes`: upload payload size for upload throughput
- `url`: Actual URL for download test (used by `method: http`)
- `upload_url`: Actual URL for upload test (used by `method: http`)

**Note:** Unlike other service tests, throughput test does NOT use the `target` field. This avoids confusion about which URL is actually used.

## Verified Against Real Aruba UXI

Implementasi ini telah diverifikasi terhadap CSV export dari Aruba UXI sensor asli:

- ✅ File: `aruba-uxi-raw-data-report-2026-01-13T11_49_28.csv`
- ✅ Rows: 6,318
- ✅ Test types: ap_assoc, dhcp, dns, ping, http_get, wifi_data
- ✅ WiFi data pattern: same timestamp pairing
- ✅ Column order: identical
- ✅ Data format: identical

## Migration from Aruba UXI

1. Export service list from Aruba Central
2. Convert to `config.yaml` format:
   ```yaml
   services:
     internal:
       - name: "Service Name from Aruba"
         target: "target.host.com"
         tests: [icmp, http, tcp_80, tcp_443]
         frequency: fastest
   ```
3. Deploy UXI-Lite sensor
4. (Optional) Upload CSV to Aruba Central for historical continuity
