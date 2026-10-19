#!/usr/bin/env python3
"""Collect a sanitized, read-only *Android runtime* UART status report.

No root is required for basic data. Optional --root uses KernelSU/su only to
READ already-mounted debugfs files. Never mounts debugfs, changes pinmux/clock,
writes registers, reads bootargs, or exports raw kernel logs or identifiers.
Android runtime values do not establish what ABL leaves enabled.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

PIN_NAMES = ("gpio85", "gpio86")
PIN_NUMBER_RE = re.compile(r"\b(?:pin\s+)?(?:85|86)\b", re.IGNORECASE)
CLK_RE = re.compile(r"qupv3|qup.*s4|geni", re.IGNORECASE)
TTY_RE = re.compile(r"^(?:ttyMSM|ttyHS|ttyGS|ttyS)[0-9]{1,3}$")
SAFE_DIR_RE = re.compile(r"^[A-Za-z0-9_.:@-]{1,100}$")
MAX_TEXT = 2 * 1024 * 1024


def run(args, timeout=12):
    return subprocess.run(args, capture_output=True, text=True, errors="replace",
                          timeout=timeout, check=False)


def collect(adb="adb", *, root=False, invoke=run) -> dict:
    def call(args):
        try:
            result = invoke([adb] + args)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        # Drop any output beyond a strict in-memory bound.
        value = result.stdout
        if len(value) > MAX_TEXT:
            return None
        return value

    devices = call(["devices"])
    if devices is None:
        raise ValueError("ADB is unavailable")
    connected = [
        line for line in devices.splitlines()
        if re.fullmatch(r"[^\s]+\s+device", line.strip())
    ]
    if len(connected) != 1:
        raise ValueError("Exactly one authorized ADB device is required")
    product = (call(["shell", "getprop", "ro.product.device"]) or "").strip()
    if product != "nabu":
        raise ValueError("Connected product is not nabu")

    def read(path):
        if root:
            # Command/path literals originate only from our allowlisted paths.
            return call(["shell", "su", "-c", "cat " + path])
        return call(["shell", "cat", path])

    consoles_raw = read("/proc/consoles")
    consoles = []
    if consoles_raw:
        for line in consoles_raw.splitlines():
            name = line.split()[0] if line.split() else ""
            if name.startswith(("ttyMSM", "ttyHS", "ttyS", "ttyGS")):
                consoles.append(name[:32])
    consoles = sorted(set(consoles))

    tty_raw = call(["shell", "ls", "/sys/class/tty"])
    tty = sorted({part for part in (tty_raw or "").split()
                  if TTY_RE.fullmatch(part)})[:40]

    clk_raw = read("/sys/kernel/debug/clk/clk_summary")
    clocks = []
    if clk_raw is not None:
        for line in clk_raw.splitlines():
            if not CLK_RE.search(line):
                continue
            fields = line.split()
            if not fields:
                continue
            name = fields[0]
            if not SAFE_DIR_RE.fullmatch(name):
                continue
            # clk_summary columns: enable, prepare, protect, rate etc.
            # Only the first three numeric columns are exported. No raw dump.
            numeric = []
            for field in fields[1:4]:
                if field.isdigit():
                    numeric.append(int(field))
            clocks.append({"name": name, "first_numeric_fields": numeric})
            if len(clocks) >= 48:
                break

    pin_states = []
    folders = call(["shell", "ls", "/sys/kernel/debug/pinctrl"])
    if folders is not None:
        for folder in folders.split():
            if not SAFE_DIR_RE.fullmatch(folder):
                continue
            candidate = f"/sys/kernel/debug/pinctrl/{folder}/pinmux-pins"
            raw = read(candidate)
            if raw is None:
                continue
            for line in raw.splitlines():
                if not (any(pin in line.lower() for pin in PIN_NAMES) or
                        PIN_NUMBER_RE.search(line)):
                    continue
                # Re-emit bounded, strictly printable GPIO/owner hints only.
                short = re.sub(r"[^A-Za-z0-9 _.,:()/@+-]", "", line)[:160]
                if short:
                    pin_states.append(short)
                if len(pin_states) >= 24:
                    break
            if len(pin_states) >= 24:
                break

    return {
        "schema": "ios-nabu-stage7-android-uart-status-v1",
        "device": "nabu",
        "read_only": True,
        "root_used": root,
        "source": "currently running Android, NOT Qualcomm ABL or XNU",
        "consoles_with_uart_like_names": consoles,
        "uart_like_tty_devices": tty,
        "filtered_qup_clock_rows": clocks,
        "filtered_gpio85_86_pinctrl_lines": pin_states,
        "clock_debugfs_readable": clk_raw is not None,
        "pinmux_debugfs_readable": folders is not None and bool(pin_states),
        "early_uart_output_confirmed": False,
        "exposed_debug_pads_confirmed": False,
        "warnings": [
            "Missing debugfs data is UNKNOWN, not proof a UART is off.",
            "An Android ttyMSM console is not evidence of access at ABL handoff.",
            "No GPIO writes, MMIO register reads/writes, mounts or raw bootargs/dmesg.",
            "Never attach a serial adapter to unidentified contacts.",
        ]
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--adb", default="adb", help="Path to Android platform-tools adb")
    p.add_argument("--root", action="store_true", help="Use su for read-only debugfs")
    p.add_argument("--out", type=Path, required=True, help="Local, sanitized JSON")
    args = p.parse_args(argv)
    if shutil.which(args.adb) is None:
        p.exit(1, "ERROR: adb executable not found\n")
    try:
        report = collect(args.adb, root=args.root)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n",
                            encoding="utf-8")
    except (OSError, ValueError) as exc:
        p.exit(1, f"ERROR: {exc}\n")
    print("Saved sanitized Android-only UART report:", args.out)
    print("Clock info readable:", report["clock_debugfs_readable"])
    print("UART tty names:", report["uart_like_tty_devices"])
    print("NOT evidence of an accessible UART at bootloader entry.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
