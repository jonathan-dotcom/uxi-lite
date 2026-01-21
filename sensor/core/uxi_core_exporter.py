#!/usr/bin/env python3
"""UXI-Lite Core Tests Exporter."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import math
import os
import re
import socket
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import yaml
from prometheus_client import Counter, Gauge, start_http_server

from triage import collect_triage


LOG = logging.getLogger("uxi_core_exporter")

INCIDENT_TYPES = (
    "high_dns_lookup_time",
    "dhcp_slow",
    "packet_loss",
    "high_latency",
    "association_slow",
    "weak_signal",
    "captive_portal",
    "http_slow",
    "high_jitter",
)
INCIDENT_STATE_PATH = "/opt/uxi-lite-sensor/state/incidents.json"
ARUBA_STATE_PATH = "/opt/uxi-lite-sensor/state/aruba_state.json"

# Aruba UXI raw-data-report schema (22 columns)
ARUBA_RAW_COLUMNS = [
    "timestamp",
    "sensor_uid",
    "sensor_name",
    "network_uid",
    "network_alias",
    "interface_type",
    "test_type_code",
    "target",
    "name",
    "ip_address",
    "elapsed_time_seconds",
    "bssid",
    "channel",
    "channel_utilization",
    "frequency",
    "rssi",
    "latency",
    "jitter",
    "packet_loss",
    "download_speed",
    "upload_speed",
    "service_uid",
]
TEST_ALIASES = {
    "ping": "icmp",
    "icmp_ping": "icmp",
    "http_2xx": "http",
    "https": "http",
    "tcp80": "tcp_80",
    "tcp_80": "tcp_80",
    "tcp-80": "tcp_80",
    "tcp:80": "tcp_80",
    "tcp443": "tcp_443",
    "tcp_443": "tcp_443",
    "tcp-443": "tcp_443",
    "tcp:443": "tcp_443",
}


UXI_CORE_OK = Gauge(
    "uxi_core_ok",
    "UXI core step success (1=ok, 0=fail)",
    ["sensor", "network", "step"],
)
UXI_CORE_TIME_MS = Gauge(
    "uxi_core_time_ms",
    "UXI core step duration in milliseconds",
    ["sensor", "network", "step"],
)

# Core test specific timing metrics (for dashboard panels)
UXI_AP_ASSOCIATION_TIME_MS = Gauge(
    "uxi_ap_association_time_ms",
    "WiFi AP association time in milliseconds",
    ["sensor", "network"],
)
UXI_DHCP_TIME_MS = Gauge(
    "uxi_dhcp_time_ms",
    "DHCP response time in milliseconds",
    ["sensor", "network"],
)
UXI_DNS_TIME_MS = Gauge(
    "uxi_dns_time_ms",
    "DNS lookup time in milliseconds",
    ["sensor", "network"],
)

UXI_NETWORK_IP_PRESENT = Gauge(
    "uxi_network_ip_present",
    "Network IPv4 present (1=present, 0=missing)",
    ["sensor", "network"],
)
UXI_WIFI_RSSI_DBM = Gauge(
    "uxi_wifi_rssi_dbm",
    "Wi-Fi RSSI in dBm",
    ["sensor", "network"],
)
UXI_WIFI_FREQ_MHZ = Gauge(
    "uxi_wifi_freq_mhz",
    "Wi-Fi frequency in MHz",
    ["sensor", "network"],
)
UXI_WIFI_CHANNEL = Gauge(
    "uxi_wifi_channel",
    "Wi-Fi channel number",
    ["sensor", "network"],
)
UXI_WIFI_TX_BITRATE_MBPS = Gauge(
    "uxi_wifi_tx_bitrate_mbps",
    "Wi-Fi TX bitrate in Mbps",
    ["sensor", "network"],
)
UXI_WIFI_RX_BITRATE_MBPS = Gauge(
    "uxi_wifi_rx_bitrate_mbps",
    "Wi-Fi RX bitrate in Mbps",
    ["sensor", "network"],
)
UXI_WIFI_CHANNEL_BUSY_PCT = Gauge(
    "uxi_wifi_channel_busy_pct",
    "Wi-Fi channel busy percentage",
    ["sensor", "network"],
)
UXI_WIFI_ENV_AP_RSSI_DBM = Gauge(
    "uxi_wifi_env_ap_rssi_dbm",
    "Wi-Fi environment AP RSSI in dBm",
    ["sensor", "network", "iface", "ssid", "bssid", "band", "channel", "width_mhz"],
)
UXI_WIFI_ENV_AP_LAST_SEEN_SECONDS = Gauge(
    "uxi_wifi_env_ap_last_seen_seconds",
    "Wi-Fi environment AP last seen timestamp in seconds",
    ["sensor", "network", "iface", "ssid", "bssid", "band", "channel", "width_mhz"],
)
UXI_WIFI_ENV_CHANNEL_AP_COUNT = Gauge(
    "uxi_wifi_env_channel_ap_count",
    "Wi-Fi environment AP count per channel",
    ["sensor", "network", "band", "channel"],
)
UXI_WIFI_ENV_CHANNEL_MAX_RSSI_DBM = Gauge(
    "uxi_wifi_env_channel_max_rssi_dbm",
    "Wi-Fi environment max RSSI per channel",
    ["sensor", "network", "band", "channel"],
)
UXI_WIFI_ENV_CHANNEL_AVG_RSSI_DBM = Gauge(
    "uxi_wifi_env_channel_avg_rssi_dbm",
    "Wi-Fi environment average RSSI per channel",
    ["sensor", "network", "band", "channel"],
)
UXI_WIFI_BAND = Gauge(
    "uxi_wifi_band",
    "Wi-Fi band indicator (2.4/5/6 GHz)",
    ["sensor", "network", "band"],
)
UXI_SERVICE_RTT_AVG_MS = Gauge(
    "uxi_service_rtt_avg_ms",
    "Service RTT average in ms",
    ["sensor", "network", "target", "scope"],
)
UXI_SERVICE_PACKET_LOSS_PCT = Gauge(
    "uxi_service_packet_loss_pct",
    "Service packet loss percentage",
    ["sensor", "network", "target", "scope"],
)
UXI_SERVICE_JITTER_MS = Gauge(
    "uxi_service_jitter_ms",
    "Service jitter (mdev) in ms",
    ["sensor", "network", "target", "scope"],
)
UXI_SERVICE_UP = Gauge(
    "uxi_service_up",
    "Service reachability (1=UP, 0=DOWN)",
    ["sensor", "network", "target", "scope", "name"],
)
UXI_SERVICE_LAST_TEST_TIMESTAMP = Gauge(
    "uxi_service_last_test_timestamp",
    "Unix timestamp of last service test",
    ["sensor", "network", "target", "scope"],
)
UXI_LAST_DATA_TIMESTAMP = Gauge(
    "uxi_last_data_timestamp",
    "Unix timestamp of when sensor last sent data",
    ["sensor", "network"],
)
UXI_CURRENT_TEST = Gauge(
    "uxi_current_test",
    "Currently running test (1=active, 0=idle)",
    ["sensor", "network", "test_type", "target", "service_name"],
)
UXI_CYCLE_NUMBER = Gauge(
    "uxi_cycle_number",
    "Current test cycle number",
    ["sensor"],
)
UXI_CYCLE_PROGRESS = Gauge(
    "uxi_cycle_progress_pct",
    "Test cycle progress percentage (0-100)",
    ["sensor", "network"],
)
UXI_CYCLE_TESTS_TOTAL = Gauge(
    "uxi_cycle_tests_total",
    "Total number of tests in current cycle",
    ["sensor", "network"],
)
UXI_CYCLE_TESTS_COMPLETED = Gauge(
    "uxi_cycle_tests_completed",
    "Number of tests completed in current cycle",
    ["sensor", "network"],
)
UXI_THROUGHPUT_DOWNLOAD_MBPS = Gauge(
    "uxi_throughput_download_mbps",
    "Throughput download speed in Mbps (Fast.com-like test)",
    ["sensor", "network", "target"],
)
UXI_SENSOR_INFO = Gauge(
    "uxi_sensor_info",
    "UXI sensor info",
    ["sensor", "model", "serial"],
)
UXI_NETWORK_INFO = Gauge(
    "uxi_network_info",
    "UXI network info",
    [
        "sensor",
        "network",
        "ip_config",
        "dhcp_server",
        "gateway",
        "primary_dns",
        "secondary_dns",
        "wifi_mac",
        "wifi_ip",
    ],
)
UXI_SENSOR_LOCATION = Gauge(
    "uxi_sensor_location",
    "UXI sensor location info",
    ["sensor", "network", "lat", "lon", "address_notes"],
)
UXI_WIFI_BSSID_INFO = Gauge(
    "uxi_wifi_bssid_info",
    "Wi-Fi BSSID info",
    ["sensor", "network", "bssid", "ssid"],
)
UXI_WIFI_FRAME_RETRY_RATE_PCT = Gauge(
    "uxi_wifi_frame_retry_rate_pct",
    "Wi-Fi frame retry rate percentage",
    ["sensor", "network"],
)
UXI_WIFI_CLIENT_COUNT = Gauge(
    "uxi_wifi_client_count",
    "Wi-Fi client count",
    ["sensor", "network"],
)
UXI_CAPTIVE_PORTAL_DETECTED = Gauge(
    "uxi_captive_portal_detected",
    "Captive portal detected (1=yes, 0=no)",
    ["sensor", "network"],
)
UXI_CONNECTION_QUALITY_SCORE = Gauge(
    "uxi_connection_quality_score",
    "Overall connection quality score (0-100)",
    ["sensor", "network"],
)
UXI_VOIP_MOS = Gauge(
    "uxi_voip_mos",
    "VoIP MOS score",
    ["sensor", "network", "scope"],
)
UXI_SERVICE_SCOPE = Gauge(
    "uxi_service_scope",
    "Service scope marker",
    ["sensor", "network", "target", "scope"],
)
UXI_INCIDENT_ACTIVE = Gauge(
    "uxi_incident_active",
    "Incident active (1=active, 0=clear)",
    ["sensor", "network", "type"],
)
UXI_INCIDENTS_RESOLVED_TOTAL = Counter(
    "uxi_incidents_resolved_total",
    "Incidents resolved total",
    ["sensor", "network", "type"],
)
UXI_INCIDENT_RESOLVED_EVENT_DURATION_MS = Gauge(
    "uxi_incident_resolved_event_duration_ms",
    "Incident resolved event duration in ms",
    ["sensor", "network", "type", "start_ts", "end_ts"],
)


@dataclass
class CommandResult:
    """Result of a command execution."""

    returncode: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool


@dataclass
class StepResult:
    """Result of a test step."""

    ok: bool
    duration_ms: int
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert step result to JSON-serializable dict.

        Returns:
            Step result dict.
        """
        data: Dict[str, Any] = {
            "ok": 1 if self.ok else 0,
            "duration_ms": self.duration_ms,
        }
        if self.error:
            data["error"] = self.error
        return data


@dataclass
class NetworkConfig:
    """Network configuration entry."""

    name: str
    kind: str
    iface: str
    ssid: Optional[str]
    password: Optional[str]
    external_url: str
    # WPA Enterprise (802.1X) fields
    eap_method: Optional[str] = None  # PEAP, TTLS, TLS
    phase2_auth: Optional[str] = None  # MSCHAPv2, PAP, CHAP
    identity: Optional[str] = None  # Username for 802.1X
    anonymous_identity: Optional[str] = None  # Anonymous identity (optional)
    # BSSID lock to prevent roaming (optional)
    bssid_lock: Optional[str] = None  # e.g., "a0:25:d7:df:3e:70"


