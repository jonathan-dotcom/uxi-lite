# UXI-Lite Troubleshooting Guide

## Quick Diagnosis

```bash
# Check service status
sudo systemctl status uxi-core

# View live logs
journalctl -u uxi-core -f

# Check metrics endpoint
curl -s http://localhost:9105/metrics | head -50

# Check specific metrics
curl -s http://localhost:9105/metrics | grep -E "uxi_core_ok|uxi_wifi_rssi|uxi_service_up"
```

## Common Issues

### 1. Service Tidak Jalan

**Symptoms:**
- `systemctl status uxi-core` menunjukkan "failed" atau "inactive"

**Solutions:**

```bash
# Check logs
journalctl -u uxi-core -n 100

# Manual run untuk debug
sudo /opt/uxi-lite-sensor/.venv/bin/python3 \
  /opt/uxi-lite-sensor/core/uxi_core_exporter.py \
  --config /opt/uxi-lite-sensor/config/config.yaml

# Check Python dependencies
/opt/uxi-lite-sensor/.venv/bin/pip list

# Reinstall dependencies
sudo /opt/uxi-lite-sensor/.venv/bin/pip install -r /opt/uxi-lite-sensor/core/requirements.txt
```

### 2. WiFi Tidak Konek

**Symptoms:**
- `uxi_wifi_rssi_dbm` menunjukkan 0 atau tidak ada
- Logs menunjukkan "Failed to connect to WiFi"

**Solutions:**

```bash
# Check WiFi radio status
nmcli radio wifi

# Enable WiFi radio
nmcli radio wifi on

# List available networks
nmcli device wifi list

# Manual connect test
nmcli device wifi connect "SSID_NAME" password "PASSWORD"

# Check config.yaml
cat /opt/uxi-lite-sensor/config/config.yaml | grep -A5 "wifi:"
```

**Config Check:**
```yaml
wifi:
  - name: Office-WiFi
    iface: wlan1          # Pastikan interface benar (wlan0, wlan1, etc)
    ssid: MySSID          # Case-sensitive!
    password: MyPassword  # Untuk open WiFi, gunakan ""
```

### 3. Dashboard Kosong (No Data)

**Symptoms:**
- Grafana dashboard menunjukkan "No data"
- Prometheus targets menunjukkan "DOWN"

**Diagnosis:**

```bash
# 1. Check sensor metrics accessible
curl http://<SENSOR_IP>:9105/metrics | grep uxi_

# 2. Check Prometheus targets
curl http://<SERVER_IP>:9090/api/v1/targets | jq

# 3. Check prometheus.yml target
cat /opt/uxi-lite-server/server/docker/prometheus.yml | grep -A5 "targets:"
```

**Solutions:**

1. **Firewall:** Pastikan port 9105 terbuka di sensor
   ```bash
   sudo ufw allow 9105/tcp
   ```

2. **Prometheus Config:** Update target IP
   ```yaml
   # server/docker/prometheus.yml
   scrape_configs:
     - job_name: 'uxi-core'
       static_configs:
         # BEGIN UXI CORE TARGETS
         - targets:
             - "192.168.1.100:9105"  # Ganti dengan IP sensor
         # END UXI CORE TARGETS
   ```

3. **Restart Prometheus:**
   ```bash
   docker compose -f /opt/uxi-lite-server/server/docker/docker-compose.yml restart prometheus
   ```

### 4. Dashboard Data Kosong Walau Prometheus OK

**Symptoms:**
- Prometheus menunjukkan target "UP"
- Tapi Grafana tetap "No data"

**Cause:** Kemungkinan `export_aruba_csv: true` tapi Aruba mode tidak update Prometheus metrics.

**Solution:** Pastikan menggunakan versi terbaru yang sudah fix bug ini. Check:
```bash
curl -s http://localhost:9105/metrics | grep uxi_service_rtt_avg_ms
```

Jika tidak ada output, update ke versi terbaru.

### 5. DNS Resolution Fails

**Symptoms:**
- `uxi_dns_ms` selalu 0 atau error
- Logs menunjukkan "DNS lookup failed"

