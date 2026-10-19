#!/usr/bin/env python3
"""Static-only checks for a public Xiaomi Pad 5 Linux source DTS.

This intentionally does not parse cpp-expanded FDT or prove U-Boot hardware
compatibility. It catches accidental use of an SM8150 MTP reference board
and incorrect USB device roles before attempting host compilation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

SOURCE = ("SeimoDev/linux-xiaomi-nabu",
          "4e6d08bb1b467c721e19cd693e4ec7388d982d73")
MAX_DTS = 512 * 1024


def block(text: str, label: str) -> str:
    match = re.search(r"&"+re.escape(label)+r"\s*\{", text)
    if not match:
        raise ValueError(f"Missing &{label} DTS block")
    start = match.end()
    depth = 1
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i]
    raise ValueError(f"Unterminated &{label} DTS block")


def prop(source: str, key: str, value: str) -> bool:
    return bool(re.search(
        r"\b" + re.escape(key) + r"\s*=\s*" +
        re.escape('"'+value+'"') + r"\s*;",source,
    ))


def inspect(dts: str) -> dict:
    if not 512 < len(dts) <= MAX_DTS:
        raise ValueError("Public nabu DTS size outside expected bounds")
    if not re.search(r'compatible\s*=\s*"xiaomi,nabu"\s*,\s*"qcom,sm8150"\s*;', dts):
        raise ValueError("DTS must explicitly identify Xiaomi Pad 5 / SM8150")
    if '#include "sm8150.dtsi"' not in dts:
        raise ValueError("Missing SM8150 SoC include")
    if '#include "sm8150-wcd9340.dtsi"' not in dts:
        raise ValueError("Missing public nabu audio platform include")
    controller = block(dts,"usb_1")
    usb1 = block(dts,"usb_1_dwc3")
    usb2 = block(dts,"usb_2_dwc3")
    if not prop(controller,"status","okay"):
        raise ValueError("USB1 controller must be enabled in public DTS")
    if not prop(usb1,"dr_mode","otg"):
        raise ValueError("nabu USB1 has an OTG controller, not MTP peripheral-only")
    if not prop(usb1,"maximum-speed","high-speed"):
        raise ValueError("nabu USB1 is limited to high-speed")
    if not re.search(r"\bphys\s*=\s*<&usb_1_hsphy>\s*;",usb1):
        raise ValueError("nabu USB1 requires HS PHY, not the MTP QMP setup")
    if not prop(usb2,"dr_mode","host"):
        raise ValueError("nabu USB2 is host-only in public Linux DTS")
    return {
        "schema":"ios-nabu-stage8-public-dts-source-contract-v1",
        "source_repo":SOURCE[0],
        "source_commit":SOURCE[1],
        "target_board":"xiaomi,nabu",
        "soc":"qcom,sm8150",
        "usb1_role_from_linux_dts":"otg",
        "usb1_speed_from_linux_dts":"high-speed",
        "usb1_phy_from_linux_dts":"usb_1_hsphy",
        "usb2_role_from_linux_dts":"host",
        "nabu_hardware_support_in_uboot_verified":False,
        "bootloader_time_usb_init_verified":False,
        "bootable_artifact_produced":False,
        "warning":"Text-source check only; does not test or initialize USB/PMIC on device.",
    }


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source",type=Path,required=True)
    ap.add_argument("--report",type=Path,required=True)
    args=ap.parse_args(argv)
    try:
        result=inspect(args.source.read_text(encoding="utf-8"))
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    except (ValueError,OSError) as exc:
        print(f"ERROR: {exc}",file=sys.stderr)
        return 1
    print("PASS: public nabu DTS USB role/static source checks")
    print("NOT hardware validated; NOT suitable for device boot")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