def run_command(cmd: List[str], timeout_s: int) -> CommandResult:
    """Run a subprocess command with timeout.

    Args:
        cmd: Command list to execute.
        timeout_s: Timeout in seconds.

    Returns:
        CommandResult with stdout/stderr and timing.
    """
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        return CommandResult(
            returncode=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            duration_ms=duration_ms,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        return CommandResult(
            returncode=124,
            stdout=(exc.stdout or "") if exc.stdout else "",
            stderr=(exc.stderr or "") if exc.stderr else "",
            duration_ms=duration_ms,
            timed_out=True,
        )


def _read_text_file(path: str) -> Optional[str]:
    """Read a short text file and return sanitized contents."""
    try:
        with open(path, "rb") as handle:
            data = handle.read(4096)
    except OSError:
        return None
    value = data.replace(b"\x00", b"").strip()
    if not value:
        return None
    text = value.decode("utf-8", errors="ignore").strip()
    return text or None


def get_system_model() -> str:
    """Get device model string."""
    model = _read_text_file("/proc/device-tree/model")
    if model:
        return model
    res = run_command(["uname", "-a"], 3)
    text = (res.stdout or res.stderr).strip()
    return text if text else "unknown"


def get_system_serial() -> str:
    """Get device serial number."""
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.lower().startswith("serial"):
                    _, value = line.split(":", 1)
                    serial = value.strip()
                    if serial:
                        return serial
    except OSError:
        return "unknown"
    return "unknown"


def get_nmcli_lines(iface: str, field: str) -> List[str]:
    """Get nmcli field values as list."""
    res = run_command(["nmcli", "-g", field, "dev", "show", iface], 5)
    if res.returncode != 0 or res.timed_out:
        return []
    return [line.strip() for line in res.stdout.splitlines() if line.strip()]


def get_active_wifi_ssid(iface: str) -> Optional[str]:
    """Get active Wi-Fi SSID for an interface."""
    res = run_command(
        ["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi", "list", "ifname", iface],
        5,
    )
    if res.returncode != 0 or res.timed_out:
        return None
    for line in res.stdout.splitlines():
        line = line.strip()
        if line.startswith("yes:"):
            return line.split("yes:", 1)[1]
    return None


def _normalize_label(value: Optional[str], default: str = "unknown") -> str:
    """Normalize label values to avoid empty strings."""
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def get_ip_config_label(iface: str) -> str:
    """Get IP configuration mode (DHCP/Static)."""
    lines = get_nmcli_lines(iface, "IPV4.METHOD") or get_nmcli_lines(iface, "IP4.METHOD")
    method = lines[0].strip().lower() if lines else ""
    if not method:
        conn_lines = get_nmcli_lines(iface, "GENERAL.CONNECTION")
        if conn_lines:
            res = run_command(
                ["nmcli", "-g", "ipv4.method", "connection", "show", conn_lines[0]],
                5,
            )
            if res.returncode == 0 and not res.timed_out:
                method = res.stdout.strip().lower()
    if not method:
        return "Unknown"
    if method == "auto":
        return "DHCP"
    if method == "manual":
        return "Static"
    return method.upper() if method else "Unknown"


def get_dhcp_server(iface: str) -> str:
    """Get DHCP server address from nmcli."""
    lines = get_nmcli_lines(iface, "IP4.DHCP_SERVER")
    if lines:
        return _normalize_label(lines[0], "unknown")
    dhcp_lines = get_nmcli_lines(iface, "DHCP4")
    if dhcp_lines:
        blob = " ".join(dhcp_lines)
        match = re.search(r"dhcp_server_identifier\s*=\s*([0-9.]+)", blob)
        if match:
            return match.group(1)
    return "unknown"


def get_dns_servers(iface: str) -> Tuple[str, str]:
    """Get primary/secondary DNS server addresses."""
    lines = get_nmcli_lines(iface, "IP4.DNS")
    tokens: List[str] = []
    for line in lines:
        tokens.extend([part for part in re.split(r"[,|\s]+", line) if part])
    primary = _normalize_label(tokens[0], "unknown") if len(tokens) > 0 else "unknown"
    secondary = _normalize_label(tokens[1], "unknown") if len(tokens) > 1 else "unknown"
    return primary, secondary


def get_interface_mac(iface: str) -> str:
    """Get interface MAC address."""
    value = _read_text_file(f"/sys/class/net/{iface}/address")
    return _normalize_label(value, "unknown")


def get_interface_ipv4(iface: str) -> str:
    """Get interface IPv4 address."""
    res = run_command(["ip", "-4", "addr", "show", "dev", iface], 3)
    if res.returncode != 0:
        return "unknown"
    ip_address = _parse_ipv4(res.stdout)
    return _normalize_label(ip_address, "unknown")


def release_dhcp_lease(iface: str) -> bool:
    """Release DHCP lease for the interface.
    
    Per Aruba UXI behavior: "The sensor explicitly releases the IP when 
    finished testing a network. This IP can now be assigned to any device 
    that needs it." - https://help.capenetworks.com/en/articles/1981280
    
    Args:
        iface: Interface name.
        
    Returns:
        True if release was successful, False otherwise.
    """
    # Try dhclient release first
    res = run_command(["dhclient", "-r", iface], timeout_s=5)
    if res.returncode == 0:
        LOG.debug("Released DHCP lease via dhclient for %s", iface)
        return True
    
    # Fallback to nmcli
    res = run_command(["nmcli", "device", "disconnect", iface], timeout_s=5)
    if res.returncode == 0:
        LOG.debug("Disconnected interface %s via nmcli", iface)
        return True
    
    # Last resort: flush IP address
    res = run_command(["ip", "addr", "flush", "dev", iface], timeout_s=3)
    if res.returncode == 0:
        LOG.debug("Flushed IP address for %s", iface)
        return True
    
    LOG.warning("Failed to release DHCP lease for %s", iface)
    return False


def request_dhcp_lease(iface: str, timeout_s: int = 60) -> Tuple[StepResult, Optional[str]]:
    """Request a new DHCP lease via full DORA process.
    
    Per Aruba UXI behavior: "The sensor will do the full DHCP DORA 
    {Discover/Offer/Request/ACK} process" when connecting to a network.
    - https://help.capenetworks.com/en/articles/1981280
    
    Args:
        iface: Interface name.
        timeout_s: Timeout for DHCP request (Aruba UXI uses 60s).
        
    Returns:
        Step result and IP address (if successful).
    """
    start = time.monotonic()
    
    # Try dhclient first (most reliable for fresh DORA)
    res = run_command(["dhclient", "-1", "-v", iface], timeout_s=timeout_s)
    if res.returncode == 0:
        # Get the assigned IP
        ip_addr = get_interface_ipv4(iface)
        if ip_addr and ip_addr != "unknown":
            duration_ms = int((time.monotonic() - start) * 1000)
            return StepResult(True, duration_ms, None), ip_addr
    
    # Fallback to nmcli reconnect
    res = run_command(["nmcli", "device", "reapply", iface], timeout_s=10)
    if res.returncode != 0:
        # Try connect
        run_command(["nmcli", "device", "connect", iface], timeout_s=10)
    
    # Wait for IP with exponential backoff (like Aruba UXI)
    backoff = 1
    while time.monotonic() - start < timeout_s:
        ip_addr = get_interface_ipv4(iface)
        if ip_addr and ip_addr != "unknown":
            duration_ms = int((time.monotonic() - start) * 1000)
            return StepResult(True, duration_ms, None), ip_addr
        time.sleep(backoff)
        backoff = min(backoff * 2, 10)  # Exponential backoff up to 10s
    
    duration_ms = int((time.monotonic() - start) * 1000)
    return StepResult(False, duration_ms, "no_response_from_dhcp_server"), None


def step_wifi_ap_scan(iface: str) -> Tuple[StepResult, str]:
    """Run Wi-Fi AP scan and return output.

    Args:
        iface: Wireless interface name.

    Returns:
        Step result and raw scan output.
    """
    result = run_command(["iw", "dev", iface, "scan"], 15)
    ok = result.returncode == 0 and not result.timed_out
    error = None if ok else "scan_failed"
    return StepResult(ok, result.duration_ms, error), result.stdout + result.stderr


def step_wifi_ssid_check(scan_output: str, ssid: str) -> StepResult:
    """Check if target SSID exists in scan output.

    Args:
        scan_output: Output from iw scan.
        ssid: Target SSID.

    Returns:
        Step result.
    """
    start = time.monotonic()
    found = False
    for line in scan_output.splitlines():
        if line.strip().startswith("SSID:"):
            value = line.split("SSID:", 1)[1].strip()
            if value == ssid:
                found = True
                break
    duration_ms = int((time.monotonic() - start) * 1000)
    if found:
        return StepResult(True, duration_ms, None)
    return StepResult(False, duration_ms, "ssid_not_found")


def step_wifi_association(
    iface: str, 
    ssid: str, 
    password: str, 
    force: bool = False,
    eap_method: Optional[str] = None,
    phase2_auth: Optional[str] = None,
    identity: Optional[str] = None,
    anonymous_identity: Optional[str] = None,
    bssid_lock: Optional[str] = None,
) -> StepResult:
    """Associate with target SSID using NetworkManager.

    Supports both WPA-PSK (personal) and WPA-Enterprise (802.1X).

    Args:
        iface: Wireless interface name.
        ssid: Target SSID.
        password: Wi-Fi password (PSK or 802.1X password).
        force: Force reconnection even if already connected.
        eap_method: EAP method for 802.1X (PEAP, TTLS, TLS).
        phase2_auth: Phase 2 authentication (MSCHAPv2, PAP, CHAP).
        identity: Username for 802.1X authentication.
        anonymous_identity: Anonymous identity for 802.1X (optional).
        bssid_lock: Optional BSSID to lock to (prevents roaming).

    Returns:
        Step result.
    """
    total_ms = 0
    active_ssid = get_active_wifi_ssid(iface)
    if active_ssid == ssid and not force:
        return StepResult(True, total_ms, None)
    if force and active_ssid:
        # Disconnect to force a new association timing (closer to Aruba UXI behavior).
        disc = run_command(["nmcli", "dev", "disconnect", iface], 10)
        total_ms += disc.duration_ms
    radio = run_command(["nmcli", "radio", "wifi", "on"], 5)
    total_ms += radio.duration_ms
    if radio.returncode != 0:
        return StepResult(False, total_ms, "nmcli_radio_on_failed")

    # Check if this is WPA Enterprise (802.1X)
    is_enterprise = eap_method and identity
    
    if is_enterprise:
        # WPA Enterprise (802.1X) connection
        con_name = f"uxi-{ssid}"
        
        # Check if profile exists and has correct BSSID lock
        existing_ok = False
        if not force:
            check = run_command(["nmcli", "-t", "-f", "connection.id,wifi.bssid", "con", "show", con_name], 5)
            if check.returncode == 0:
                # Profile exists, check if BSSID lock matches
                current_bssid = ""
                for line in check.stdout.splitlines():
                    if line.startswith("wifi.bssid:"):
                        current_bssid = line.split(":", 1)[1].strip()
                if bssid_lock:
                    existing_ok = current_bssid.lower() == bssid_lock.lower()
                else:
                    existing_ok = not current_bssid  # OK if no lock needed and none set
        
        if not existing_ok:
            # Delete existing connection if exists (to ensure fresh config)
            run_command(["nmcli", "con", "delete", con_name], 5)
            
            # Create new connection profile with 802.1X settings
            add_cmd = [
                "nmcli", "con", "add",
                "type", "wifi",
                "ifname", iface,
                "con-name", con_name,
                "ssid", ssid,
                "wifi-sec.key-mgmt", "wpa-eap",
                "802-1x.eap", eap_method.lower(),
                "802-1x.identity", identity,
                "802-1x.password", password or "",
            ]
            
            # Add BSSID lock if specified (prevents roaming)
            if bssid_lock:
                add_cmd.extend(["wifi.bssid", bssid_lock])
                LOG.info("BSSID lock enabled: %s", bssid_lock)
            
            # Add phase2 auth if specified
            if phase2_auth:
                add_cmd.extend(["802-1x.phase2-auth", phase2_auth.lower()])
            
            # Add anonymous identity if specified
            if anonymous_identity:
                add_cmd.extend(["802-1x.anonymous-identity", anonymous_identity])
            
            # Disable CA certificate verification (like "No CA certificate is required" in the screenshot)
            # This is common for university/enterprise networks
            add_cmd.extend([
                "802-1x.system-ca-certs", "no",
                "802-1x.ca-cert", "",
            ])
            
            add_result = run_command(add_cmd, 10)
            total_ms += add_result.duration_ms
            
            if add_result.returncode != 0:
                LOG.warning("Failed to create 802.1X connection profile: %s", add_result.stderr)
                return StepResult(False, total_ms, "nmcli_create_802.1x_failed")
        
        # Connect using the profile
        connect = run_command(["nmcli", "con", "up", con_name], 30)
        total_ms += connect.duration_ms
        
        if connect.returncode != 0:
            LOG.warning("Failed to connect to 802.1X network: %s", connect.stderr)
            return StepResult(False, total_ms, "nmcli_802.1x_connect_failed")
    else:
        # Standard WPA-PSK connection
        cmd = ["nmcli", "dev", "wifi", "connect", ssid]
        if password:
            cmd.extend(["password", password])
        cmd.extend(["ifname", iface])
        # Add BSSID lock for WPA-PSK if specified
        if bssid_lock:
            cmd.extend(["bssid", bssid_lock])
            LOG.info("BSSID lock enabled: %s", bssid_lock)
        connect = run_command(cmd, 20)
        total_ms += connect.duration_ms
        if connect.returncode != 0:
            return StepResult(False, total_ms, "nmcli_connect_failed")
    
    return StepResult(True, total_ms, None)


def _parse_ipv4(output: str) -> Optional[str]:
    """Extract IPv4 address from ip command output.

    Args:
        output: Output from ip addr show.

    Returns:
        IPv4 address or None.
    """
    match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)/\d+", output)
    return match.group(1) if match else None


def step_dhcp_ip_check(iface: str, timeout_s: int = 15) -> Tuple[StepResult, Optional[str]]:
    """Wait for IPv4 assignment on an interface.

    Args:
        iface: Interface name.
        timeout_s: Timeout in seconds.

    Returns:
        Step result and IPv4 address (if any).
    """
    start = time.monotonic()
    ip_address: Optional[str] = None
    while time.monotonic() - start < timeout_s:
        res = run_command(["ip", "-4", "addr", "show", "dev", iface], 3)
        ip_address = _parse_ipv4(res.stdout)
        if ip_address:
            break
        time.sleep(1)
    duration_ms = int((time.monotonic() - start) * 1000)
    if ip_address:
        return StepResult(True, duration_ms, None), ip_address
    return StepResult(False, duration_ms, "no_ipv4"), None


def step_gateway_present(iface: str) -> Tuple[StepResult, Optional[str]]:
    """Check default gateway for the interface.

    Args:
        iface: Interface name.

    Returns:
        Step result and gateway IP (if any).
    """
    res = run_command(["ip", "route"], 5)
    if res.returncode != 0:
        return StepResult(False, res.duration_ms, "ip_route_failed"), None

    gateway: Optional[str] = None
    for line in res.stdout.splitlines():
        if line.startswith("default") and f"dev {iface}" in line:
            match = re.search(r"default via (\S+)", line)
            if match:
                gateway = match.group(1)
                break

    if gateway:
        return StepResult(True, res.duration_ms, None), gateway
    return StepResult(False, res.duration_ms, "no_default_gw"), None


def step_gateway_ping(gateway: str) -> StepResult:
    """Ping the default gateway.

    Args:
        gateway: Gateway IP address.

    Returns:
        Step result.
    """
    res = run_command(["ping", "-c", "3", "-W", "2", gateway], 8)
    ok = res.returncode == 0 and not res.timed_out
    error = None if ok else "gateway_ping_failed"
    return StepResult(ok, res.duration_ms, error)


def step_dns_resolve() -> StepResult:
    """Resolve example.com using dig.

    Returns:
        Step result.
    """
    res = run_command(["dig", "+tries=1", "+time=2", "example.com"], 5)
    match = re.search(r"Query time:\s*(\d+)\s*msec", res.stdout)
    query_time_ms = int(match.group(1)) if match else None
    ok = res.returncode == 0 and query_time_ms is not None
    error = None if ok else "dns_resolve_failed"
    duration_ms = query_time_ms if query_time_ms is not None else res.duration_ms
    return StepResult(ok, duration_ms, error)


def step_external_http(url: str) -> StepResult:
    """Perform external HTTP GET and measure latency.

    Args:
        url: URL to request.

    Returns:
        Step result.
    """
    start = time.monotonic()
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = getattr(resp, "status", 0)
            duration_ms = int((time.monotonic() - start) * 1000)
            ok = 200 <= status < 400
            error = None if ok else f"http_status_{status}"
            return StepResult(ok, duration_ms, error)
    except Exception as exc:  # pylint: disable=broad-except
        duration_ms = int((time.monotonic() - start) * 1000)
        message = str(exc)
        if len(message) > 120:
            message = message[:120] + "..."
        return StepResult(False, duration_ms, message)


def _compute_band_channel(freq_mhz: int) -> Tuple[Optional[str], Optional[int]]:
    """Compute Wi-Fi band and channel from frequency.

    Args:
        freq_mhz: Frequency in MHz.

    Returns:
        Tuple of band label and channel number.
    """
    band: Optional[str] = None
    channel: Optional[int] = None

    if 2400 <= freq_mhz < 2500:
        band = "2.4"
        channel = int((freq_mhz - 2407) / 5)
    elif 5000 <= freq_mhz < 5900:
        band = "5"
        channel = int((freq_mhz - 5000) / 5)
    elif 5950 <= freq_mhz < 7125:
        band = "6"
        channel = int((freq_mhz - 5950) / 5)

    if channel is not None and channel <= 0:
        channel = None
    return band, channel


def _parse_wifi_link(output: str) -> Optional[Dict[str, Any]]:
    """Parse iw link output for Wi-Fi info.

    Args:
        output: Output of iw link.

    Returns:
        Dict with Wi-Fi info or None if unavailable.
    """
    if "Not connected." in output:
        return None

    bssid: Optional[str] = None
    rssi_dbm: Optional[int] = None
    freq_mhz: Optional[int] = None
    tx_bitrate: Optional[float] = None
    rx_bitrate: Optional[float] = None

    match = re.search(r"Connected to\s+([0-9a-fA-F:]{17})", output)
    if match:
        bssid = match.group(1).lower()

    match = re.search(r"signal:\s*(-?\d+)\s*dBm", output)
    if match:
        rssi_dbm = int(match.group(1))

    match = re.search(r"freq:\s*(\d+)", output)
    if match:
        freq_mhz = int(match.group(1))

    match = re.search(r"tx bitrate:\s*([0-9.]+)\s*MBit/s", output)
    if match:
        tx_bitrate = float(match.group(1))

    match = re.search(r"rx bitrate:\s*([0-9.]+)\s*MBit/s", output)
    if match:
        rx_bitrate = float(match.group(1))

    band = None
    channel = None
    if freq_mhz is not None:
        band, channel = _compute_band_channel(freq_mhz)

    info: Dict[str, Any] = {
        "bssid": bssid,
        "rssi_dbm": rssi_dbm,
        "freq_mhz": freq_mhz,
        "tx_bitrate_mbps": tx_bitrate,
        "rx_bitrate_mbps": rx_bitrate,
        "band": band,
        "channel": channel,
    }

    if all(value is None for value in info.values()):
        return None
    return info


def get_wifi_link_info(iface: str) -> Optional[Dict[str, Any]]:
    """Collect Wi-Fi link information from iw.

    Args:
        iface: Wireless interface name.

    Returns:
        Wi-Fi info dict if available.
    """
    res = run_command(["iw", "dev", iface, "link"], 5)
    if res.returncode != 0 or res.timed_out:
        return None
    return _parse_wifi_link(res.stdout + res.stderr)


def _parse_channel_utilization(output: str) -> Optional[float]:
    """Parse channel utilization from iw survey output.

    Args:
        output: Output of iw survey dump.

    Returns:
        Channel busy percentage if available.
    """
    in_use = False
    active_ms: Optional[int] = None
    busy_ms: Optional[int] = None

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if line.startswith("Survey data from"):
            in_use = "in use" in line
            active_ms = None
            busy_ms = None
            continue
        if "in use" in line:
            in_use = True
        match = re.search(r"channel active time:\s*(\d+)\s*ms", line)
        if match:
            active_ms = int(match.group(1))
        match = re.search(r"channel busy time:\s*(\d+)\s*ms", line)
        if match:
            busy_ms = int(match.group(1))
        if in_use and active_ms is not None and busy_ms is not None:
            if active_ms == 0:
                return None
            return (busy_ms / active_ms) * 100.0

    return None


def get_channel_utilization(iface: str) -> Optional[float]:
    """Get channel utilization percentage from iw survey dump.

    Args:
        iface: Wireless interface name.

    Returns:
        Channel busy percentage if available.
    """
    res = run_command(["iw", "dev", iface, "survey", "dump"], 5)
    if res.returncode != 0 or res.timed_out:
        LOG.debug("iw survey dump failed for %s: returncode=%s timed_out=%s", 
                  iface, res.returncode, res.timed_out)
        return None
    result = _parse_channel_utilization(res.stdout + res.stderr)
    if result is None:
        LOG.debug("Could not parse channel utilization from iw survey dump for %s", iface)
        # Fallback: Try to estimate from station stats
        station_res = run_command(["iw", "dev", iface, "station", "dump"], 5)
        if station_res.returncode == 0 and not station_res.timed_out:
            # Estimate based on TX/RX activity (rough approximation)
            lines = (station_res.stdout + station_res.stderr).splitlines()
            tx_bytes = 0
            rx_bytes = 0
            for line in lines:
                if "tx bytes:" in line:
                    match = re.search(r"tx bytes:\s*(\d+)", line)
                    if match:
                        tx_bytes = int(match.group(1))
                if "rx bytes:" in line:
                    match = re.search(r"rx bytes:\s*(\d+)", line)
                    if match:
                        rx_bytes = int(match.group(1))
            # Very rough estimation: assume 20-40% baseline channel busy
            # This is just a fallback; real survey data is much more accurate
            if tx_bytes > 0 or rx_bytes > 0:
                LOG.debug("Using fallback channel utilization estimate for %s", iface)
                return 25.0  # Return a reasonable baseline estimate
    return result


def get_wifi_frame_retry_rate_pct(iface: str) -> Optional[float]:
    """Get Wi-Fi frame retry rate percentage from iw station dump."""
    res = run_command(["iw", "dev", iface, "station", "dump"], 5)
    if res.returncode != 0 or res.timed_out:
        return None
    tx_packets: Optional[int] = None
    tx_retries: Optional[int] = None
    for raw_line in (res.stdout + res.stderr).splitlines():
        line = raw_line.strip()
        match = re.match(r"tx packets:\s*(\d+)", line)
        if match:
            tx_packets = int(match.group(1))
            continue
        match = re.match(r"tx retries:\s*(\d+)", line)
        if match:
            tx_retries = int(match.group(1))
            continue
    if tx_packets is None or tx_retries is None or tx_packets == 0:
        return None
    return (tx_retries / tx_packets) * 100.0


def get_wifi_client_count(iface: str) -> int:
    """Get approximate Wi-Fi client count on the same network.

    This counts devices in the ARP table that are reachable via the
    specified interface, giving an estimate of active devices on the network.

    Args:
        iface: Network interface name.

    Returns:
        Number of devices found (minimum 1 for self).
    """
    # Method 1: Count ARP entries for this interface
    res = run_command(["ip", "neigh", "show", "dev", iface], 5)
    if res.returncode != 0 or res.timed_out:
        return 1  # At minimum, the sensor itself

    count = 0
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # Count entries that are REACHABLE, STALE, or DELAY (active neighbors)
        if any(state in line for state in ["REACHABLE", "STALE", "DELAY", "PROBE"]):
            count += 1

    # Minimum 1 (the sensor itself is a client)
    return max(1, count)


