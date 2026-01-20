#!/usr/bin/env python3
"""Minimal self-test for Wi-Fi scan parser."""

import os
import sys

sys.path.append(os.path.dirname(__file__))

from uxi_core_exporter import parse_wifi_scan_output


SAMPLE_OUTPUT = """
BSS 00:11:22:33:44:55(on wlan1)
    freq: 2412
    signal: -45.00 dBm
    SSID: Test24
    HT operation:
        primary channel: 1
        secondary channel offset: above
BSS 66:77:88:99:aa:bb(on wlan1)
    freq: 5180
    signal: -60.00 dBm
    SSID: Test5
    VHT operation:
        channel width: 1 (80 MHz)
"""


def run() -> None:
    """Run basic parser checks."""
    scan_time = 1700000000.0
    aps = parse_wifi_scan_output(SAMPLE_OUTPUT, "wlan1", scan_time)
    assert len(aps) == 2, aps

    ap24 = aps[0]
    assert ap24["bssid"] == "00:11:22:33:44:55"
    assert ap24["ssid"] == "Test24"
    assert ap24["freq_mhz"] == 2412
    assert ap24["band"] == "2.4"
    assert ap24["channel"] == 1
    assert ap24["width_mhz"] == 40
    assert ap24["last_seen_seconds"] == scan_time

    ap5 = aps[1]
    assert ap5["bssid"] == "66:77:88:99:aa:bb"
    assert ap5["ssid"] == "Test5"
    assert ap5["freq_mhz"] == 5180
    assert ap5["band"] == "5"
    assert ap5["channel"] == 36
    assert ap5["width_mhz"] == 80
    assert ap5["last_seen_seconds"] == scan_time


if __name__ == "__main__":
    run()
    print("wifi scan parser ok")
