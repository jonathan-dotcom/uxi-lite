#!/usr/bin/env python3
"""Minimal self-test for config target parsing."""

import os
import sys

sys.path.append(os.path.dirname(__file__))

from uxi_core_exporter import get_icmp_targets


def run() -> None:
    cfg_services = {
        "services": {
            "internal": [{"name": "GW", "target": "10.0.0.1", "tests": ["icmp"]}],
            "external": [
                {"name": "Cloud", "target": "https://www.google.com", "tests": ["icmp", "http"]}
            ],
        }
    }
    all_targets, internal_targets, external_targets = get_icmp_targets(cfg_services)
    assert all_targets == ["10.0.0.1", "www.google.com"]
    assert internal_targets == ["10.0.0.1"]
    assert external_targets == ["www.google.com"]

    cfg_structured = {
        "targets": {
            "icmp_internal": [{"name": "GW", "target": "10.0.0.1"}],
            "icmp_external": [{"name": "Google", "target": "www.google.com"}],
        }
    }
    all_targets, internal_targets, external_targets = get_icmp_targets(cfg_structured)
    assert all_targets == ["10.0.0.1", "www.google.com"]
    assert internal_targets == ["10.0.0.1"]
    assert external_targets == ["www.google.com"]

    cfg_legacy = {"targets": {"icmp": ["1.1.1.1", "8.8.8.8"]}}
    all_targets, internal_targets, external_targets = get_icmp_targets(cfg_legacy)
    assert all_targets == ["1.1.1.1", "8.8.8.8"]
    assert internal_targets == []
    assert external_targets == ["1.1.1.1", "8.8.8.8"]

    cfg_nested = {
        "targets": {
            "internal": {"icmp": [{"name": "GW", "target": "10.10.10.1"}]},
            "external": {"icmp": [{"name": "Cloud", "target": "1.1.1.1"}]},
        }
    }
    all_targets, internal_targets, external_targets = get_icmp_targets(cfg_nested)
    assert all_targets == ["10.10.10.1", "1.1.1.1"]
    assert internal_targets == ["10.10.10.1"]
    assert external_targets == ["1.1.1.1"]


if __name__ == "__main__":
    run()
    print("target parsing ok")