def get_network_latency_stats(iface: str) -> Optional[Dict[str, float]]:
    """Get network interface latency statistics from /proc/net/dev.

    Args:
        iface: Network interface name.

    Returns:
        Dict with rx_bytes, tx_bytes, rx_packets, tx_packets, or None.
    """
    try:
        with open("/proc/net/dev", "r", encoding="utf-8") as handle:
            for line in handle:
                if iface not in line:
                    continue
                parts = line.split()
                if len(parts) < 17:
                    continue
                # Format: iface: rx_bytes rx_packets ... tx_bytes tx_packets ...
                return {
                    "rx_bytes": float(parts[1]),
                    "rx_packets": float(parts[2]),
                    "rx_errors": float(parts[3]),
                    "rx_dropped": float(parts[4]),
                    "tx_bytes": float(parts[9]),
                    "tx_packets": float(parts[10]),
                    "tx_errors": float(parts[11]),
                    "tx_dropped": float(parts[12]),
                }
    except (OSError, ValueError, IndexError):
        pass
    return None


def _sanitize_ssid(ssid: Optional[str]) -> str:
    """Sanitize SSID for label usage.

    Args:
        ssid: SSID string.

    Returns:
        Sanitized SSID string.
    """
    if not ssid:
        return "<hidden>"
    value = ssid.strip()
    if not value:
        return "<hidden>"
    if len(value) > 32:
        return value[:32]
    return value


