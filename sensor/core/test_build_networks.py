#!/usr/bin/env python3
"""Minimal self-test for build_networks() config parsing."""

import os
import sys

sys.path.append(os.path.dirname(__file__))

from uxi_core_exporter import build_networks


def run() -> None:
    cfg = {
        "external_http": {"url": "https://example.com"},
        "wifi": [
            {
                "name": "OpenWiFi",
                "iface": "wlan0",
                "ssid": "OPEN_SSID",
                "password": "",
            }
        ],
        "wired": [{"name": "LAN", "iface": "eth0"}],
    }
    networks = build_networks(cfg)
    assert [(n.name, n.kind) for n in networks] == [("OpenWiFi", "wifi"), ("LAN", "wired")]
    assert networks[0].password == ""
    assert networks[0].external_url == "https://example.com"
    assert networks[1].external_url == "https://example.com"


if __name__ == "__main__":
    run()
    print("build_networks ok")
