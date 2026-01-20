#!/usr/bin/env python3
"""Minimal self-test for external HTTP URL selection."""

import os
import sys

sys.path.append(os.path.dirname(__file__))

from uxi_core_exporter import get_external_http_url


def run() -> None:
    cfg = {
        "services": {
            "external": [{"name": "Example", "target": "example.com", "tests": ["http"]}]
        }
    }
    assert get_external_http_url(cfg) == "https://example.com"

    cfg2 = {"external_http": {"url": "https://custom.example.org"}}
    assert get_external_http_url(cfg2) == "https://custom.example.org"

    cfg3 = {
        "targets": {
            "external": {
                "http": [{"name": "Legacy", "target": "https://legacy.example.com"}]
            }
        }
    }
    assert get_external_http_url(cfg3) == "https://legacy.example.com"


if __name__ == "__main__":
    run()
    print("external http url ok")