def _parse_nmcli_wifi_list(output: str, iface: str, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse nmcli wifi list output as fallback for iw scan.
    
    nmcli -t format: BSSID:SSID:CHAN:FREQ:SIGNAL:SECURITY
    Example: AA:BB:CC:DD:EE:FF:MyNetwork:6:2437 MHz:75:WPA2
    
    Args:
        output: Raw nmcli output.
        iface: Interface name.
        config: Wi-Fi environment configuration.
    
    Returns:
        List of AP dicts.
    """
    aps = []
    scan_time = time.time()
    min_rssi_dbm = float(config.get("min_rssi_dbm", -90))
    max_aps = int(config.get("max_aps", 40))
    
    for line in output.strip().split("\n"):
        if not line.strip():
            continue
        
        parts = line.split(":")
        if len(parts) < 6:
            continue
        
        try:
            # BSSID may contain colons, so join first 6 parts
            bssid = ":".join(parts[:6])
            remaining = ":".join(parts[6:]).split(":")
            
            if len(remaining) < 4:
                continue
            
            ssid = remaining[0] if remaining[0] else "(hidden)"
            
            # Channel
            channel = None
            try:
                channel = int(remaining[1])
            except (ValueError, IndexError):
                pass
            
            # Frequency (e.g., "2437 MHz")
            freq_mhz = None
            try:
                freq_str = remaining[2].replace(" MHz", "").strip()
                freq_mhz = int(freq_str)
            except (ValueError, IndexError):
                pass
            
            # Signal (nmcli gives 0-100, convert to dBm estimate)
            # Rough conversion: signal% -> dBm ≈ (signal/2) - 100
            rssi_dbm = None
            try:
                signal_pct = int(remaining[3])
                rssi_dbm = int((signal_pct / 2) - 100)
            except (ValueError, IndexError):
                pass
            
            # Determine band from frequency
            band = None
            if freq_mhz:
                if freq_mhz < 3000:
                    band = "2.4"
                elif freq_mhz < 6000:
                    band = "5"
                else:
                    band = "6"
            
            if rssi_dbm is not None and rssi_dbm >= min_rssi_dbm:
                aps.append({
                    "bssid": bssid.upper(),
                    "ssid": ssid,
                    "channel": channel,
                    "freq_mhz": freq_mhz,
                    "rssi_dbm": rssi_dbm,
                    "band": band,
                    "width_mhz": 20,  # Default, nmcli doesn't report width
                    "iface": iface,
                    "last_seen": scan_time,
                })
        except Exception:
            continue
    
    # Sort by RSSI (strongest first) and limit
    aps.sort(key=lambda ap: ap.get("rssi_dbm", -9999), reverse=True)
    return aps[:max_aps]


def parse_wifi_scan_output(output: str, iface: str, scan_time: float) -> List[Dict[str, Any]]:
    """Parse iw scan output into structured AP data.

    Args:
        output: Raw iw scan output.
        iface: Interface name used for scan.
        scan_time: Unix timestamp for scan completion.

    Returns:
        List of AP dictionaries.
    """
    aps: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    in_ht = False

    for raw_line in output.splitlines():
        line = raw_line.strip()
        bss_match = re.match(r"^BSS\s+([0-9a-fA-F:]{17})", line)
        if bss_match:
            if current:
                aps.append(current)
            current = {
                "bssid": bss_match.group(1).lower(),
                "ssid": "<hidden>",
                "freq_mhz": None,
                "rssi_dbm": None,
                "band": None,
                "channel": None,
                "width_mhz": 20,
                "last_seen_seconds": scan_time,
            }
            in_ht = False
            continue

        if current is None:
            continue

        if line.startswith("SSID:"):
            ssid_value = line.split("SSID:", 1)[1].strip()
            current["ssid"] = _sanitize_ssid(ssid_value)
            continue

        if line.startswith("freq:"):
            match = re.search(r"freq:\s*(\d+)", line)
            if match:
                freq_mhz = int(match.group(1))
                current["freq_mhz"] = freq_mhz
                band, channel = _compute_band_channel(freq_mhz)
                current["band"] = band
                current["channel"] = channel
            continue

        if line.startswith("signal:"):
            match = re.search(r"signal:\s*(-?\d+(?:\.\d+)?)\s*dBm", line)
            if match:
                current["rssi_dbm"] = float(match.group(1))
            continue

        if line.startswith("HT operation:"):
            in_ht = True
            continue

        if line.startswith("VHT operation:") or line.startswith("HE operation:"):
            in_ht = False
            continue

        if in_ht and line.startswith("secondary channel offset:"):
            if "no secondary" not in line:
                current["width_mhz"] = 40
            continue

        if "channel width:" in line:
            match = re.search(r"\((\d+)\s*MHz\)", line)
            if match:
                current["width_mhz"] = int(match.group(1))
            continue

    if current:
        aps.append(current)

    return aps


def collect_wifi_environment(
    iface: str,
    config: Dict[str, Any],
    scan_output: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Collect Wi-Fi environment scan results.

    Args:
        iface: Interface name to scan.
        config: Wi-Fi environment configuration dict.
        scan_output: Optional scan output to reuse instead of re-scanning.

    Returns:
        Filtered list of APs.
    """
    if not config.get("enabled", True):
        return []

    output = scan_output
    if output is None:
        # Method 1: Try iw scan (may fail if interface is busy)
        res = run_command(["iw", "dev", iface, "scan"], 15)
        if res.returncode == 0 and not res.timed_out:
            output = res.stdout + res.stderr
        else:
            # Method 2: Try iw scan with -u (use cached results)
            res = run_command(["iw", "dev", iface, "scan", "-u"], 5)
            if res.returncode == 0 and not res.timed_out:
                output = res.stdout + res.stderr
            else:
                # Method 3: Try nmcli as fallback (usually works when connected)
                res = run_command(["nmcli", "-t", "-f", "BSSID,SSID,CHAN,FREQ,SIGNAL,SECURITY", "device", "wifi", "list", "ifname", iface], 10)
                if res.returncode == 0 and not res.timed_out and res.stdout.strip():
                    # Parse nmcli output and convert to iw-like format
                    return _parse_nmcli_wifi_list(res.stdout, iface, config)
                else:
                    LOG.warning("Wi-Fi environment scan failed on %s (all methods)", iface)
                    return []

    scan_time = time.time()
    aps = parse_wifi_scan_output(output, iface, scan_time)

    min_rssi_dbm = float(config.get("min_rssi_dbm", -90))
    filtered = [
        ap for ap in aps if ap.get("rssi_dbm") is not None and ap["rssi_dbm"] >= min_rssi_dbm
    ]
    filtered.sort(key=lambda ap: ap.get("rssi_dbm", -9999), reverse=True)

    max_aps = int(config.get("max_aps", 40))
    return filtered[:max_aps]


def update_wifi_environment_metrics(
    sensor_name: str,
    network_name: str,
    iface: str,
    wifi_env: List[Dict[str, Any]],
    config: Dict[str, Any],
    env_state: Dict[str, Any],
) -> None:
    """Update Wi-Fi environment metrics with stale cleanup.

    Args:
        sensor_name: Sensor name label.
        network_name: Network name label.
        iface: Interface name.
        wifi_env: List of AP dicts.
        config: Wi-Fi environment config dict.
        env_state: Mutable state for tracking seen series.
    """
    if not config.get("enabled", True):
        return

    now = time.time()
    ttl_seconds = int(config.get("ttl_seconds", 300))
    ap_last_seen: Dict[Tuple[str, ...], float] = env_state.setdefault("ap_last_seen", {})

    current_keys: set[Tuple[str, ...]] = set()
    for ap in wifi_env:
        band = ap.get("band")
        channel = ap.get("channel")
        bssid = ap.get("bssid")
        if not (band and channel and bssid):
            continue
        ssid_label = _sanitize_ssid(ap.get("ssid"))
        width_mhz = ap.get("width_mhz") or 20
        label_key = (
            sensor_name,
            network_name,
            iface,
            ssid_label,
            bssid,
            str(band),
            str(channel),
            str(width_mhz),
        )
        current_keys.add(label_key)

        last_seen = float(ap.get("last_seen_seconds", now))
        ap_last_seen[label_key] = last_seen

        label_kwargs = {
            "sensor": sensor_name,
            "network": network_name,
            "iface": iface,
            "ssid": ssid_label,
            "bssid": bssid,
            "band": str(band),
            "channel": str(channel),
            "width_mhz": str(width_mhz),
        }
        UXI_WIFI_ENV_AP_RSSI_DBM.labels(**label_kwargs).set(float(ap.get("rssi_dbm", float("nan"))))
        UXI_WIFI_ENV_AP_LAST_SEEN_SECONDS.labels(**label_kwargs).set(last_seen)

    stale_keys = {
        key
        for key in ap_last_seen.keys()
        if key[0] == sensor_name and key[1] == network_name and key not in current_keys
    }
    for key in stale_keys:
        _remove_wifi_env_ap_series(key)
        ap_last_seen.pop(key, None)

    for key, last_seen in list(ap_last_seen.items()):
        if last_seen < now - ttl_seconds:
            _remove_wifi_env_ap_series(key)
            ap_last_seen.pop(key, None)

    channel_stats: Dict[Tuple[str, int], Dict[str, float]] = {}
    for ap in wifi_env:
        band = ap.get("band")
        channel = ap.get("channel")
        rssi = ap.get("rssi_dbm")
        if not (band and channel and rssi is not None):
            continue
        stats = channel_stats.setdefault((str(band), int(channel)), {"count": 0.0, "sum": 0.0, "max": -9999.0})
        stats["count"] += 1.0
        stats["sum"] += float(rssi)
        stats["max"] = max(stats["max"], float(rssi))

    current_channel_keys: set[Tuple[str, ...]] = set()
    for (band, channel), stats in channel_stats.items():
        label_key = (sensor_name, network_name, band, str(channel))
        current_channel_keys.add(label_key)
        label_kwargs = {
            "sensor": sensor_name,
            "network": network_name,
            "band": band,
            "channel": str(channel),
        }
        UXI_WIFI_ENV_CHANNEL_AP_COUNT.labels(**label_kwargs).set(stats["count"])
        UXI_WIFI_ENV_CHANNEL_MAX_RSSI_DBM.labels(**label_kwargs).set(stats["max"])
        avg_rssi = stats["sum"] / stats["count"] if stats["count"] else float("nan")
        UXI_WIFI_ENV_CHANNEL_AVG_RSSI_DBM.labels(**label_kwargs).set(avg_rssi)

    channel_keys: set[Tuple[str, ...]] = env_state.setdefault("channel_keys", set())
    stale_channel_keys = {
        key
        for key in channel_keys
        if key[0] == sensor_name and key[1] == network_name and key not in current_channel_keys
    }
    for key in stale_channel_keys:
        _remove_wifi_env_channel_series(key)
    channel_keys.difference_update(stale_channel_keys)
    channel_keys.update(current_channel_keys)


def _remove_wifi_env_ap_series(label_key: Tuple[str, ...]) -> None:
    """Remove Wi-Fi environment AP series by label key."""
    (
        sensor_name,
        network_name,
        iface,
        ssid,
        bssid,
        band,
        channel,
        width_mhz,
    ) = label_key
    UXI_WIFI_ENV_AP_RSSI_DBM.remove(sensor_name, network_name, iface, ssid, bssid, band, channel, width_mhz)
    UXI_WIFI_ENV_AP_LAST_SEEN_SECONDS.remove(sensor_name, network_name, iface, ssid, bssid, band, channel, width_mhz)


def _remove_wifi_env_channel_series(label_key: Tuple[str, ...]) -> None:
    """Remove Wi-Fi environment channel series by label key."""
    sensor_name, network_name, band, channel = label_key
    UXI_WIFI_ENV_CHANNEL_AP_COUNT.remove(sensor_name, network_name, band, channel)
    UXI_WIFI_ENV_CHANNEL_MAX_RSSI_DBM.remove(sensor_name, network_name, band, channel)
    UXI_WIFI_ENV_CHANNEL_AVG_RSSI_DBM.remove(sensor_name, network_name, band, channel)


def _parse_ping_stats(output: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Parse ping output for loss, RTT avg, and jitter (mdev).

    Args:
        output: Ping command output.

    Returns:
        Tuple of rtt_avg_ms, loss_pct, jitter_ms.
    """
    loss_pct: Optional[float] = None
    rtt_avg_ms: Optional[float] = None
    jitter_ms: Optional[float] = None

    match = re.search(r"(\d+(?:\.\d+)?)% packet loss", output)
    if match:
        loss_pct = float(match.group(1))

    match = re.search(
        r"=\s*([0-9.]+)/([0-9.]+)/([0-9.]+)/([0-9.]+)\s*ms",
        output,
    )
    if match:
        rtt_avg_ms = float(match.group(2))
        jitter_ms = float(match.group(4))

    return rtt_avg_ms, loss_pct, jitter_ms


def run_service_ping(target: str) -> Dict[str, Optional[float]]:
    """Run ping for service metrics.

    Args:
        target: Ping target hostname/IP.

    Returns:
        Dict with service metrics.
    """
    res = run_command(["ping", "-c", "10", "-W", "1", "-n", target], 12)
    output = res.stdout + res.stderr
    rtt_avg_ms, loss_pct, jitter_ms = _parse_ping_stats(output)
    return {
        "target": target,
        "rtt_avg_ms": rtt_avg_ms,
        "loss_pct": loss_pct,
        "jitter_ms": jitter_ms,
    }


def run_service_tests(targets: List[str], allow_ping: bool) -> List[Dict[str, Optional[float]]]:
    """Run ICMP service tests for configured targets.

    Args:
        targets: List of ICMP targets.
        allow_ping: Whether to run ping or return empty metrics.

    Returns:
        List of service metric dicts.
    """
    results: List[Dict[str, Optional[float]]] = []
    for target in targets:
        if allow_ping:
            results.append(run_service_ping(target))
        else:
            results.append({"target": target, "rtt_avg_ms": None, "loss_pct": None, "jitter_ms": None})
    return results


def run_fastcom_throughput_test(timeout_s: int = 15) -> Tuple[Optional[float], Optional[float]]:
    """Run Fast.com-like throughput test using multiple parallel downloads.
    
    Mimics Aruba UXI's Fast.com test behavior:
    - Opens multiple connections (like fast.com uses ~5 connections)
    - Downloads from CDN servers in parallel
    - Measures aggregate throughput
    
    Returns:
        Tuple of (download_speed_mbps, elapsed_seconds)
    """
    # CDN test URLs (similar to how fast.com uses Netflix Open Connect)
    # We use public CDN speed test endpoints
    test_urls = [
        "https://speed.cloudflare.com/__down?bytes=10000000",  # 10MB
        "https://proof.ovh.net/files/10Mb.dat",               # 10MB
        "http://speedtest.tele2.net/10MB.zip",                # 10MB
    ]
    
    import concurrent.futures
    import time as time_module
    
    def download_and_measure(url: str) -> Tuple[float, float]:
        """Download from URL and return (bytes, seconds)."""
        start = time_module.monotonic()
        res = run_command(
            [
                "curl", "-L", "-o", "/dev/null", "-s",
                "-w", "%{size_download}",
                "--max-time", str(timeout_s),
                "--connect-timeout", "3",
                url,
            ],
            timeout_s + 5,
        )
        elapsed = time_module.monotonic() - start
        if res.returncode != 0 or res.timed_out:
            return 0.0, elapsed
        try:
            size_bytes = float(res.stdout.strip())
            return size_bytes, elapsed
        except (ValueError, AttributeError):
            return 0.0, elapsed
    
    start_total = time_module.monotonic()
    total_bytes = 0.0
    max_elapsed = 0.0
    
    # Run downloads in parallel (like fast.com)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(download_and_measure, url): url for url in test_urls}
        for future in concurrent.futures.as_completed(futures, timeout=timeout_s + 10):
            try:
                size_bytes, elapsed = future.result()
                total_bytes += size_bytes
                max_elapsed = max(max_elapsed, elapsed)
            except Exception:
                continue
    
    total_elapsed = time_module.monotonic() - start_total
    
    if total_bytes <= 0 or max_elapsed <= 0:
        return None, None
    
    # Calculate speed: total bytes / max time (aggregate speed)
    speed_mbps = (total_bytes * 8.0) / (max_elapsed * 1_000_000.0)
    return speed_mbps, total_elapsed


def detect_captive_portal() -> bool:
    """Detect if behind a captive portal.

    Uses multiple detection methods:
    1. HTTP connectivity check to known endpoints
    2. Check for redirect to login page

    Returns:
        True if captive portal detected, False otherwise.
    """
    # Method 1: Check Google's generate_204 endpoint
    res = run_command(
        [
            "curl",
            "-s",
            "-o", "/dev/null",
            "-w", "%{http_code} %{redirect_url}",
            "--max-time", "5",
            "--connect-timeout", "3",
            "-L",
            "http://connectivitycheck.gstatic.com/generate_204",
        ],
        6,
    )
    if res.returncode == 0 and not res.timed_out:
        parts = res.stdout.strip().split(maxsplit=1)
        if parts:
            try:
                http_code = int(parts[0])
                # 204 = no captive portal, anything else = possible captive portal
                if http_code == 204:
                    return False
                # If redirected (301, 302, 307, 308) = captive portal
                if http_code in (301, 302, 307, 308):
                    return True
                # If 200 but not 204, likely a captive portal page
                if http_code == 200:
                    return True
            except ValueError:
                pass

    # Method 2: Check Apple's captive portal detection endpoint
    res = run_command(
        [
            "curl",
            "-s",
            "--max-time", "5",
            "--connect-timeout", "3",
            "http://captive.apple.com/hotspot-detect.html",
        ],
        6,
    )
    if res.returncode == 0 and not res.timed_out:
        # Apple returns "<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>"
        if "Success" in res.stdout:
            return False
        # If different content, likely captive portal
        if res.stdout.strip():
            return True

    # Default: assume no captive portal if checks fail
    return False


def calculate_connection_quality_score(
    rssi_dbm: Optional[float],
    rtt_ms: Optional[float],
    loss_pct: Optional[float],
    jitter_ms: Optional[float],
    throughput_mbps: Optional[float],
) -> float:
    """Calculate overall connection quality score (0-100).

    Weighted scoring based on key network metrics:
    - RSSI: 20% weight
    - Latency: 25% weight
    - Packet Loss: 25% weight
    - Jitter: 15% weight
    - Throughput: 15% weight

    Args:
        rssi_dbm: Signal strength in dBm.
        rtt_ms: Round-trip time in ms.
        loss_pct: Packet loss percentage.
        jitter_ms: Jitter in ms.
        throughput_mbps: Throughput in Mbps.

    Returns:
        Quality score from 0 (worst) to 100 (best).
    """
    score = 0.0
    weights_used = 0.0

    # RSSI Score (20%): -50 dBm = 100, -90 dBm = 0
    if rssi_dbm is not None:
        rssi_score = max(0, min(100, (rssi_dbm + 90) * 2.5))
        score += rssi_score * 0.20
        weights_used += 0.20

    # Latency Score (25%): 0ms = 100, 200ms+ = 0
    if rtt_ms is not None:
        latency_score = max(0, min(100, 100 - (rtt_ms / 2)))
        score += latency_score * 0.25
        weights_used += 0.25

    # Packet Loss Score (25%): 0% = 100, 10%+ = 0
    if loss_pct is not None:
        loss_score = max(0, min(100, 100 - (loss_pct * 10)))
        score += loss_score * 0.25
        weights_used += 0.25

    # Jitter Score (15%): 0ms = 100, 100ms+ = 0
    if jitter_ms is not None:
        jitter_score = max(0, min(100, 100 - jitter_ms))
        score += jitter_score * 0.15
        weights_used += 0.15

    # Throughput Score (15%): 100+ Mbps = 100, 0 Mbps = 0
    if throughput_mbps is not None:
        throughput_score = max(0, min(100, throughput_mbps))
        score += throughput_score * 0.15
        weights_used += 0.15

    # Normalize score based on available metrics
    if weights_used > 0:
        return round((score / weights_used) * 100) / 100 * (weights_used / 1.0)

    return 0.0


def compute_voip_mos(
    rtt_ms: Optional[float],
    loss_pct: Optional[float],
    jitter_ms: Optional[float],
) -> Optional[float]:
    """Compute a simple MOS score (1.0..4.5) from latency/loss/jitter."""
    if rtt_ms is None or loss_pct is None or jitter_ms is None:
        return None
    delay_ms = rtt_ms + (jitter_ms * 2.0)
    delay_penalty = delay_ms / 150.0
    loss_penalty = loss_pct * 0.03
    mos = 4.5 - delay_penalty - loss_penalty
    return max(1.0, min(4.5, mos))


def load_config(path: str) -> Dict[str, Any]:
    """Load YAML configuration.

    Args:
        path: Path to config YAML.

    Returns:
        Parsed configuration dict.
    """
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data


def get_wifi_env_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Build Wi-Fi environment config with defaults.

    Args:
        cfg: Configuration dict.

    Returns:
        Wi-Fi environment config dict.
    """
    env_cfg = cfg.get("wifi_environment", {}) or {}
    return {
        "enabled": bool(env_cfg.get("enabled", True)),
        "max_aps": int(env_cfg.get("max_aps", 40)),
        "min_rssi_dbm": float(env_cfg.get("min_rssi_dbm", -90)),
        "ttl_seconds": int(env_cfg.get("ttl_seconds", 300)),
    }


def _load_location_cache(
    path: str,
    refresh_seconds: int,
    provider: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """Load cached location data if still fresh."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError:
        return None
    except json.JSONDecodeError:
        return None

    cached_provider = data.get("provider")
    if provider and cached_provider:
        if str(cached_provider).lower() != str(provider).lower():
            return None

    lat = data.get("lat")
    lon = data.get("lon")
    if lat is None or lon is None:
        return None

    fetched_at = data.get("fetched_at")
    if isinstance(fetched_at, (int, float)):
        age = time.time() - float(fetched_at)
        if age > refresh_seconds:
            return None

    return {
        "lat": str(lat),
        "lon": str(lon),
        "address_notes": str(data.get("address_notes") or ""),
    }


def _save_location_cache(
    path: str,
    payload: Dict[str, str],
    provider: Optional[str] = None,
) -> None:
    """Persist location payload to cache."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    data = {
        "lat": payload.get("lat"),
        "lon": payload.get("lon"),
        "address_notes": payload.get("address_notes", ""),
        "fetched_at": time.time(),
    }
    if provider:
        data["provider"] = provider
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle)


def _fetch_location_ipinfo(timeout_s: int = 4) -> Optional[Dict[str, str]]:
    """Fetch location from ipinfo.io."""
    req = urllib.request.Request(
        "https://ipinfo.io/json",
        headers={"User-Agent": "uxi-lite/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = json.load(resp)
    loc = data.get("loc")
    if not loc:
        return None
    parts = [part.strip() for part in str(loc).split(",")]
    if len(parts) != 2:
        return None
    lat, lon = parts
    notes = ", ".join(
        [str(value) for value in [data.get("city"), data.get("region"), data.get("country")] if value]
    )
    return {"lat": lat, "lon": lon, "address_notes": notes}


def _fetch_location_ipapi(timeout_s: int = 4) -> Optional[Dict[str, str]]:
    """Fetch location from ipapi.co."""
    req = urllib.request.Request(
        "https://ipapi.co/json",
        headers={"User-Agent": "uxi-lite/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = json.load(resp)
    lat = data.get("latitude")
    lon = data.get("longitude")
    if lat is None or lon is None:
        return None
    notes = ", ".join(
        [str(value) for value in [data.get("city"), data.get("region"), data.get("country_name")] if value]
    )
    return {"lat": str(lat), "lon": str(lon), "address_notes": notes}


def _fetch_location_google(
    api_key: str,
    wifi_env: List[Dict[str, Any]],
    consider_ip: Optional[bool] = None,
    timeout_s: int = 5,
) -> Optional[Dict[str, str]]:
    """Fetch location from Google Geolocation API using Wi-Fi BSSIDs."""
    api_key = api_key.strip()
    if not api_key:
        return None

    access_points = []
    for ap in wifi_env:
        bssid = ap.get("bssid")
        if not bssid:
            continue
        entry = {"macAddress": str(bssid)}
        rssi = ap.get("rssi_dbm")
        if rssi is not None:
            entry["signalStrength"] = int(round(float(rssi)))
        channel = ap.get("channel")
        if channel is not None:
            try:
                entry["channel"] = int(channel)
            except (TypeError, ValueError):
                pass
        access_points.append(entry)

    if not access_points:
        return None

    payload: Dict[str, Any] = {"wifiAccessPoints": access_points}
    if consider_ip is not None:
        payload["considerIp"] = bool(consider_ip)

    url = f"https://www.googleapis.com/geolocation/v1/geolocate?key={urllib.parse.quote(api_key)}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "User-Agent": "uxi-lite/1.0",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = json.load(resp)

    location = data.get("location") or {}
    lat = location.get("lat")
    lon = location.get("lng")
    if lat is None or lon is None:
        return None
    return {"lat": str(lat), "lon": str(lon), "address_notes": ""}


def get_location_config(
    cfg: Dict[str, Any],
    wifi_env: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, str]]:
    """Get location config if available.

    Supports manual lat/lon or auto geolocation via public IP/Google Wi-Fi.
    """
    location = cfg.get("location") or {}
    address_notes = location.get("address_notes") or ""
    lat = location.get("lat")
    lon = location.get("lon")
    if lat is not None and lon is not None:
        return {
            "lat": str(lat),
            "lon": str(lon),
            "address_notes": str(address_notes),
        }

    if not bool(location.get("auto")):
        return None

    provider = str(location.get("provider") or "ipinfo").lower()
    cache_path = str(
        location.get("cache_path") or "/opt/uxi-lite-sensor/state/location.json"
    )
    refresh_hours = float(location.get("refresh_hours", 24))
    refresh_seconds = max(0, int(refresh_hours * 3600))

    cached = _load_location_cache(cache_path, refresh_seconds, provider)
    if cached:
        if address_notes:
            cached["address_notes"] = str(address_notes)
        return cached

    try:
        if provider == "google":
            api_key = str(location.get("google_api_key") or location.get("api_key") or "")
            min_aps = int(location.get("google_min_aps", 2))
            consider_ip = location.get("google_consider_ip")
            wifi_list = wifi_env or []
            if len(wifi_list) < max(1, min_aps):
                fetched = None
            else:
                fetched = _fetch_location_google(api_key, wifi_list, consider_ip=consider_ip)
        elif provider == "ipapi":
            fetched = _fetch_location_ipapi()
        else:
            fetched = _fetch_location_ipinfo()
    except Exception:  # pylint: disable=broad-except
        fetched = None

    if not fetched:
        return None
    if address_notes:
        fetched["address_notes"] = str(address_notes)
    _save_location_cache(cache_path, fetched, provider=provider)
    return fetched


def get_incident_thresholds(cfg: Dict[str, Any]) -> Dict[str, float]:
    """Get incident thresholds with defaults."""
    thresholds = cfg.get("incident_thresholds") or {}
    return {
        "dns_ms": float(thresholds.get("dns_ms", 200)),
        "dhcp_ms": float(thresholds.get("dhcp_ms", 1500)),
        "packet_loss_pct": float(thresholds.get("packet_loss_pct", 5)),
        "latency_ms": float(thresholds.get("latency_ms", 100)),
        "jitter_ms": float(thresholds.get("jitter_ms", 50)),
        "association_ms": float(thresholds.get("association_ms", 10000)),
        "http_ms": float(thresholds.get("http_ms", 3000)),
        "rssi_dbm": float(thresholds.get("rssi_dbm", -75)),
    }


def get_throughput_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Get throughput test configuration."""
    throughput_cfg = cfg.get("throughput_test") or {}
    return {
        "enabled": bool(throughput_cfg.get("enabled", False)),
        "url": throughput_cfg.get("url", "https://speed.hetzner.de/10MB.bin"),
        "upload_url": throughput_cfg.get("upload_url", "https://httpbin.org/post"),
    }


def get_external_http_url(cfg: Dict[str, Any]) -> str:
    """Get external HTTP URL for web reachability check."""
    external_cfg = cfg.get("external_http") or {}
    url = external_cfg.get("url")
    if url:
        return str(url).strip()

    services = _get_services(cfg)
    for entry in services.get("external", []):
        tests = entry.get("tests") or []
        if "http" in tests:
            return _normalize_http_target(str(entry.get("target", "")).strip())

    targets_cfg = cfg.get("targets", {}) or {}
    for key in ("http_external", "external_http"):
        candidates = parse_target_entries(targets_cfg.get(key))
        if candidates:
            return candidates[0]

    nested_external = (targets_cfg.get("external") or {}).get("http")
    candidates = parse_target_entries(nested_external)
    if candidates:
        return candidates[0]

    top_level = cfg.get("external_url")
    if top_level:
        return str(top_level).strip()

    return "https://www.google.com"


def build_networks(cfg: Dict[str, Any]) -> List[NetworkConfig]:
    """Build network list from configuration.

    Args:
        cfg: Configuration dict.

    Returns:
        List of NetworkConfig objects (max 4).
    """
    networks: List[NetworkConfig] = []
    external_http_url = get_external_http_url(cfg)

    for entry in cfg.get("wifi", []) or []:
        iface = entry.get("iface")
        ssid = entry.get("ssid")
        password = entry.get("password", "")
        external_url = entry.get("external_url") or external_http_url
        
        # WPA Enterprise (802.1X) fields
        eap_method = entry.get("eap_method")  # PEAP, TTLS, TLS
        phase2_auth = entry.get("phase2_auth")  # MSCHAPv2, PAP, CHAP
        identity = entry.get("identity")  # Username
        anonymous_identity = entry.get("anonymous_identity")  # Optional
        
        # BSSID lock to prevent roaming (optional)
        bssid_lock = entry.get("bssid_lock")  # e.g., "a0:25:d7:df:3e:70"
        
        if not (iface and ssid):
            LOG.warning("Skipping wifi entry with missing fields (need iface/ssid): %s", entry)
            continue
        name = entry.get("name") or f"wifi-{ssid}"
        networks.append(
            NetworkConfig(
                name=name,
                kind="wifi",
                iface=iface,
                ssid=ssid,
                password=password,
                external_url=external_url,
                eap_method=eap_method,
                phase2_auth=phase2_auth,
                identity=identity,
                anonymous_identity=anonymous_identity,
                bssid_lock=bssid_lock,
            )
        )

    for entry in cfg.get("wired", []) or []:
        iface = entry.get("iface")
        external_url = entry.get("external_url") or external_http_url
        if not iface:
            LOG.warning("Skipping wired entry with missing fields (need iface): %s", entry)
            continue
        name = entry.get("name") or f"wired-{iface}"
        networks.append(
            NetworkConfig(
                name=name,
                kind="wired",
                iface=iface,
                ssid=None,
                password=None,
                external_url=external_url,
            )
        )

    if len(networks) > 4:
        LOG.warning("More than 4 networks configured, using first 4")
    return networks[:4]


def _set_gauge_value(gauge: Gauge, labels: Dict[str, str], value: Optional[float]) -> None:
    """Set a gauge value, using NaN when data is missing.

    Args:
        gauge: Prometheus gauge to update.
        labels: Label dict for the gauge.
        value: Value to set or None.
    """
    gauge.labels(**labels).set(float("nan") if value is None else value)


def _set_singleton_gauge(
    gauge: Gauge,
    label_names: List[str],
    label_values: Tuple[str, ...],
    state: Dict[Any, Tuple[str, ...]],
    state_key: Any,
) -> None:
    """Set a singleton gauge series and remove the previous one if changed."""
    previous = state.get(state_key)
    if previous and previous != label_values:
        gauge.remove(*previous)
    gauge.labels(**dict(zip(label_names, label_values))).set(1.0)
    state[state_key] = label_values


def _clear_singleton_gauge(
    gauge: Gauge,
    state: Dict[Any, Tuple[str, ...]],
    state_key: Any,
) -> None:
    """Remove a singleton gauge series for a state key."""
    previous = state.pop(state_key, None)
    if previous:
        gauge.remove(*previous)


def update_metrics(
    sensor_name: str,
    network_name: str,
    steps: Dict[str, StepResult],
    ip_present: bool,
    wifi_info: Optional[Dict[str, Any]],
    service_results: List[Dict[str, Optional[float]]],
    internal_targets: set[str],
    external_targets: set[str],
    wifi_bssid_state: Dict[Any, Tuple[str, ...]],
) -> None:
    """Update Prometheus gauges.

    Args:
        sensor_name: Sensor name label.
        network_name: Network name label.
        steps: Step results.
        ip_present: Whether IPv4 is present.
        wifi_info: Wi-Fi info dict (wifi networks only).
        service_results: Service ping results.
        wifi_bssid_state: Mutable state for Wi-Fi BSSID series.
    """
    for step_name, result in steps.items():
        UXI_CORE_OK.labels(sensor=sensor_name, network=network_name, step=step_name).set(
            1 if result.ok else 0
        )
        UXI_CORE_TIME_MS.labels(
            sensor=sensor_name, network=network_name, step=step_name
        ).set(result.duration_ms)

    UXI_NETWORK_IP_PRESENT.labels(sensor=sensor_name, network=network_name).set(
        1 if ip_present else 0
    )

    if wifi_info is not None:
        labels = {"sensor": sensor_name, "network": network_name}
        _set_gauge_value(UXI_WIFI_RSSI_DBM, labels, wifi_info.get("rssi_dbm"))
        _set_gauge_value(UXI_WIFI_FREQ_MHZ, labels, wifi_info.get("freq_mhz"))
        _set_gauge_value(UXI_WIFI_CHANNEL, labels, wifi_info.get("channel"))
        _set_gauge_value(UXI_WIFI_TX_BITRATE_MBPS, labels, wifi_info.get("tx_bitrate_mbps"))
        _set_gauge_value(UXI_WIFI_RX_BITRATE_MBPS, labels, wifi_info.get("rx_bitrate_mbps"))
        _set_gauge_value(UXI_WIFI_CHANNEL_BUSY_PCT, labels, wifi_info.get("channel_busy_pct"))
        _set_gauge_value(
            UXI_WIFI_FRAME_RETRY_RATE_PCT,
            labels,
            wifi_info.get("frame_retry_rate_pct"),
        )
        client_count = wifi_info.get("client_count", 1)
        UXI_WIFI_CLIENT_COUNT.labels(**labels).set(float(client_count))

        bssid = wifi_info.get("bssid")
        ssid = wifi_info.get("ssid") or network_name
        if bssid:
            _set_singleton_gauge(
                UXI_WIFI_BSSID_INFO,
                ["sensor", "network", "bssid", "ssid"],
                (sensor_name, network_name, str(bssid), str(ssid)),
                wifi_bssid_state,
                (sensor_name, network_name),
            )
        else:
            _clear_singleton_gauge(
                UXI_WIFI_BSSID_INFO,
                wifi_bssid_state,
                (sensor_name, network_name),
            )

        band = wifi_info.get("band")
        for band_label in ["2.4", "5", "6"]:
            UXI_WIFI_BAND.labels(
                sensor=sensor_name, network=network_name, band=band_label
            ).set(1.0 if band == band_label else 0.0)

    for result in service_results:
        target = result.get("target")
        if not target:
            continue
        if target in internal_targets:
            scope = "internal"
        elif target in external_targets:
            scope = "external"
        else:
            scope = "external"
        
        labels = {"sensor": sensor_name, "network": network_name, "target": target, "scope": scope}
        UXI_SERVICE_SCOPE.labels(
            sensor=sensor_name, network=network_name, target=target, scope=scope
        ).set(1.0)
        _set_gauge_value(UXI_SERVICE_RTT_AVG_MS, labels, result.get("rtt_avg_ms"))
        _set_gauge_value(UXI_SERVICE_PACKET_LOSS_PCT, labels, result.get("loss_pct"))
        _set_gauge_value(UXI_SERVICE_JITTER_MS, labels, result.get("jitter_ms"))
        
        # Service UP status (derived from packet loss)
        loss_pct = result.get("loss_pct")
        service_name = result.get("name", target)
        if loss_pct is not None:
            is_up = 1.0 if loss_pct < 100 else 0.0
            UXI_SERVICE_UP.labels(
                sensor=sensor_name, network=network_name, target=target, scope=scope, name=service_name
            ).set(is_up)
        
        # Last test timestamp
        UXI_SERVICE_LAST_TEST_TIMESTAMP.labels(
            sensor=sensor_name, network=network_name, target=target, scope=scope
        ).set(time.time())


def collect_network_info(
    network: NetworkConfig,
    ip_address: Optional[str],
    gateway: Optional[str],
) -> Dict[str, str]:
    """Collect network info labels for ABOUT panel."""
    ip_config = get_ip_config_label(network.iface)
    dhcp_server = get_dhcp_server(network.iface)
    primary_dns, secondary_dns = get_dns_servers(network.iface)
    wifi_mac = get_interface_mac(network.iface)
    wifi_ip = get_interface_ipv4(network.iface)
    if ip_address and wifi_ip == "unknown":
        wifi_ip = ip_address
    return {
        "ip_config": _normalize_label(ip_config, "Unknown"),
        "dhcp_server": _normalize_label(dhcp_server, "unknown"),
        "gateway": _normalize_label(gateway, "unknown"),
        "primary_dns": _normalize_label(primary_dns, "unknown"),
        "secondary_dns": _normalize_label(secondary_dns, "unknown"),
        "wifi_mac": _normalize_label(wifi_mac, "unknown"),
        "wifi_ip": _normalize_label(wifi_ip, "unknown"),
    }


def update_info_metrics(
    sensor_name: str,
    network: NetworkConfig,
    network_info: Dict[str, str],
    sensor_model: str,
    sensor_serial: str,
    location_cfg: Optional[Dict[str, str]],
    info_state: Dict[str, Dict[Any, Tuple[str, ...]]],
) -> None:
    """Update info/location metrics with singleton series."""
    _set_singleton_gauge(
        UXI_SENSOR_INFO,
        ["sensor", "model", "serial"],
        (sensor_name, sensor_model, sensor_serial),
        info_state.setdefault("sensor_info", {}),
        sensor_name,
    )

    network_labels = (
        sensor_name,
        network.name,
        network_info["ip_config"],
        network_info["dhcp_server"],
        network_info["gateway"],
        network_info["primary_dns"],
        network_info["secondary_dns"],
        network_info["wifi_mac"],
        network_info["wifi_ip"],
    )
    _set_singleton_gauge(
        UXI_NETWORK_INFO,
        [
            "sensor",
            "network",
            "ip_config",
            "dhcp_server",
            "gateway",
            "primary_dns",
            "secondary_dns",
            "wifi_mac",
            "wifi_ip",
        ],
        network_labels,
        info_state.setdefault("network_info", {}),
        (sensor_name, network.name),
    )

    if location_cfg:
        location_labels = (
            sensor_name,
            network.name,
            location_cfg["lat"],
            location_cfg["lon"],
            location_cfg["address_notes"],
        )
        _set_singleton_gauge(
            UXI_SENSOR_LOCATION,
            ["sensor", "network", "lat", "lon", "address_notes"],
            location_labels,
            info_state.setdefault("location", {}),
            (sensor_name, network.name),
        )
    else:
        _clear_singleton_gauge(
            UXI_SENSOR_LOCATION,
            info_state.setdefault("location", {}),
            (sensor_name, network.name),
        )


def select_external_target(icmp_targets: List[str]) -> Optional[str]:
    """Pick the external target for MOS calculation."""
    if "1.1.1.1" in icmp_targets:
        return "1.1.1.1"
    return icmp_targets[0] if icmp_targets else None


def parse_target_entries(entries: Any) -> List[str]:
    """Parse target entries from config into a list of strings."""
    if not entries:
        return []
    if not isinstance(entries, list):
        return []
    targets: List[str] = []
    for item in entries:
        if isinstance(item, str):
            value = item.strip()
            if value:
                targets.append(value)
            continue
        if isinstance(item, dict):
            raw = item.get("target") or item.get("host") or item.get("address")
            if raw is None:
                continue
            value = str(raw).strip()
            if value:
                targets.append(value)
    return targets


def _normalize_test_name(value: str) -> str:
    """Normalize a test name to a canonical identifier."""
    key = value.strip().lower().replace("-", "_")
    return TEST_ALIASES.get(key, key)


def _normalize_tests(entries: Any) -> List[str]:
    """Normalize tests list into a de-duplicated list of names."""
    if entries is None:
        return []
    values = entries if isinstance(entries, list) else [entries]
    tests: List[str] = []
    seen: set[str] = set()
    for item in values:
        if item is None:
            continue
        name = _normalize_test_name(str(item))
        if not name or name in seen:
            continue
        tests.append(name)
        seen.add(name)
    return tests


def parse_service_entries(entries: Any) -> List[Dict[str, Any]]:
    """Parse service entries from config."""
    if not entries or not isinstance(entries, list):
        return []
    services: List[Dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        raw_target = item.get("target") or item.get("host") or item.get("address")
        # Allow services without target (e.g., throughput-only)
        target = str(raw_target).strip() if raw_target else ""
        name = str(item.get("name") or target or "unnamed").strip()
        tests = _normalize_tests(item.get("tests"))
        if not tests:
            LOG.warning("Service entry %s missing tests; defaulting to icmp", name)
            tests = ["icmp"]
        # Get frequency setting (fastest, 10min, 20min, 30min, 1hr, etc.)
        frequency = str(item.get("frequency", "fastest")).strip()
        services.append({
            "name": name,
            "target": target,
            "tests": tests,
            "frequency": frequency,
        })
    return services


def _get_services(cfg: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Get services grouped by scope."""
    services_cfg = cfg.get("services", {}) or {}
    return {
        "internal": parse_service_entries(services_cfg.get("internal")),
        "external": parse_service_entries(services_cfg.get("external")),
    }


def _extract_host(target: str) -> str:
    """Extract hostname/IP from a target that may be a URL."""
    parsed = urllib.parse.urlparse(target)
    if parsed.scheme and parsed.hostname:
        return parsed.hostname
    return target


def _normalize_http_target(target: str) -> str:
    """Normalize an HTTP target to include scheme."""
    parsed = urllib.parse.urlparse(target)
    if parsed.scheme:
        return target
    return f"https://{target}"


def get_icmp_targets(cfg: Dict[str, Any]) -> Tuple[List[str], List[str], List[str]]:
    """Get ICMP targets from config.

    Supports services format:
      services:
        internal:
          - name: Gateway
            target: 10.0.0.1
            tests: [icmp]
        external:
          - name: Google
            target: https://www.google.com
            tests: [icmp, http]

    Supports both legacy format:
      targets:
        icmp: ["8.8.8.8", "1.1.1.1"]

    And current format:
      targets:
        icmp_internal: [{name: ..., target: ...}, ...]
        icmp_external: [{name: ..., target: ...}, ...]

    Returns:
        Tuple of (all_targets, internal_targets, external_targets).
    """
    services = _get_services(cfg)
    internal_targets: List[str] = []
    external_targets: List[str] = []
    for entry in services.get("internal", []):
        if "icmp" in (entry.get("tests") or []):
            host = _extract_host(str(entry.get("target", "")).strip())
            if host:
                internal_targets.append(host)
    for entry in services.get("external", []):
        if "icmp" in (entry.get("tests") or []):
            host = _extract_host(str(entry.get("target", "")).strip())
            if host:
                external_targets.append(host)

    targets_cfg = cfg.get("targets", {}) or {}
    internal_targets.extend(parse_target_entries(targets_cfg.get("icmp_internal")))
    external_targets.extend(parse_target_entries(targets_cfg.get("icmp_external")))

    nested_internal = (targets_cfg.get("internal") or {}).get("icmp")
    nested_external = (targets_cfg.get("external") or {}).get("icmp")
    internal_targets.extend(parse_target_entries(nested_internal))
    external_targets.extend(parse_target_entries(nested_external))

    legacy_targets = parse_target_entries(targets_cfg.get("icmp"))
    if legacy_targets:
        external_targets.extend(legacy_targets)

    internal_unique: List[str] = []
    external_unique: List[str] = []
    seen_internal: set[str] = set()
    seen_external: set[str] = set()
    for target in internal_targets:
        if target in seen_internal:
            continue
        internal_unique.append(target)
        seen_internal.add(target)
    for target in external_targets:
        if target in seen_external:
            continue
        external_unique.append(target)
        seen_external.add(target)

    all_targets: List[str] = []
    seen: set[str] = set()
    for target in internal_unique + external_unique:
        if target in seen:
            continue
        all_targets.append(target)
        seen.add(target)
    return all_targets, internal_unique, external_unique


def find_service_result(
    service_results: List[Dict[str, Optional[float]]],
    target: Optional[str],
) -> Optional[Dict[str, Optional[float]]]:
    """Find service result by target label."""
    if not target:
        return None
    for result in service_results:
        if result.get("target") == target:
            return result
    return None


def update_voip_mos_metrics(
    sensor_name: str,
    network_name: str,
    internal_result: Optional[Dict[str, Optional[float]]],
    external_result: Optional[Dict[str, Optional[float]]],
) -> None:
    """Update VoIP MOS metrics for internal/external scopes."""
    internal_mos = None
    if internal_result:
        internal_mos = compute_voip_mos(
            internal_result.get("rtt_avg_ms"),
            internal_result.get("loss_pct"),
            internal_result.get("jitter_ms"),
        )
    _set_gauge_value(
        UXI_VOIP_MOS,
        {"sensor": sensor_name, "network": network_name, "scope": "internal"},
        internal_mos,
    )

    external_mos = None
    if external_result:
        external_mos = compute_voip_mos(
            external_result.get("rtt_avg_ms"),
            external_result.get("loss_pct"),
            external_result.get("jitter_ms"),
        )
    _set_gauge_value(
        UXI_VOIP_MOS,
        {"sensor": sensor_name, "network": network_name, "scope": "external"},
        external_mos,
    )


def evaluate_incidents(
    steps: Dict[str, StepResult],
    service_results: List[Dict[str, Optional[float]]],
    thresholds: Dict[str, float],
    wifi_info: Optional[Dict[str, Any]] = None,
    captive_portal: bool = False,
) -> Dict[str, bool]:
    """Evaluate incident conditions.

    Args:
        steps: Step results dict.
        service_results: Service test results.
        thresholds: Incident thresholds.
        wifi_info: Wi-Fi info dict (optional).
        captive_portal: Whether captive portal was detected.

    Returns:
        Dict of incident type to active status.
    """
    dns_step = steps.get("dns_resolve")
    dhcp_step = steps.get("dhcp_ip")
    assoc_step = steps.get("wifi_association")
    http_step = steps.get("external_http")

    # High DNS lookup time
    high_dns = bool(
        dns_step and dns_step.ok and dns_step.duration_ms > thresholds.get("dns_ms", 200)
    )

    # DHCP slow
    dhcp_slow = bool(
        dhcp_step and dhcp_step.ok and dhcp_step.duration_ms > thresholds.get("dhcp_ms", 1500)
    )

    # Association slow (> 10 seconds)
    association_slow = bool(
        assoc_step and assoc_step.ok and assoc_step.duration_ms > thresholds.get("association_ms", 10000)
    )

    # HTTP slow (> 3 seconds)
    http_slow = bool(
        http_step and http_step.ok and http_step.duration_ms > thresholds.get("http_ms", 3000)
    )

    # Weak signal (RSSI < -75 dBm)
    weak_signal = False
    if wifi_info:
        rssi = wifi_info.get("rssi_dbm")
        if rssi is not None:
            weak_signal = rssi < thresholds.get("rssi_dbm", -75)

    # Packet loss, high latency, high jitter from service results
    max_loss = None
    max_latency = None
    max_jitter = None
    for result in service_results:
        target = result.get("target")
        if target == "gateway":
            continue
        loss_pct = result.get("loss_pct")
        rtt_ms = result.get("rtt_avg_ms")
        jitter_ms = result.get("jitter_ms")

        if loss_pct is not None:
            if max_loss is None or loss_pct > max_loss:
                max_loss = loss_pct
        if rtt_ms is not None:
            if max_latency is None or rtt_ms > max_latency:
                max_latency = rtt_ms
        if jitter_ms is not None:
            if max_jitter is None or jitter_ms > max_jitter:
                max_jitter = jitter_ms

    packet_loss = bool(
        max_loss is not None and max_loss > thresholds.get("packet_loss_pct", 5)
    )
    high_latency = bool(
        max_latency is not None and max_latency > thresholds.get("latency_ms", 100)
    )
    high_jitter = bool(
        max_jitter is not None and max_jitter > thresholds.get("jitter_ms", 50)
    )

    return {
        "high_dns_lookup_time": high_dns,
        "dhcp_slow": dhcp_slow,
        "packet_loss": packet_loss,
        "high_latency": high_latency,
        "association_slow": association_slow,
        "weak_signal": weak_signal,
        "captive_portal": captive_portal,
        "http_slow": http_slow,
        "high_jitter": high_jitter,
    }


def _incident_key(sensor_name: str, network_name: str) -> str:
    return f"{sensor_name}::{network_name}"


def _parse_incident_key(key: str) -> Tuple[str, str]:
    if "::" in key:
        sensor_name, network_name = key.split("::", 1)
        return sensor_name, network_name
    return key, ""


def load_incident_state(path: str) -> Dict[str, Any]:
    """Load incident state from JSON."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"active": {}, "resolved": {}, "counters": {}}


def save_incident_state(path: str, state: Dict[str, Any]) -> None:
    """Persist incident state to JSON."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=True)


def initialize_incident_counters(state: Dict[str, Any]) -> None:
    """Initialize incident counters from state."""
    counters = state.get("counters") or {}
    for key, per_type in counters.items():
        sensor_name, network_name = _parse_incident_key(key)
        for inc_type, total in (per_type or {}).items():
            try:
                value = int(total)
            except (TypeError, ValueError):
                value = 0
            if value > 0:
                UXI_INCIDENTS_RESOLVED_TOTAL.labels(
                    sensor=sensor_name, network=network_name, type=inc_type
                ).inc(value)


def update_incident_state(
    sensor_name: str,
    network_name: str,
    active_flags: Dict[str, bool],
    state: Dict[str, Any],
    max_events_per_type: int = 3,
) -> List[Tuple[str, Dict[str, Any]]]:
    """Update incident state and return newly resolved events."""
    now = datetime.now(timezone.utc)
    key = _incident_key(sensor_name, network_name)
    active_map = state.setdefault("active", {}).setdefault(key, {})
    resolved_map = state.setdefault("resolved", {}).setdefault(key, {})
    counters = state.setdefault("counters", {}).setdefault(key, {})
    newly_resolved: List[Tuple[str, Dict[str, Any]]] = []

    for inc_type in INCIDENT_TYPES:
        is_active = bool(active_flags.get(inc_type))
        if is_active:
            if inc_type not in active_map:
                active_map[inc_type] = {"start_ts": now.isoformat()}
        else:
            if inc_type in active_map:
                start_ts = active_map.pop(inc_type).get("start_ts") or now.isoformat()
                try:
                    start_dt = datetime.fromisoformat(start_ts)
                except ValueError:
                    start_dt = now
                duration_ms = int((now - start_dt).total_seconds() * 1000)
                event = {
                    "start_ts": start_ts,
                    "end_ts": now.isoformat(),
                    "duration_ms": duration_ms,
                }
                events = resolved_map.setdefault(inc_type, [])
                events.append(event)
                if len(events) > max_events_per_type:
                    events.pop(0)
                counters[inc_type] = int(counters.get(inc_type, 0)) + 1
                newly_resolved.append((inc_type, event))

    return newly_resolved


def update_incident_metrics(
    sensor_name: str,
    network_name: str,
    active_flags: Dict[str, bool],
    state: Dict[str, Any],
    metrics_state: Dict[str, Any],
) -> None:
    """Update incident metrics from state."""
    for inc_type in INCIDENT_TYPES:
        active = 1.0 if active_flags.get(inc_type) else 0.0
        UXI_INCIDENT_ACTIVE.labels(
            sensor=sensor_name, network=network_name, type=inc_type
        ).set(active)

    key = _incident_key(sensor_name, network_name)
    resolved_map = state.get("resolved", {}).get(key, {})
    current_keys: set[Tuple[str, ...]] = set()

    for inc_type, events in resolved_map.items():
        for event in events or []:
            start_ts = str(event.get("start_ts", ""))
            end_ts = str(event.get("end_ts", ""))
            duration = float(event.get("duration_ms", 0.0))
            label_key = (sensor_name, network_name, inc_type, start_ts, end_ts)
            current_keys.add(label_key)
            UXI_INCIDENT_RESOLVED_EVENT_DURATION_MS.labels(
                sensor=sensor_name,
                network=network_name,
                type=inc_type,
                start_ts=start_ts,
                end_ts=end_ts,
            ).set(duration)

    event_keys = metrics_state.setdefault("resolved_event_keys", set())
    stale_keys = {
        key
        for key in event_keys
        if key[0] == sensor_name and key[1] == network_name and key not in current_keys
    }
    for key in stale_keys:
        UXI_INCIDENT_RESOLVED_EVENT_DURATION_MS.remove(*key)
    event_keys.difference_update(stale_keys)
    event_keys.update(current_keys)


def write_jsonl(path: str, record: Dict[str, Any]) -> None:
    """Append a JSONL record to the log file.

    Args:
        path: JSONL file path.
        record: Record dictionary.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def _format_aruba_timestamp(ts: Optional[datetime] = None) -> str:
    """Format timestamp like Aruba UXI raw report (local time, milliseconds)."""
    if ts is None:
        ts = datetime.now()
    return ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _stable_hex(value: str, length: int = 12) -> str:
    """Stable short hex digest for IDs."""
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()
    return digest[:length]


def load_aruba_state(path: str) -> Dict[str, Any]:
    """Load Aruba export state (sensor_uid/service_uids/network_uids)."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"sensor_uid": "", "services": {}, "networks": {}}


def save_aruba_state(path: str, state: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=True)


def get_or_create_sensor_uid(state: Dict[str, Any]) -> str:
    uid = str(state.get("sensor_uid") or "").strip()
    if uid:
        return uid
    uid = str(uuid.uuid4())
    state["sensor_uid"] = uid
    return uid


def get_or_create_network_uid(state: Dict[str, Any], network: "NetworkConfig") -> str:
    networks = state.setdefault("networks", {})
    key = f"{network.kind}::{network.name}::{network.ssid or ''}::{network.iface}"
    uid = str(networks.get(key) or "").strip()
    if uid:
        return uid
    if network.kind == "wifi" and network.ssid:
        uid = f"ssid-{_stable_hex(network.ssid, 12)}"
    else:
        uid = f"net-{_stable_hex(key, 12)}"
    networks[key] = uid
    return uid


def get_or_create_service_uid(state: Dict[str, Any], scope: str, name: str, target: str) -> str:
    services = state.setdefault("services", {})
    key = f"{scope}::{name}::{target}"
    uid = str(services.get(key) or "").strip()
    if uid:
        return uid
    uid = str(uuid.uuid4())
    services[key] = uid
    return uid


def ensure_aruba_csv_header(path: str) -> None:
    """Create CSV and header if missing."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ARUBA_RAW_COLUMNS)
        writer.writeheader()


def _fmt_float(value: Optional[float], decimals: Optional[int] = None) -> str:
    if value is None:
        return ""
    try:
        val = float(value)
    except (TypeError, ValueError):
        return ""
    if math.isfinite(val) and abs(val - round(val)) < 1e-9:
        return str(int(round(val)))
    if decimals is not None:
        return f"{val:.{decimals}f}".rstrip("0").rstrip(".")
    return f"{val:.7f}".rstrip("0").rstrip(".")


def append_aruba_rows(path: str, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    ensure_aruba_csv_header(path)
    with open(path, "a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ARUBA_RAW_COLUMNS)
        for row in rows:
            # Fill missing columns with empty string
            out = {col: "" for col in ARUBA_RAW_COLUMNS}
            for col, val in (row or {}).items():
                if col not in out:
                    continue
                out[col] = "" if val is None else str(val)
            writer.writerow(out)


def _dns_query_time_seconds(domain: str, server: Optional[str] = None) -> Optional[float]:
    """Return DNS query time in seconds for a resolver."""
    cmd = ["dig", "+tries=1", "+time=2"]
    if server:
        cmd.append(f"@{server}")
    cmd.append(domain)
    res = run_command(cmd, 5)
    match = re.search(r"Query time:\s*(\d+)\s*msec", res.stdout)
    if res.returncode != 0 or not match:
        return None
    return int(match.group(1)) / 1000.0


def _http_get_elapsed_seconds(url: str) -> Optional[float]:
    result = step_external_http(url)
    if not result.ok:
        return None
    return result.duration_ms / 1000.0


def _tcp_connect_stats(host: str, port: int, attempts: int = 10) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """TCP connect 'ping' style stats.

    Returns (latency_ms_avg, jitter_ms_std, loss_pct).
    """
    durations: List[float] = []
    failures = 0
    for _ in range(attempts):
        start = time.monotonic()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        try:
            sock.connect((host, port))
            durations.append((time.monotonic() - start) * 1000.0)
        except Exception:  # pylint: disable=broad-except
            failures += 1
        finally:
            try:
                sock.close()
            except OSError:
                pass
    total = attempts
    loss_pct = (failures / total * 100.0) if total else None
    if not durations:
        return None, None, loss_pct
    avg = sum(durations) / len(durations)
    if len(durations) > 1:
        mean = avg
        var = sum((x - mean) ** 2 for x in durations) / (len(durations) - 1)
        std = math.sqrt(var)
    else:
        std = 0.0
    return avg, std, loss_pct


def _aruba_row(
    test_type_code: str,
    sensor_uid: str,
    sensor_name: str,
    network_uid: str,
    network_alias: str,
    interface_type: str,
    ts: Optional[datetime] = None,
    wifi_info: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Build Aruba CSV row for any test type including wifi_data.

    Args:
        test_type_code: Test type (ping, http_get, throughput, voip_mos, wifi_data, etc.)
        sensor_uid, sensor_name, network_uid, network_alias, interface_type: Context fields.
        ts: Timestamp for the row.
        wifi_info: WiFi link info dict (for wifi_data rows).
        **kwargs: Additional fields (target, name, service_uid, latency, etc.)

    Returns:
        Dict with all CSV columns.
    """
    def fmt(val: Any, decimals: int = 2) -> str:
        return _fmt_float(val, decimals=decimals) if val is not None else ""

    row = {
        "timestamp": _format_aruba_timestamp(ts),
        "sensor_uid": sensor_uid,
        "sensor_name": sensor_name,
        "network_uid": network_uid,
        "network_alias": network_alias,
        "interface_type": interface_type,
        "test_type_code": test_type_code,
        "target": kwargs.get("target", ""),
        "name": kwargs.get("name", ""),
        "ip_address": kwargs.get("ip_address", ""),
        "elapsed_time_seconds": fmt(kwargs.get("elapsed_s"), 3),
        "bssid": "",
        "channel": "",
        "channel_utilization": "",
        "frequency": "",
        "rssi": "",
        "latency": fmt(kwargs.get("latency")),
        "jitter": fmt(kwargs.get("jitter")),
        "packet_loss": fmt(kwargs.get("packet_loss")),
        "download_speed": fmt(kwargs.get("download_speed")),
        "upload_speed": fmt(kwargs.get("upload_speed")),
        "service_uid": kwargs.get("service_uid", ""),
    }

    # Populate wifi fields if wifi_info provided
    if wifi_info:
        if wifi_info.get("bssid"):
            row["bssid"] = str(wifi_info["bssid"])
        if wifi_info.get("channel") is not None:
            row["channel"] = str(int(wifi_info["channel"]))
        if wifi_info.get("channel_busy_pct") is not None:
            row["channel_utilization"] = fmt(float(wifi_info["channel_busy_pct"]) / 100.0)
        if wifi_info.get("freq_mhz") is not None:
            try:
                row["frequency"] = str(int(float(wifi_info["freq_mhz"]) * 1_000_000))
            except (TypeError, ValueError):
                pass
        if wifi_info.get("rssi_dbm") is not None:
            try:
                row["rssi"] = str(int(wifi_info["rssi_dbm"]))
            except (TypeError, ValueError):
                pass

    return row


def _collect_wifi_info_for_aruba(network: "NetworkConfig") -> Optional[Dict[str, Any]]:
    if network.kind != "wifi":
        return None
    link_info = get_wifi_link_info(network.iface) or {}
    link_info["channel_busy_pct"] = get_channel_utilization(network.iface)
    return link_info


def get_aruba_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Return Aruba CSV export config.

    NOTE:
    - Keep backward compatibility with the old nested config:
      aruba: {enabled, raw_csv_path, wifi_data_interval_seconds, dns_domain}
    - Support "normal mode" Aruba CSV export (no aruba.enabled needed) using top-level keys:
      export_aruba_csv: true
      aruba_csv_path: /opt/uxi-lite-sensor/logs/aruba-uxi-raw-data-report.csv
      wifi_data_interval_seconds: 15
    
    Aruba UXI runs tests CONTINUOUSLY with no fixed cycle interval.
    Each service can have its own frequency setting.
    inter_cycle_delay_seconds is optional delay after completing all tests (default: 0).
    inter_test_delay_seconds is optional delay between individual tests (default: 0).
    """
    aruba = cfg.get('aruba', {}) or {}

    enabled = bool(aruba.get('enabled')) or bool(cfg.get('export_aruba_csv'))
    raw_csv_path = (
        aruba.get('raw_csv_path')
        or cfg.get('aruba_csv_path')
        or '/opt/uxi-lite-sensor/logs/aruba-uxi-raw-data-report.csv'
    )
    wifi_data_interval_seconds = int(
        aruba.get('wifi_data_interval_seconds')
        or cfg.get('wifi_data_interval_seconds')
        or 15
    )
    dns_domain = str(aruba.get('dns_domain') or cfg.get('dns_domain') or 'example.com')
    # Optional delay between cycles (Aruba agents use 5 min, sensors use 0)
    inter_cycle_delay_seconds = int(
        aruba.get('inter_cycle_delay_seconds')
        or cfg.get('inter_cycle_delay_seconds')
        or 0
    )
    # Optional delay between individual tests (helps match Aruba UXI test frequency)
    # Aruba UXI averages ~20-40 seconds between tests, default 5s is a good starting point
    inter_test_delay_seconds = float(
        aruba.get('inter_test_delay_seconds')
        or cfg.get('inter_test_delay_seconds')
        or 5.0
    )

    return {
        'enabled': enabled,
        'raw_csv_path': raw_csv_path,
        'wifi_data_interval_seconds': wifi_data_interval_seconds,
        'dns_domain': dns_domain,
        'inter_cycle_delay_seconds': inter_cycle_delay_seconds,
        'inter_test_delay_seconds': inter_test_delay_seconds,
    }


# Frequency mapping: name -> seconds
FREQUENCY_MAP: Dict[str, int] = {
    "fastest": 0,      # Every cycle
    "10min": 600,
    "20min": 1200,
    "30min": 1800,
    "1hr": 3600,
    "2hr": 7200,
    "4hr": 14400,
    "6hr": 21600,
    "12hr": 43200,
}


def get_service_frequency_seconds(service: Dict[str, Any]) -> int:
    """Get frequency in seconds for a service.
    
    Args:
        service: Service configuration dict with optional 'frequency' key.
        
    Returns:
        Frequency in seconds. 0 means run every cycle (fastest).
    """
    freq = str(service.get("frequency", "fastest")).lower().strip()
    return FREQUENCY_MAP.get(freq, 0)


def should_run_service(
    service_key: str,
    frequency_seconds: int,
    last_run_times: Dict[str, float],
) -> bool:
    """Check if a service should run based on its frequency.
    
    Args:
        service_key: Unique key for the service (e.g., "internal:Google:google.com")
        frequency_seconds: Minimum seconds between runs (0 = always run)
        last_run_times: Dict tracking last run time per service
        
    Returns:
        True if service should run, False otherwise.
    """
    if frequency_seconds <= 0:
        return True  # "fastest" - run every cycle
    
    last_run = last_run_times.get(service_key, 0)
    now = time.time()
    
    return (now - last_run) >= frequency_seconds

def run_aruba_mode(
    cfg: Dict[str, Any],
    sensor_name: str,
    networks: List["NetworkConfig"],
) -> None:
    """Run Aruba UXI compatible scheduler and export raw CSV.
    
    Test cycle matches Aruba UXI (per official documentation):
    - Tests run CONTINUOUSLY in round-robin fashion, one at a time
    - Each service can have its own frequency (fastest, 10min, 20min, etc.)
    - Core tests (ap_assoc, dhcp, dns) run every cycle
    - Service tests respect their frequency setting
    - No fixed cycle interval - next cycle starts after previous completes
    - Optional inter_cycle_delay_seconds for agents (default: 0)
    
    Test order per cycle:
    1. Connect to WiFi (AP Association)
    2. DHCP (Allocate IP)
    3. DNS (Primary + Secondary)
    4. Internal service tests (respecting frequency)
    5. External service tests (respecting frequency)
    6. Disconnect and repeat
    
    Each test creates: test_row + wifi_data_row (same timestamp)
    """
    aruba_cfg = get_aruba_config(cfg)
    raw_path = str(aruba_cfg["raw_csv_path"])
    dns_domain = str(aruba_cfg["dns_domain"])
    inter_cycle_delay = int(aruba_cfg.get("inter_cycle_delay_seconds", 0))
    throughput_cfg = get_throughput_config(cfg)

    state = load_aruba_state(cfg.get("aruba_state_path", ARUBA_STATE_PATH))
    sensor_uid = get_or_create_sensor_uid(state)
    ensure_aruba_csv_header(raw_path)
    save_aruba_state(cfg.get("aruba_state_path", ARUBA_STATE_PATH), state)

    # Incident tracking
    incident_state_path = cfg.get("incident_state_path", INCIDENT_STATE_PATH)
    incident_state = load_incident_state(incident_state_path)
    initialize_incident_counters(incident_state)
    incident_metrics_state: Dict[str, Any] = {}
    incident_thresholds = get_incident_thresholds(cfg)

    services = _get_services(cfg)
    all_services: List[Tuple[str, Dict[str, Any]]] = [
        (scope, entry)
        for scope in ("internal", "external")
        for entry in services.get(scope, [])
    ]
    
    # Track last run time per service for frequency control
    # Key format: "{scope}:{name}:{target}"
    last_run_times: Dict[str, float] = {}

    LOG.info(
        "Aruba mode enabled: raw_csv=%s dns_domain=%s inter_cycle_delay=%ds inter_test_delay=%.1fs services=%d",
        raw_path, dns_domain, inter_cycle_delay, aruba_cfg.get("inter_test_delay_seconds", 5.0), len(all_services)
    )
    
    # Get inter-test delay (helps match Aruba UXI test frequency)
    inter_test_delay = float(aruba_cfg.get("inter_test_delay_seconds", 5.0))

    # Helper to build common context dict
    def ctx(network_uid: str, network_alias: str, iface_type: str) -> Dict[str, str]:
        return {
            "sensor_uid": sensor_uid,
            "sensor_name": sensor_name,
            "network_uid": network_uid,
            "network_alias": network_alias,
            "interface_type": iface_type,
        }

    # Track current test state
    current_test_labels: Dict[str, str] = {}
    
    def set_current_test(network_alias: str, test_type: str, target: str = "", service_name: str = "") -> None:
        """Set the currently running test metric."""
        nonlocal current_test_labels
        # Clear previous test
        if current_test_labels:
            try:
                UXI_CURRENT_TEST.labels(**current_test_labels).set(0)
            except Exception:
                pass
        # Set new test
        current_test_labels = {
            "sensor": sensor_name,
            "network": network_alias,
            "test_type": test_type,
            "target": target or "-",
            "service_name": service_name or "-",
        }
        UXI_CURRENT_TEST.labels(**current_test_labels).set(1)
    
    def clear_current_test() -> None:
        """Clear the current test metric."""
        nonlocal current_test_labels
        if current_test_labels:
            try:
                UXI_CURRENT_TEST.labels(**current_test_labels).set(0)
            except Exception:
                pass
            current_test_labels = {}

    # Helper to append test row + wifi_data row (Aruba pattern)
    def append_with_wifi(
        network: "NetworkConfig",
        c: Dict[str, str],
        test_type: str,
        ts: datetime,
        svc_name: str = "",
        service_uid: str = "",
        **test_kwargs: Any,
    ) -> None:
        wifi_info = _collect_wifi_info_for_aruba(network)
        rows = [
            _aruba_row(test_type, **c, ts=ts, name=svc_name, service_uid=service_uid, **test_kwargs),
            _aruba_row("wifi_data", **c, ts=ts, wifi_info=wifi_info, name=svc_name, service_uid=service_uid),
        ]
        append_aruba_rows(raw_path, rows)
    
    # Helper to add delay between tests (helps match Aruba UXI frequency)
    def test_delay() -> None:
        """Add inter-test delay to match Aruba UXI test frequency."""
        if inter_test_delay > 0:
            time.sleep(inter_test_delay)

    # State tracking for Wi-Fi environment metrics (for stale cleanup)
    wifi_env_state: Dict[str, Any] = {}
    
    # Continuous test cycle (Aruba UXI runs tests in round-robin, one at a time)
    cycle_num = 0
    while True:
        cycle_num += 1
        cycle_start = time.time()
        tests_run = 0
        tests_skipped = 0
        
        # Calculate total expected tests for progress tracking
        total_tests_estimate = 0
        for network in networks:
            # Core tests: ap_assoc (if wifi), dhcp, dns (x2)
            total_tests_estimate += 1 if network.kind == "wifi" else 0  # ap_assoc
            total_tests_estimate += 1  # dhcp
            total_tests_estimate += 2  # dns primary + secondary
        # Service tests (estimate - actual depends on frequency)
        for scope, service in all_services:
            tests = service.get("tests") or []
            if "http" in tests:
                total_tests_estimate += 2  # http80 + http443
            if "tcp_80" in tests:
                total_tests_estimate += 1
            if "tcp_443" in tests:
                total_tests_estimate += 1
            if "icmp" in tests:
                total_tests_estimate += 1
            if "voip_mos" in tests:
                total_tests_estimate += 1
            if "throughput" in tests:
                total_tests_estimate += 1
        
        for network in networks:
            network_uid = get_or_create_network_uid(state, network)
            network_alias = network.ssid or network.name
            c = ctx(network_uid, network_alias, network.kind)
            
            # Initialize incident tracking for this network
            aruba_steps: Dict[str, StepResult] = {}
            aruba_service_results: List[Dict[str, Optional[float]]] = []
            aruba_wifi_info: Optional[Dict[str, Any]] = None
            aruba_captive_portal = False
            
            # Set cycle info metrics
            UXI_CYCLE_NUMBER.labels(sensor=sensor_name).set(cycle_num)
            UXI_CYCLE_TESTS_TOTAL.labels(sensor=sensor_name, network=network_alias).set(total_tests_estimate)

            # === CORE TESTS (always run every cycle) ===
            
            # 1. AP Association (WiFi only)
            if network.kind == "wifi":
                set_current_test(network_alias, "ap_assoc", network.ssid or "", "WiFi Association")
                ts = datetime.now()
                assoc = step_wifi_association(
                    iface=network.iface,
                    ssid=network.ssid or "",
                    password=network.password or "",
                    force=True,
                    eap_method=network.eap_method,
                    phase2_auth=network.phase2_auth,
                    identity=network.identity,
                    anonymous_identity=network.anonymous_identity,
                    bssid_lock=network.bssid_lock,
                )
                append_with_wifi(network, c, "ap_assoc", ts,
                               elapsed_s=assoc.duration_ms / 1000.0 if assoc.duration_ms else 0.0)
                
                # Update Prometheus metric for dashboard
                if assoc.duration_ms:
                    UXI_AP_ASSOCIATION_TIME_MS.labels(sensor=sensor_name, network=network_alias).set(assoc.duration_ms)
                
                # Track for incident evaluation
                aruba_steps["wifi_association"] = assoc
                
                tests_run += 1
                UXI_CYCLE_TESTS_COMPLETED.labels(sensor=sensor_name, network=network_alias).set(tests_run)
                UXI_CYCLE_PROGRESS.labels(sensor=sensor_name, network=network_alias).set(
                    min(100, (tests_run / max(1, total_tests_estimate)) * 100)
                )
                UXI_LAST_DATA_TIMESTAMP.labels(sensor=sensor_name, network=network_alias).set(time.time())
                
                # === UPDATE WIFI PROMETHEUS METRICS ===
                wifi_info = _collect_wifi_info_for_aruba(network)
                aruba_wifi_info = wifi_info  # Track for incident evaluation
                if wifi_info:
                    # RSSI (use rssi_dbm key from _parse_wifi_link)
                    rssi = wifi_info.get("rssi_dbm")
                    if rssi is not None:
                        UXI_WIFI_RSSI_DBM.labels(sensor=sensor_name, network=network_alias).set(rssi)
                    
                    channel = wifi_info.get("channel")
                    if channel is not None:
                        UXI_WIFI_CHANNEL.labels(sensor=sensor_name, network=network_alias).set(channel)
                    
                    rx_bitrate = wifi_info.get("rx_bitrate_mbps")
                    if rx_bitrate is not None:
                        UXI_WIFI_RX_BITRATE_MBPS.labels(sensor=sensor_name, network=network_alias).set(rx_bitrate)
                    
                    tx_bitrate = wifi_info.get("tx_bitrate_mbps")
                    if tx_bitrate is not None:
                        UXI_WIFI_TX_BITRATE_MBPS.labels(sensor=sensor_name, network=network_alias).set(tx_bitrate)
                    
                    # Channel utilization (busy percentage)
                    channel_busy = wifi_info.get("channel_busy_pct")
                    if channel_busy is not None:
                        UXI_WIFI_CHANNEL_BUSY_PCT.labels(sensor=sensor_name, network=network_alias).set(channel_busy)
                    
                    # Client count (estimate from ARP table)
                    client_count = get_wifi_client_count(network.iface)
                    UXI_WIFI_CLIENT_COUNT.labels(sensor=sensor_name, network=network_alias).set(client_count)
                    
                    # WiFi frequency
                    freq = wifi_info.get("freq_mhz") or 0
                    if freq > 0:
                        UXI_WIFI_FREQ_MHZ.labels(sensor=sensor_name, network=network_alias).set(freq)
                        # WiFi band (use "2.4", "5", "6" to match dashboard variable)
                        if freq >= 5950:
                            band = "6"
                        elif freq >= 5000:
                            band = "5"
                        else:
                            band = "2.4"
                        for band_label in ["2.4", "5", "6"]:
                            UXI_WIFI_BAND.labels(sensor=sensor_name, network=network_alias, band=band_label).set(
                                1.0 if band == band_label else 0.0
                            )
                    
                    # BSSID info
                    bssid = wifi_info.get("bssid") or "unknown"
                    ssid = wifi_info.get("ssid") or network_alias
                    UXI_WIFI_BSSID_INFO.labels(
                        sensor=sensor_name, network=network_alias, bssid=bssid, ssid=ssid
                    ).set(1.0)
                
                # NOTE: WiFi Environment Scan moved to END of cycle (after all service tests)
                # to match Aruba UXI test order

            # 2. DHCP (Allocate IP) - Full DORA process per Aruba UXI behavior
            # Per https://help.capenetworks.com/en/articles/1981280:
            # "The sensor will do the full DHCP DORA process every time it joins a network"
            set_current_test(network_alias, "dhcp", network.iface, "DHCP")
            
            ts = datetime.now()
            # Use full DORA request (matches Aruba UXI sensor behavior)
            dhcp_res, ip_addr = request_dhcp_lease(network.iface, timeout_s=60)
            append_with_wifi(network, c, "dhcp", ts,
                           ip_address=ip_addr or "",
                           elapsed_s=dhcp_res.duration_ms / 1000.0 if dhcp_res.duration_ms else 0.0)
            
            # Update Prometheus metric for dashboard
            if dhcp_res.duration_ms:
                UXI_DHCP_TIME_MS.labels(sensor=sensor_name, network=network_alias).set(dhcp_res.duration_ms)
            
            # Track for incident evaluation
            aruba_steps["dhcp_ip"] = dhcp_res
            
            # Update network info metrics right after DHCP (when we have valid IP)
            if ip_addr:
                ip_config = get_ip_config_label(network.iface)
                dhcp_server = get_dhcp_server(network.iface)
                _, gateway = step_gateway_present(network.iface)
                primary_dns, secondary_dns = get_dns_servers(network.iface)
                wifi_mac = get_interface_mac(network.iface)
                wifi_ip = ip_addr  # Use the IP we just got
                
                UXI_NETWORK_INFO.labels(
                    sensor=sensor_name,
                    network=network_alias,
                    ip_config=ip_config or "DHCP",
                    dhcp_server=dhcp_server or "unknown",
                    gateway=gateway or "unknown",
                    primary_dns=primary_dns or "unknown",
                    secondary_dns=secondary_dns or "unknown",
                    wifi_mac=wifi_mac or "unknown",
                    wifi_ip=wifi_ip or "unknown",
                ).set(1.0)
                
                # Also update IP present metric
                UXI_NETWORK_IP_PRESENT.labels(sensor=sensor_name, network=network_alias).set(1.0)
            
            tests_run += 1
            UXI_CYCLE_TESTS_COMPLETED.labels(sensor=sensor_name, network=network_alias).set(tests_run)
            UXI_CYCLE_PROGRESS.labels(sensor=sensor_name, network=network_alias).set(
                min(100, (tests_run / max(1, total_tests_estimate)) * 100)
            )
            UXI_LAST_DATA_TIMESTAMP.labels(sensor=sensor_name, network=network_alias).set(time.time())

            # 3. DNS (Primary + Secondary)
            primary_dns, secondary_dns = get_dns_servers(network.iface)
            dns_worst_elapsed_ms: Optional[float] = None
            for dns_server in [primary_dns, secondary_dns]:
                if dns_server and dns_server != "unknown":
                    set_current_test(network_alias, "dns", dns_server, "DNS Resolution")
                    ts = datetime.now()
                    elapsed = _dns_query_time_seconds(dns_domain, dns_server)
                    append_with_wifi(network, c, "dns", ts, ip_address=dns_server, elapsed_s=elapsed)
                    
                    # Update Prometheus metric for dashboard (use last DNS result)
                    if elapsed is not None:
                        UXI_DNS_TIME_MS.labels(sensor=sensor_name, network=network_alias).set(elapsed * 1000)
                        # Track worst DNS time for incident evaluation
                        elapsed_ms = elapsed * 1000
                        if dns_worst_elapsed_ms is None or elapsed_ms > dns_worst_elapsed_ms:
                            dns_worst_elapsed_ms = elapsed_ms
                    
                    tests_run += 1
                    UXI_CYCLE_TESTS_COMPLETED.labels(sensor=sensor_name, network=network_alias).set(tests_run)
                    UXI_CYCLE_PROGRESS.labels(sensor=sensor_name, network=network_alias).set(
                        min(100, (tests_run / max(1, total_tests_estimate)) * 100)
                    )
                    UXI_LAST_DATA_TIMESTAMP.labels(sensor=sensor_name, network=network_alias).set(time.time())
            
            # Track DNS result for incident evaluation
            if dns_worst_elapsed_ms is not None:
                aruba_steps["dns_resolve"] = StepResult(ok=True, duration_ms=dns_worst_elapsed_ms)

            # === SERVICE TESTS (Internal + External) ===
            # Aruba UXI test order: HTTP80 → TCP80 → HTTP443 → TCP443 → ICMP
            # Each service respects its frequency setting
            for scope, service in all_services:
                svc_name = str(service.get("name") or "").strip()
                svc_target = str(service.get("target") or "").strip()
                tests = service.get("tests") or []
                
                # Skip if no name
                if not svc_name:
                    continue
                
                # For throughput-only services, target is optional (uses throughput_test.url)
                # For other tests, target is required
                is_throughput_only = tests == ["throughput"]
                if not svc_target and not is_throughput_only:
                    continue

                # Check frequency - skip if not due yet
                service_key = f"{scope}:{svc_name}:{svc_target}"
                frequency_seconds = get_service_frequency_seconds(service)
                
                if not should_run_service(service_key, frequency_seconds, last_run_times):
                    tests_skipped += 1
                    continue
                
                # Mark service as run
                last_run_times[service_key] = time.time()

                host = _extract_host(svc_target)
                service_uid = get_or_create_service_uid(state, scope, svc_name, svc_target)

                # Port 80 tests (HTTP GET then TCP ping) - Aruba order
                if "http" in tests:
                    set_current_test(network_alias, "http_get", f"http://{host}:80", svc_name)
                    ts = datetime.now()
                    elapsed = _http_get_elapsed_seconds(f"http://{host}:80")
                    append_with_wifi(network, c, "http_get", ts, svc_name, service_uid,
                                   target=f"http://{host}:80", elapsed_s=elapsed)
                    tests_run += 1
                    UXI_CYCLE_TESTS_COMPLETED.labels(sensor=sensor_name, network=network_alias).set(tests_run)
                    test_delay()

                if "tcp_80" in tests:
                    set_current_test(network_alias, "tcp_ping", f"{host}:80", svc_name)
                    ts = datetime.now()
                    latency, jitter, loss = _tcp_connect_stats(host, 80, attempts=10)
                    append_with_wifi(network, c, "ping", ts, svc_name, service_uid,
                                   target=f"{host}:80", latency=latency, jitter=jitter, packet_loss=loss)
                    tests_run += 1
                    UXI_CYCLE_TESTS_COMPLETED.labels(sensor=sensor_name, network=network_alias).set(tests_run)
                    test_delay()

                # Port 443 tests (HTTP GET then TCP ping) - Aruba order
                if "http" in tests:
                    set_current_test(network_alias, "http_get", f"https://{host}:443", svc_name)
                    ts = datetime.now()
                    elapsed = _http_get_elapsed_seconds(f"https://{host}:443")
                    append_with_wifi(network, c, "http_get", ts, svc_name, service_uid,
                                   target=f"https://{host}:443", elapsed_s=elapsed)
                    tests_run += 1
                    UXI_CYCLE_TESTS_COMPLETED.labels(sensor=sensor_name, network=network_alias).set(tests_run)
                    test_delay()

                if "tcp_443" in tests:
                    set_current_test(network_alias, "tcp_ping", f"{host}:443", svc_name)
                    ts = datetime.now()
                    latency, jitter, loss = _tcp_connect_stats(host, 443, attempts=10)
                    append_with_wifi(network, c, "ping", ts, svc_name, service_uid,
                                   target=f"{host}:443", latency=latency, jitter=jitter, packet_loss=loss)
                    tests_run += 1
                    UXI_CYCLE_TESTS_COMPLETED.labels(sensor=sensor_name, network=network_alias).set(tests_run)
                    test_delay()

                # ICMP Ping (last, per Aruba order) - THIS IS THE MAIN SERVICE TEST
                # RTT, jitter, packet_loss metrics come from this test
                if "icmp" in tests:
                    set_current_test(network_alias, "icmp_ping", host, svc_name)
                    ts = datetime.now()
                    ping_res = run_service_ping(host)
                    append_with_wifi(network, c, "ping", ts, svc_name, service_uid,
                                   target=host, latency=ping_res.get("rtt_avg_ms"),
                                   jitter=ping_res.get("jitter_ms"), packet_loss=ping_res.get("loss_pct"))
                    tests_run += 1
                    UXI_CYCLE_TESTS_COMPLETED.labels(sensor=sensor_name, network=network_alias).set(tests_run)
                    test_delay()
                    
                    # === UPDATE PROMETHEUS METRICS FOR DASHBOARD ===
                    rtt = ping_res.get("rtt_avg_ms")
                    jitter = ping_res.get("jitter_ms")
                    loss = ping_res.get("loss_pct")
                    
                    svc_labels = {
                        "sensor": sensor_name,
                        "network": network_alias,
                        "target": host,
                        "scope": scope,
                    }
                    
                    if rtt is not None:
                        UXI_SERVICE_RTT_AVG_MS.labels(**svc_labels).set(rtt)
                    if jitter is not None:
                        UXI_SERVICE_JITTER_MS.labels(**svc_labels).set(jitter)
                    if loss is not None:
                        UXI_SERVICE_PACKET_LOSS_PCT.labels(**svc_labels).set(loss)
                        # Service UP if packet loss < 100%
                        is_up = 1.0 if loss < 100 else 0.0
                        UXI_SERVICE_UP.labels(
                            sensor=sensor_name, network=network_alias, 
                            target=host, scope=scope, name=svc_name
                        ).set(is_up)
                    
                    UXI_SERVICE_LAST_TEST_TIMESTAMP.labels(**svc_labels).set(time.time())
                    UXI_SERVICE_SCOPE.labels(**svc_labels).set(1.0)
                    
                    # Track for incident evaluation
                    aruba_service_results.append({
                        "target": host,
                        "scope": scope,
                        "rtt_avg_ms": rtt,
                        "jitter_ms": jitter,
                        "loss_pct": loss,
                    })

                # VoIP MOS (uses ping test_type_code, MOS calculated from latency/jitter/loss)
                if "voip_mos" in tests:
                    set_current_test(network_alias, "voip_mos", host, svc_name)
                    ts = datetime.now()
                    ping_res = run_service_ping(host)
                    append_with_wifi(network, c, "ping", ts, svc_name, service_uid,
                                   target=host, latency=ping_res.get("rtt_avg_ms"),
                                   jitter=ping_res.get("jitter_ms"), packet_loss=ping_res.get("loss_pct"))
                    tests_run += 1
                    UXI_CYCLE_TESTS_COMPLETED.labels(sensor=sensor_name, network=network_alias).set(tests_run)
                    test_delay()
                    
                    # Calculate MOS score and update metrics
                    rtt = ping_res.get("rtt_avg_ms") or 0
                    jitter = ping_res.get("jitter_ms") or 0
                    loss = ping_res.get("loss_pct") or 0
                    mos = compute_voip_mos(rtt, loss, jitter)
                    if mos is not None:
                        UXI_VOIP_MOS.labels(sensor=sensor_name, network=network_alias, scope=scope).set(mos)

                # Throughput test (Fast.com-like) - Aruba UXI uses headless Chromium
                # NOW ALSO outputs to raw CSV for Aruba UXI compatibility
                if "throughput" in tests and throughput_cfg.get("enabled"):
                    set_current_test(network_alias, "throughput", "speed.test", svc_name)
                    ts = datetime.now()
                    # Use Fast.com-like parallel download test
                    download_speed, elapsed = run_fastcom_throughput_test(timeout_s=20)
                    
                    # Update Prometheus metrics for dashboard display
                    if download_speed is not None:
                        UXI_THROUGHPUT_DOWNLOAD_MBPS.labels(
                            sensor=sensor_name,
                            network=network_alias,
                            target=svc_name,
                        ).set(download_speed)
                        LOG.info(
                            "Throughput test %s: download=%.2f Mbps (elapsed=%.1fs)",
                            svc_name, download_speed, elapsed or 0
                        )
                        
                        # === WRITE THROUGHPUT TO CSV (Aruba UXI compatible) ===
                        append_with_wifi(
                            network, c, "throughput", ts,
                            svc_name=svc_name,
                            service_uid=service_uid,
                            download_speed=download_speed,
                            elapsed_s=elapsed,
                        )
                    else:
                        LOG.warning("Throughput test %s: FAILED", svc_name)
                    tests_run += 1
                    UXI_CYCLE_TESTS_COMPLETED.labels(sensor=sensor_name, network=network_alias).set(tests_run)
                
                # Update progress
                UXI_CYCLE_PROGRESS.labels(sensor=sensor_name, network=network_alias).set(
                    min(100, (tests_run / max(1, total_tests_estimate)) * 100)
                )
                UXI_LAST_DATA_TIMESTAMP.labels(sensor=sensor_name, network=network_alias).set(time.time())

            # === WIFI ENVIRONMENT SCAN (at end of cycle per Aruba UXI order) ===
            if network.kind == "wifi":
                wifi_env_cfg = get_wifi_env_config(cfg)
                if wifi_env_cfg.get("enabled", False):
                    set_current_test(network_alias, "wifi_scan", network.iface, "WiFi Environment Scan")
                    wifi_env = collect_wifi_environment(network.iface, wifi_env_cfg)
                    if wifi_env:
                        update_wifi_environment_metrics(
                            sensor_name=sensor_name,
                            network_name=network_alias,
                            iface=network.iface,
                            wifi_env=wifi_env,
                            config=wifi_env_cfg,
                            env_state=wifi_env_state,
                        )
                        
                        # Update channel busy percentage from environment scan
                        wifi_info = _collect_wifi_info_for_aruba(network)
                        current_channel = wifi_info.get("channel") if wifi_info else None
                        if current_channel:
                            channel_aps = [ap for ap in wifi_env if ap.get("channel") == current_channel]
                            if channel_aps:
                                busy_estimate = min(100.0, len(channel_aps) * 10.0)
                                UXI_WIFI_CHANNEL_BUSY_PCT.labels(
                                    sensor=sensor_name, network=network_alias
                                ).set(busy_estimate)
                        
                        # Update client count
                        UXI_WIFI_CLIENT_COUNT.labels(sensor=sensor_name, network=network_alias).set(len(wifi_env))

            # === INCIDENT EVALUATION AND METRICS UPDATE ===
            incident_flags = evaluate_incidents(
                steps=aruba_steps,
                service_results=aruba_service_results,
                thresholds=incident_thresholds,
                wifi_info=aruba_wifi_info,
                captive_portal=aruba_captive_portal,
            )
            newly_resolved = update_incident_state(
                sensor_name=sensor_name,
                network_name=network_alias,
                active_flags=incident_flags,
                state=incident_state,
            )
            for inc_type, _event in newly_resolved:
                UXI_INCIDENTS_RESOLVED_TOTAL.labels(
                    sensor=sensor_name, network=network_alias, type=inc_type
                ).inc()
            update_incident_metrics(
                sensor_name=sensor_name,
                network_name=network_alias,
                active_flags=incident_flags,
                state=incident_state,
                metrics_state=incident_metrics_state,
            )
            save_incident_state(incident_state_path, incident_state)

            # Save state after completing all tests for this network
            save_aruba_state(cfg.get("aruba_state_path", ARUBA_STATE_PATH), state)
            
            # Per Aruba UXI behavior: "The sensor explicitly releases the IP when 
            # finished testing a network" - https://help.capenetworks.com/en/articles/1981280
            # NOTE: Network info has already been saved to Prometheus metrics, so releasing
            # the IP here won't affect dashboard display (metrics persist)
            if network.kind == "wifi":
                release_dhcp_lease(network.iface)
                LOG.debug("Released DHCP lease for WiFi network %s after testing", network_alias)
            elif network.kind == "ethernet":
                # For ethernet, we don't release to maintain connectivity for sensor management
                # This matches typical enterprise deployment where sensor needs persistent LAN access
                LOG.debug("Keeping ethernet connection for %s (management network)", network_alias)
            
            # Small delay between networks
            time.sleep(2)

        # Test cycle complete - clear current test indicator
        clear_current_test()
        
        # Set progress to 100%
        for network in networks:
            network_alias = network.ssid or network.name
            UXI_CYCLE_PROGRESS.labels(sensor=sensor_name, network=network_alias).set(100)
        
        cycle_duration = time.time() - cycle_start
        LOG.info(
            "Cycle #%d complete: %d tests run, %d skipped (frequency), duration=%.1fs",
            cycle_num, tests_run, tests_skipped, cycle_duration
        )
        
        # === UPDATE CORE METRICS FOR DASHBOARD ===
        cycle_time_ms = int(cycle_duration * 1000)
        for network in networks:
            network_alias = network.ssid or network.name
            
            # Core status - 1 if we completed without error
            UXI_CORE_OK.labels(sensor=sensor_name, network=network_alias, step="cycle").set(1.0)
            UXI_CORE_TIME_MS.labels(sensor=sensor_name, network=network_alias, step="cycle").set(cycle_time_ms)
            
            # Connection quality score (based on service test results)
            # Simple calculation: 100% if all tests passed, reduced by failures
            quality_score = 100.0
            if tests_run > 0:
                # Estimate based on cycle completion
                quality_score = min(100.0, max(0.0, 100.0 * (tests_run / max(1, total_tests_estimate))))
            UXI_CONNECTION_QUALITY_SCORE.labels(sensor=sensor_name, network=network_alias).set(quality_score)
            
            # Sensor info
            UXI_SENSOR_INFO.labels(sensor=sensor_name, model="UXI-Lite", serial=sensor_uid).set(1.0)
            
            # Network info
            ip_config = get_ip_config_label(network.iface)
            dhcp_server = get_dhcp_server(network.iface)
            _, gateway = step_gateway_present(network.iface)
            primary_dns, secondary_dns = get_dns_servers(network.iface)
            wifi_mac = get_interface_mac(network.iface)
            wifi_ip = get_interface_ipv4(network.iface)
            
            UXI_NETWORK_INFO.labels(
                sensor=sensor_name,
                network=network_alias,
                ip_config=ip_config or "unknown",
                dhcp_server=dhcp_server or "unknown",
                gateway=gateway or "unknown",
                primary_dns=primary_dns or "unknown",
                secondary_dns=secondary_dns or "unknown",
                wifi_mac=wifi_mac or "unknown",
                wifi_ip=wifi_ip or "unknown",
            ).set(1.0)
        
        # Optional delay between cycles (Aruba agents use 5 min, sensors default to 0)
        if inter_cycle_delay > 0:
            set_current_test("-", "waiting", "-", f"Inter-cycle delay ({inter_cycle_delay}s)")
            LOG.info("Waiting %d seconds before next cycle...", inter_cycle_delay)
            time.sleep(inter_cycle_delay)
            clear_current_test()


def run_tests(
    network: NetworkConfig,
    icmp_targets: List[str],
    wifi_env_cfg: Dict[str, Any],
) -> Tuple[
    Dict[str, StepResult],
    Optional[str],
    Optional[str],
    Optional[Dict[str, Any]],
    List[Dict[str, Optional[float]]],
    List[Dict[str, Any]],
]:
    """Run UXI core tests for a network.

    Args:
        network: Network configuration.
        wifi_env_cfg: Wi-Fi environment configuration.

    Returns:
        Tuple of step results, IP address, gateway, Wi-Fi info, service results, and Wi-Fi environment.
    """
    steps: Dict[str, StepResult] = {}
    ip_address: Optional[str] = None
    gateway: Optional[str] = None
    wifi_info: Optional[Dict[str, Any]] = None
    wifi_env: List[Dict[str, Any]] = []

    if network.kind == "wifi":
        scan_result, scan_output = step_wifi_ap_scan(network.iface)
        steps["wifi_ap_scan"] = scan_result
        if scan_result.ok:
            wifi_env = collect_wifi_environment(
                network.iface,
                wifi_env_cfg,
                scan_output=scan_output,
            )
        else:
            wifi_env = collect_wifi_environment(network.iface, wifi_env_cfg)

        ssid_result = step_wifi_ssid_check(scan_output, network.ssid or "")
        steps["wifi_ssid_check"] = ssid_result

        assoc_result = step_wifi_association(
            iface=network.iface,
            ssid=network.ssid or "",
            password=network.password or "",
            eap_method=network.eap_method,
            phase2_auth=network.phase2_auth,
            identity=network.identity,
            anonymous_identity=network.anonymous_identity,
            bssid_lock=network.bssid_lock,
        )
        steps["wifi_association"] = assoc_result
        link_info = get_wifi_link_info(network.iface) or {}
        link_info["channel_busy_pct"] = get_channel_utilization(network.iface)
        link_info["frame_retry_rate_pct"] = get_wifi_frame_retry_rate_pct(network.iface)
        link_info["client_count"] = get_wifi_client_count(network.iface)
        wifi_info = link_info

    dhcp_result, ip_address = step_dhcp_ip_check(network.iface)
    steps["dhcp_ip"] = dhcp_result

    if not ip_address:
        steps["gateway_present"] = StepResult(False, 0, "no_ipv4")
        steps["gateway_ping"] = StepResult(False, 0, "no_ipv4")
        steps["dns_resolve"] = StepResult(False, 0, "no_ipv4")
        steps["external_http"] = StepResult(False, 0, "no_ipv4")
        service_results = run_service_tests(icmp_targets, False)
        return steps, None, None, wifi_info, service_results, wifi_env

    gateway_result, gateway = step_gateway_present(network.iface)
    steps["gateway_present"] = gateway_result

    if gateway:
        ping_result = step_gateway_ping(gateway)
    else:
        ping_result = StepResult(False, 0, "no_gateway")
    steps["gateway_ping"] = ping_result

    dns_result = step_dns_resolve()
    steps["dns_resolve"] = dns_result

    http_result = step_external_http(network.external_url)
    steps["external_http"] = http_result

    service_results = run_service_tests(icmp_targets, True)
    if gateway:
        gateway_result = run_service_ping(gateway)
        gateway_result["target"] = "gateway"
        service_results.append(gateway_result)
    return steps, ip_address, gateway, wifi_info, service_results, wifi_env


def build_record(
    sensor_name: str,
    network: NetworkConfig,
    steps: Dict[str, StepResult],
    ip_address: Optional[str],
    gateway: Optional[str],
    wifi_info: Optional[Dict[str, Any]],
    service_results: List[Dict[str, Optional[float]]],
    wifi_env: List[Dict[str, Any]],
    triage_data: Optional[Dict[str, str]],
) -> Dict[str, Any]:
    """Build JSON record for logging.

    Args:
        sensor_name: Sensor name.
        network: Network configuration.
        steps: Step results.
        ip_address: IPv4 address.
        gateway: Default gateway.
        wifi_info: Wi-Fi info dict.
        service_results: Service metrics list.
        wifi_env: Wi-Fi environment list.
        triage_data: Optional triage data.

    Returns:
        JSON-serializable record.
    """
    record: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sensor_name": sensor_name,
        "network_name": network.name,
        "network_type": network.kind,
        "iface": network.iface,
        "external_url": network.external_url,
        "steps": {name: result.to_dict() for name, result in steps.items()},
    }

    if ip_address:
        record["ip_address"] = ip_address
    if gateway:
        record["gateway"] = gateway
    if wifi_info is not None:
        wifi_record = {
            "rssi_dbm": wifi_info.get("rssi_dbm"),
            "freq_mhz": wifi_info.get("freq_mhz"),
            "band": wifi_info.get("band"),
            "channel": wifi_info.get("channel"),
            "tx_bitrate_mbps": wifi_info.get("tx_bitrate_mbps"),
            "rx_bitrate_mbps": wifi_info.get("rx_bitrate_mbps"),
            "channel_busy_pct": wifi_info.get("channel_busy_pct"),
        }
        if any(value is not None for value in wifi_record.values()):
            record["wifi"] = wifi_record
    if service_results:
        record["services"] = service_results
    if wifi_env:
        record["wifi_environment"] = [
            {
                "ssid": ap.get("ssid"),
                "bssid": ap.get("bssid"),
                "rssi_dbm": ap.get("rssi_dbm"),
                "channel": ap.get("channel"),
                "width_mhz": ap.get("width_mhz"),
                "band": ap.get("band"),
            }
            for ap in wifi_env[:20]
        ]
    if triage_data:
        record["triage"] = triage_data

    return record


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments.

    Returns:
        Parsed arguments.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    default_config = os.path.join(base_dir, "..", "config", "config.yaml")

    parser = argparse.ArgumentParser(description="UXI-Lite Core Tests Exporter")
    parser.add_argument("--config", default=default_config, help="Path to config YAML")
    parser.add_argument("--log-path", default=None, help="Override JSONL log path")
    return parser.parse_args()


def main() -> None:
    """Entrypoint for the exporter."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if os.geteuid() != 0:
        LOG.warning("Exporter should run as root for iw/nmcli operations")

    args = parse_args()
    cfg = load_config(args.config)

    sensor_name = cfg.get("sensor_name") or socket.gethostname()
    sensor_model = get_system_model()
    sensor_serial = get_system_serial()
    metrics_port = int(cfg.get("metrics_port", 9105))
    interval_seconds = int(cfg.get("interval_seconds", 60))
    log_path = args.log_path or cfg.get("log_path")
    icmp_targets, internal_icmp_targets, external_icmp_targets = get_icmp_targets(cfg)
    internal_target_set = set(internal_icmp_targets)
    internal_target_set.add("gateway")
    external_target_set = set(external_icmp_targets)
    wifi_env_cfg = get_wifi_env_config(cfg)
    wifi_env_state: Dict[str, Any] = {"ap_last_seen": {}, "channel_keys": set()}
    incident_thresholds = get_incident_thresholds(cfg)
    throughput_cfg = get_throughput_config(cfg)
    incident_state_path = cfg.get("incident_state_path", INCIDENT_STATE_PATH)
    incident_state = load_incident_state(incident_state_path)
    initialize_incident_counters(incident_state)
    incident_metrics_state: Dict[str, Any] = {"resolved_event_keys": set()}
    info_state: Dict[str, Dict[Any, Tuple[str, ...]]] = {
        "sensor_info": {},
        "network_info": {},
        "location": {},
    }
    wifi_bssid_state: Dict[Any, Tuple[str, ...]] = {}

    if not log_path:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        log_path = os.path.join(base_dir, "..", "logs", "results.jsonl")

    networks = build_networks(cfg)
    if not networks:
        LOG.error("No valid networks configured; sleeping until config is fixed")
        while True:
            time.sleep(interval_seconds)

    start_http_server(metrics_port)
    LOG.info("Metrics server listening on 0.0.0.0:%s", metrics_port)

    # Aruba UXI compatible raw export mode (optional)
    if get_aruba_config(cfg).get("enabled"):
        run_aruba_mode(cfg=cfg, sensor_name=sensor_name, networks=networks)
        return

    index = 0
    while True:
        network = networks[index % len(networks)]
        index += 1

        try:
            steps, ip_address, gateway, wifi_info, service_results, wifi_env = run_tests(
                network,
                icmp_targets,
                wifi_env_cfg,
            )
        except Exception as exc:  # pylint: disable=broad-except
            LOG.exception("Unhandled error while running tests: %s", exc)
            steps = {"internal_error": StepResult(False, 0, str(exc))}
            ip_address = None
            gateway = None
            wifi_info = None
            service_results = run_service_tests(icmp_targets, False)
            wifi_env = []

        failed_steps = [name for name, result in steps.items() if not result.ok]
        triage_data = None
        if failed_steps:
            external_failed = "external_http" in failed_steps
            triage_data = collect_triage(
                external_target=network.external_url,
                include_traceroute=external_failed,
            )

        location_cfg = get_location_config(cfg, wifi_env)
        network_info = collect_network_info(network, ip_address, gateway)
        update_info_metrics(
            sensor_name=sensor_name,
            network=network,
            network_info=network_info,
            sensor_model=sensor_model,
            sensor_serial=sensor_serial,
            location_cfg=location_cfg,
            info_state=info_state,
        )

        # Captive portal detection
        captive_portal_detected = False
        if ip_address:
            captive_portal_detected = detect_captive_portal()
        UXI_CAPTIVE_PORTAL_DETECTED.labels(
            sensor=sensor_name, network=network.name
        ).set(1.0 if captive_portal_detected else 0.0)

        # Connection quality score
        external_target = select_external_target(external_icmp_targets)
        external_result = find_service_result(service_results, external_target)
        rssi = wifi_info.get("rssi_dbm") if wifi_info else None
        rtt = external_result.get("rtt_avg_ms") if external_result else None
        loss = external_result.get("loss_pct") if external_result else None
        jitter = external_result.get("jitter_ms") if external_result else None
        quality_score = calculate_connection_quality_score(
            rssi_dbm=rssi,
            rtt_ms=rtt,
            loss_pct=loss,
            jitter_ms=jitter,
            throughput_mbps=None,  # Throughput test only in Aruba mode
        )
        UXI_CONNECTION_QUALITY_SCORE.labels(
            sensor=sensor_name, network=network.name
        ).set(quality_score)

        update_metrics(
            sensor_name=sensor_name,
            network_name=network.name,
            steps=steps,
            ip_present=bool(ip_address),
            wifi_info=wifi_info,
            service_results=service_results,
            internal_targets=internal_target_set,
            external_targets=external_target_set,
            wifi_bssid_state=wifi_bssid_state,
        )

        update_voip_mos_metrics(
            sensor_name=sensor_name,
            network_name=network.name,
            internal_result=find_service_result(service_results, "gateway"),
            external_result=find_service_result(service_results, external_target),
        )

        incident_flags = evaluate_incidents(
            steps=steps,
            service_results=service_results,
            thresholds=incident_thresholds,
            wifi_info=wifi_info,
            captive_portal=captive_portal_detected,
        )
        newly_resolved = update_incident_state(
            sensor_name=sensor_name,
            network_name=network.name,
            active_flags=incident_flags,
            state=incident_state,
        )
        for inc_type, _event in newly_resolved:
            UXI_INCIDENTS_RESOLVED_TOTAL.labels(
                sensor=sensor_name, network=network.name, type=inc_type
            ).inc()
        update_incident_metrics(
            sensor_name=sensor_name,
            network_name=network.name,
            active_flags=incident_flags,
            state=incident_state,
            metrics_state=incident_metrics_state,
        )
        save_incident_state(incident_state_path, incident_state)

        if network.kind == "wifi":
            update_wifi_environment_metrics(
                sensor_name=sensor_name,
                network_name=network.name,
                iface=network.iface,
                wifi_env=wifi_env,
                config=wifi_env_cfg,
                env_state=wifi_env_state,
            )

        record = build_record(
            sensor_name=sensor_name,
            network=network,
            steps=steps,
            ip_address=ip_address,
            gateway=gateway,
            wifi_info=wifi_info,
            service_results=service_results,
            wifi_env=wifi_env,
            triage_data=triage_data,
        )
        write_jsonl(log_path, record)

        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
