#!/usr/bin/env python3
"""Host-only review gate: pinned U-Boot v2026.07 DWC3 gadget + nabu HS PHY.

Proofs are strictly source code + compiled DTB + final Kconfig, never live
hardware or a bootable image. A passing audit is NOT permission to boot!
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "stage9" / "tools"))
sys.path.insert(0, str(ROOT / "stage4" / "tools"))
from usb_dtb_gate import inspect as usb_inspect, find_usb, USB1, USB1_WRAPPER, USB1_HSPHY
from dtb_inspect import parse_dtb

UPSTREAM_SHA = "ece349ade2973e220f524ce59e59711cc919263f"
REQUIRED_KCONFIG = (
    "CONFIG_ARCH_SNAPDRAGON",
    "CONFIG_CLK_QCOM_SM8150",
    "CONFIG_USB_DWC3",
    "CONFIG_USB_DWC3_GENERIC",
    "CONFIG_USB_DWC3_GADGET",
    "CONFIG_DM_USB_GADGET",
    "CONFIG_USB_GADGET",
    "CONFIG_USB_FUNCTION_ACM",
    "CONFIG_PHY",
    "CONFIG_PHY_QCOM_USB_SNPS_FEMTO_V2",
    "CONFIG_CONSOLE_RECORD",
    "CONFIG_FASTBOOT_CMD_OEM_CONSOLE",
)
DANGEROUS_KCONFIG = (
    "CONFIG_FASTBOOT_FLASH",
    "CONFIG_FASTBOOT_OEM_RUN",
    "CONFIG_FASTBOOT_CMD_OEM_RUN",
    "CONFIG_EFI_CAPSULE_ON_DISK",
    "CONFIG_EFI_RUNTIME_UPDATE_CAPSULE",
)
DRIVER_PATHS = (
    "drivers/usb/dwc3/dwc3-generic.c",
    "drivers/phy/qcom/phy-qcom-snps-femto-v2.c",
)


def config_values(raw: str) -> dict[str, str]:
    if len(raw) > 2_000_000:
        raise ValueError("Kconfig input too large")
    values = {}
    for line in raw.splitlines():
        line = line.strip()
        m = re.fullmatch(r"(CONFIG_[A-Z0-9_]+)=([ymn])", line)
        if m:
            key, val = m.groups()
        else:
            m = re.fullmatch(r"# (CONFIG_[A-Z0-9_]+) is not set", line)
            if not m:
                continue
            key, val = m.group(1), "n"
        if key in values:
            raise ValueError(f"Duplicate Kconfig flag {key}")
        values[key] = val
    return values


def analyze(dtb, config: str, generic: str, phy_driver: str) -> dict:
    # Reuse the separate public nabu USB DTB contract: labels, ranges,
    # effective enable status, OTG, HS PHY phandle and disabled SS PHY.
    board = usb_inspect(dtb, require_public_contract=True)
    flags = config_values(config)
    absent = [key for key in REQUIRED_KCONFIG if flags.get(key) != "y"]
    unsafe = [key for key in DANGEROUS_KCONFIG if flags.get(key) == "y"]
    if absent or unsafe:
        raise ValueError(f"U-Boot final Kconfig invalid: missing={absent}; enabled_unsafe={unsafe}")

    # Avoid regexes that can match prose comments instead of real match table
    # entries; require actual C table initializer signatures.
    qcom_glue = bool(re.search(
        r"\.compatible\s*=\s*\"qcom,dwc3\"\s*,\s*\.data\s*=\s*"
        r"\(ulong\)\s*&qcom_ops", generic
    ))
    phy_match = bool(re.search(
        r'\.compatible\s*=\s*"qcom,sm8150-usb-hs-phy"', phy_driver
    ))
    generic_otg = (
        "dr_mode == USB_DR_MODE_OTG" in generic and
        'driver = "dwc3-generic-peripheral"' in generic and
        "CONFIG_IS_ENABLED(DM_USB_GADGET)" in generic
    )
    utmi_clock = (
        '"qcom,select-utmi-as-pipe-clk"' in generic and
        "dwc3_qcom_select_utmi_clk(qscratch_base)" in generic
    )
    qscratch_writes = (
        "dwc3_qcom_vbus_override_enable(qscratch_base, true)" in generic and
        "writel" in generic and "setbits_le32" in generic
    )
    hs_phy_writes = (
        "qcom_snps_hsphy_usb_init" in phy_driver and
        "writel_relaxed(reg, base + offset)" in phy_driver and
        "reset_assert_bulk(&priv->resets)" in phy_driver
    )
    test_sources = {
        "qcom_dwc3_wrapper_fallback_match": qcom_glue,
        "otg_binds_generic_peripheral_in_driver_model": generic_otg,
        "nabu_usb2_no_superspeed_utmi_switch_in_source": utmi_clock,
        "sm8150_hsphy_binding_in_femto_v2_driver": phy_match,
        "qcom_usb_glue_performs_mmio_writes": qscratch_writes,
        "hs_phy_init_performs_mmio_and_reset_writes": hs_phy_writes,
    }
    missing_source = sorted(name for name, ok in test_sources.items() if not ok)
    if missing_source:
        raise ValueError(f"Required pinned U-Boot source pattern missing: {missing_source}")

    dwc, phys, entries = find_usb(dtb)
    usb1 = dwc[USB1]
    if usb1["wrapper_base"] != hex(USB1_WRAPPER):
        raise ValueError("Missing target nabu Qualcomm DWC3 wrapper address")
    usb_wrapper = next((n for path, n, parent, anc in entries
                        if path == usb1["path"].rsplit("/", 1)[0]), None)
    if usb_wrapper is None:
        raise ValueError("No matching primary Qualcomm wrapper")
    compat = (usb_wrapper.props.get("compatible") or b"").split(b"\0")
    if b"qcom,dwc3" not in compat:
        raise ValueError("DWC3 wrapper is missing qcom,dwc3 fallback compatible")
    if "qcom,select-utmi-as-pipe-clk" not in usb_wrapper.props:
        raise ValueError("USB2-only Qualcomm UTMI-as-PIPE clock flag missing")
    if USB1_HSPHY not in phys:
        raise ValueError("Required USB1 High-Speed PHY missing")

    return {
        "schema": "ios-nabu-stage10-uboot-usb-driver-gate-v1",
        "upstream_tag": "v2026.07",
        "upstream_commit": UPSTREAM_SHA,
        "target_device": "xiaomi,nabu",
        "board_dtb_graph_passed": board["passes_compiled_dtb_contract"],
        "required_kconfig_enabled": list(REQUIRED_KCONFIG),
        "unsafe_kconfig_disabled": list(DANGEROUS_KCONFIG),
        "source_evidence": test_sources,
        "compiled_fdt_usb1_wrapper": hex(USB1_WRAPPER),
        "compiled_fdt_hsphy": hex(USB1_HSPHY),
        "usb_1_gadget_driver_compilation_plausible": True,
        "boot_time_typec_controller_supported": None,
        "boot_time_usb_clocks_and_phy_verified": False,
        "boot_time_ram_relocation_verified": False,
        "real_usb_enumeration_in_uboot": False,
        "xnu_debug_messages_over_usb": False,
        "safe_to_boot": False,
        "warning": (
            "Source/Kconfig/DTB agreement only. Both Qualcomm generic glue "
            "and HS PHY init WRITE hardware registers and assert resets. "
            "Do not boot a host-built U-Boot or flash any partition."
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dtb", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--uboot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        config = args.config.read_text(encoding="utf-8")
        files = [(args.uboot / path).read_text(encoding="utf-8")
                 for path in DRIVER_PATHS]
        report = analyze(parse_dtb(args.dtb.read_bytes()), config, *files)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except (ValueError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print("PASS: compiled nabu DTB / pinned U-Boot USB gadget source and Kconfig")
    print("HARDWARE/MMIO NOT TESTED: safe_to_boot=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
