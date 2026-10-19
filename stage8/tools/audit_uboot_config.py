#!/usr/bin/env python3
"""Audit a *compile-only* Qualcomm U-Boot USB log experiment.

Never calls U-Boot, USB or fastboot. This reads Kconfig text generated on an
ephemeral GitHub runner. No bootable image is published; reference DTB is
sm8150-mtp, NOT Xiaomi nabu.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

UBOOT_COMMIT = "ece349ade2973e220f524ce59e59711cc919263f"
UBOOT_TAG = "v2026.07"
REFERENCE_DT = "qcom/sm8150-mtp"
REQUIRED = {
    "CONFIG_ARM",
    "CONFIG_ARCH_SNAPDRAGON",
    "CONFIG_CLK_QCOM_SM8150",
    "CONFIG_USB_GADGET",
    "CONFIG_USB_FUNCTION_FASTBOOT",
    "CONFIG_USB_FUNCTION_ACM",
    "CONFIG_CONSOLE_RECORD",
    "CONFIG_CONSOLE_RECORD_INIT_F",
    "CONFIG_FASTBOOT_CMD_OEM_CONSOLE",
}
FORBIDDEN = {
    "CONFIG_FASTBOOT_FLASH",
    "CONFIG_FASTBOOT_OEM_RUN",
    "CONFIG_FASTBOOT_CMD_OEM_RUN",
    "CONFIG_CMD_UMS",
    "CONFIG_CMD_USB_MASS_STORAGE",
    "CONFIG_CMD_DFU",
    "CONFIG_EFI_CAPSULE_ON_DISK",
    "CONFIG_EFI_RUNTIME_UPDATE_CAPSULE",
}
ALLOWED_VALUE = re.compile(r"^CONFIG_[A-Z0-9_]+=(?:y|m|n|[0-9]+|0x[0-9a-fA-F]+|\"[^\"\r\n]*\")$")
NOT_SET = re.compile(r"^# (CONFIG_[A-Z0-9_]+) is not set$")


def decode(raw: str) -> dict[str, str]:
    if len(raw) > 2_000_000:
        raise ValueError("Unreasonably large Kconfig input")
    flags = {}
    for line in raw.splitlines():
        if not line:
            continue
        disabled = NOT_SET.fullmatch(line)
        if disabled:
            name = disabled.group(1)
            value = "n"
        elif ALLOWED_VALUE.fullmatch(line):
            name, value = line.split("=", 1)
        else:
            # Ignore unrelated comments or whitespace, reject unknown
            # active Kconfig assignments.
            if line.startswith("CONFIG_"):
                raise ValueError("Malformed active Kconfig line")
            continue
        if name in flags:
            raise ValueError(f"Duplicate Kconfig symbol: {name}")
        flags[name] = value
    return flags


def audit(raw: str) -> dict:
    flags = decode(raw)
    missing = sorted(key for key in REQUIRED if flags.get(key) != "y")
    unsafe = sorted(key for key in FORBIDDEN if flags.get(key) == "y")
    if missing or unsafe:
        raise ValueError(f"U-Boot config not safe for host-only evaluation: "
                         f"required_not_enabled={missing}, prohibited_enabled={unsafe}")
    if flags.get("CONFIG_DEFAULT_DEVICE_TREE") == '"qcom/sm8150-xiaomi-nabu"':
        raise ValueError("This smoke test must not claim a nabu-specific DTS")
    return {
        "schema": "ios-nabu-stage8-uboot-compile-audit-v1",
        "upstream": "u-boot/u-boot",
        "pinned_commit": UBOOT_COMMIT,
        "release_tag": UBOOT_TAG,
        "reference_device_tree": REFERENCE_DT,
        "nabu_board_support_verified": False,
        "device_hardware_tested": False,
        "xnu_logging_supported": False,
        "usb_console_gadget_compiled": True,
        "u_boot_recorded_console_fastboot_supported": True,
        "unsafe_fastboot_flashing_enabled": False,
        "unsafe_fastboot_arbitrary_commands_enabled": False,
        "unsafe_capsule_update_enabled": False,
        "artifact_policy": "config and compile logs only; no executable U-Boot or boot.img",
        "warning": (
            "SM8150 MTP reference compile, not a Xiaomi Pad 5 port. "
            "Do not fastboot boot or flash generated U-Boot binaries."
        ),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--report", required=True, type=Path)
    args = ap.parse_args(argv)
    try:
        data = audit(args.config.read_text(encoding="utf-8"))
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(data, indent=2)+"\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1
    print("PASS: host-only USB diagnostic config (NOT nabu bootable)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