**Solutions:**

```bash
# Check DNS config
cat /etc/resolv.conf

# Test DNS manually
dig its.ac.id
nslookup its.ac.id

# Check config dns_domain
cat /opt/uxi-lite-sensor/config/config.yaml | grep dns_domain
```

### 6. ICMP Ping Fails

**Symptoms:**
- `uxi_service_packet_loss_pct` selalu 100%
- Logs menunjukkan "ping: Operation not permitted"

**Solutions:**

```bash
# Check if running as root or with capabilities
sudo setcap cap_net_raw+ep $(which ping)

# Or run service as root (default in systemd)
cat /etc/systemd/system/uxi-core.service | grep User
```

### 7. Throughput Test Not Working

**Symptoms:**
- `uxi_throughput_download_mbps` selalu 0

**Diagnosis:**

```bash
# Test download URL manually
curl -o /dev/null -w "%{speed_download}" https://speed.cloudflare.com/__down?bytes=10000000

# Check config
cat /opt/uxi-lite-sensor/config/config.yaml | grep -A3 "throughput_test:"
```

**Config Check:**
```yaml
# Service entry (WHEN to run) - NO target needed!
services:
  external:
    - name: Speedtest
      tests: [throughput]
      frequency: 1hr

# Throughput config (HOW to run)
throughput_test:
  enabled: true
  url: https://speed.cloudflare.com/__down?bytes=10000000
  upload_url: https://speed.cloudflare.com/__up
```

### 8. Location Tidak Muncul

**Symptoms:**
- `uxi_sensor_location` tidak ada
- Geomap panel kosong

**Solutions:**

```bash
# Check internet access
curl -s https://ipinfo.io/json

# Check config
cat /opt/uxi-lite-sensor/config/config.yaml | grep -A5 "location:"
```

**Config Options:**
```yaml
# Auto-detect via IP (paling mudah)
location:
  auto: true
  provider: ipinfo
  refresh_hours: 24

# Manual coordinates
location:
  lat: -7.2575
  lon: 112.7521
  address_notes: "Gedung A, Lantai 2"
```

### 9. High Memory Usage

**Symptoms:**
- Raspberry Pi menjadi lambat
- OOM killer

**Solutions:**

```bash
# Check memory usage
free -h

# Check process memory
ps aux | grep uxi_core | awk '{print $6}'

# Reduce WiFi scan frequency
# In config.yaml:
wifi_environment:
  max_aps: 20          # Reduce from 40
  ttl_seconds: 600     # Increase from 300
```

## Log Locations

| File | Location | Description |
|------|----------|-------------|
| Service Logs | `journalctl -u uxi-core` | Systemd logs |
| JSONL Results | `/opt/uxi-lite-sensor/logs/results.jsonl` | Test results |
| Aruba CSV | `/opt/uxi-lite-sensor/logs/aruba-uxi-raw-data-report.csv` | Aruba format |
| Frequency State | `/opt/uxi-lite-sensor/state/last_run_times.json` | Service timing |

## Useful Commands

```bash
# Restart sensor
sudo systemctl restart uxi-core

# View config
cat /opt/uxi-lite-sensor/config/config.yaml

# Check CSV output
tail -20 /opt/uxi-lite-sensor/logs/aruba-uxi-raw-data-report.csv

# Check metrics count
curl -s http://localhost:9105/metrics | grep -c "^uxi_"

# Test specific metric
curl -s http://localhost:9105/metrics | grep "uxi_current_test"

# Server: restart all containers
cd /opt/uxi-lite-server/server/docker && docker compose restart

# Server: view Grafana logs
docker compose logs grafana

# Server: view Prometheus logs
docker compose logs prometheus
```

## Getting Help

1. Check logs first: `journalctl -u uxi-core -n 200`
2. Test metrics endpoint: `curl localhost:9105/metrics`
3. Verify config syntax: `python3 -c "import yaml; yaml.safe_load(open('/opt/uxi-lite-sensor/config/config.yaml'))"`
