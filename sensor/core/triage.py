#!/usr/bin/env python3
"""Lightweight triage helpers for UXI-Lite sensor."""

from __future__ import annotations

import shutil
import subprocess
import time
import urllib.parse
from typing import Dict, Optional, List


def _format_output(
    cmd: List[str],
    returncode: int,
    stdout: str,
    stderr: str,
    duration_ms: int,
    timed_out: bool,
) -> str:
    """Format command execution output.

    Args:
        cmd: Command list executed.
        returncode: Process return code.
        stdout: Standard output captured.
        stderr: Standard error captured.
        duration_ms: Duration in milliseconds.
        timed_out: Whether the command timed out.

    Returns:
        Formatted command output string.
    """
    header = (
        f"cmd={' '.join(cmd)}\n"
        f"rc={returncode} duration_ms={duration_ms} timed_out={timed_out}\n"
    )
    return header + "stdout:\n" + stdout + "\nstderr:\n" + stderr


def _run_command(cmd: List[str], timeout_s: int) -> str:
    """Run a command with timeout and return formatted output.

    Args:
        cmd: Command list to execute.
        timeout_s: Timeout in seconds.

    Returns:
        Formatted command output string.
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
        return _format_output(
            cmd,
            proc.returncode,
            proc.stdout or "",
            proc.stderr or "",
            duration_ms,
            False,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        return _format_output(
            cmd,
            124,
            (exc.stdout or "") if exc.stdout else "",
            (exc.stderr or "") if exc.stderr else "",
            duration_ms,
            True,
        )


def _target_host(target: str) -> Optional[str]:
    """Extract a hostname from a URL or raw target.

    Args:
        target: URL or hostname/IP.

    Returns:
        Hostname/IP if available.
    """
    parsed = urllib.parse.urlparse(target)
    if parsed.scheme and parsed.hostname:
        return parsed.hostname
    return target if target else None


def collect_triage(external_target: Optional[str], include_traceroute: bool) -> Dict[str, str]:
    """Collect lightweight diagnostics when a step fails.

    Args:
        external_target: URL or host for traceroute.
        include_traceroute: Whether to run traceroute.

    Returns:
        Dict of triage outputs keyed by command name.
    """
    triage: Dict[str, str] = {}
    triage["nmcli_dev_status"] = _run_command(["nmcli", "dev", "status"], 5)
    triage["ip_route"] = _run_command(["ip", "route"], 5)

    if shutil.which("resolvectl"):
        triage["resolvectl_status"] = _run_command(["resolvectl", "status"], 5)
    else:
        triage["resolv_conf"] = _run_command(["cat", "/etc/resolv.conf"], 3)

    if include_traceroute and external_target:
        host = _target_host(external_target)
        if host:
            triage["traceroute"] = _run_command(["traceroute", "-n", host], 15)

    return triage
