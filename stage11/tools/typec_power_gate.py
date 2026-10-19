#!/usr/bin/env python3
"""Offline PM8150B Type-C, USB1 PHY power and U-Boot driver-coverage audit.

Input: *compiled public Linux* Xiaomi nabu DTB, pinned U-Boot v2026.07
source tree and final host-build Kconfig. Does not touch real hardware,
run the U-Boot executable or generate bootable images.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "stage4" / "tools"))
sys.path.insert(0, str(BASE / "stage9" / "tools"))
sys.path.insert(0, str(BASE / "stage10" / "tools"))
from dtb_inspect import Node, parse_dtb, strings
from usb_dtb_gate import (inspect as inspect_usb, catalog, effective_status,
                          find_usb, USB1, USB1_HSPHY)
from uboot_usb_driver_gate import config_values, UPSTREAM_SHA

SUPPLIES = {
    "vdda-pll-supply": 880_000,
    "vdda18-supply": 1_800_000,
    "vdda33-supply": 3_072_000,
}
TYPEC = "qcom,pm8150b-typec"
VBUS = "qcom,pm8150b-vbus-reg"
CONNECTOR = "usb-c-connector"


def one_word(node: Node, key: str) -> int:
    value = node.props.get(key)
    if value is None or len(value) != 4:
        raise ValueError(f"Required single 32-bit DTB property absent/invalid: {key}")
    return int.from_bytes(value, "big")


def optional_word(node: Node, key: str) -> int | None:
    value = node.props.get(key)
    if value is None:
        return None
    if len(value) != 4:
        raise ValueError(f"Malformed DTB property: {key}")
    return int.from_bytes(value, "big")


def inventory(root: Node):
    entries = catalog(root)
    handles = {}
    for path, node, parent, ancestors in entries:
        for name in ("phandle", "linux,phandle"):
            if name in node.props:
                n = one_word(node, name)
                if not n:
                    raise ValueError("Zero FDT phandle")
                if n in handles and handles[n][0] != path:
                    raise ValueError("Duplicate FDT phandle")
                handles[n] = (path, node, ancestors)
    return entries, handles


def sole_compatible(entries, needle: str):
    found = [(p, n, a) for p,n,parent,a in entries
             if needle in strings(n.props.get("compatible"))]
    if len(found) != 1:
        raise ValueError(f"Expected exactly one {needle} node, got {len(found)}")
    path, node, ancestors = found[0]
    if not effective_status(node, ancestors):
        raise ValueError(f"Required {needle} node or ancestor is disabled")
    return path, node, ancestors


def supply_phandle(node: Node, key: str, handles: dict):
    ident = one_word(node, key)
    if ident not in handles:
        raise ValueError(f"Unresolved supply reference {key}")
    path, provider, ancestors = handles[ident]
    if not effective_status(provider, ancestors):
        raise ValueError(f"Disabled supply provider for {key}")
    return ident, provider


def resolve_specs(node: Node, property: str, width_property: str,
                  handles: dict, minimum: int, maximum: int) -> int:
    """Validate DTB phandle+args clock/reset/power specs without reading MMIO."""
    raw = node.props.get(property)
    if raw is None or len(raw) == 0 or len(raw) % 4:
        raise ValueError(f"Absent/truncated FDT {property} specifiers")
    words = [int.from_bytes(raw[i:i+4], "big") for i in range(0, len(raw), 4)]
    at = 0
    count = 0
    while at < len(words):
        key = words[at]
        at += 1
        if key not in handles:
            raise ValueError(f"Unresolved {property} provider phandle")
        path, provider, ancestors = handles[key]
        if not effective_status(provider, ancestors):
            raise ValueError(f"Disabled {property} provider")
        args = one_word(provider, width_property)
        if args > 3 or at + args > len(words):
            raise ValueError(f"Malformed {property} provider argument count")
        at += args
        count += 1
        if count > maximum:
            raise ValueError(f"Too many {property} dependencies")
    if count < minimum:
        raise ValueError(f"Not enough {property} dependencies")
    return count


def validate_clocks_and_resets(root: Node, entries, handles, usb_path: str,
                               phy_path: str) -> dict:
    nodes = {path:node for path,node,parent,ancestors in entries}
    dwc = nodes[usb_path]
    wrapper = nodes.get(usb_path.rsplit("/", 1)[0])
    hs_phy = nodes[phy_path]
    if wrapper is None:
        raise ValueError("DWC3 Qualcomm USB wrapper missing")

    expected_names = ["cfg_noc", "core", "iface", "sleep", "mock_utmi", "xo"]
    if strings(wrapper.props.get("clock-names")) != expected_names:
        raise ValueError("Unexpected USB1 Qualcomm wrapper clock-names")
    wrapper_clocks = resolve_specs(wrapper,"clocks","#clock-cells",
                                   handles,minimum=6,maximum=6)
    wrapper_resets = resolve_specs(wrapper,"resets","#reset-cells",
                                   handles,minimum=1,maximum=1)
    power_domains = resolve_specs(wrapper,"power-domains",
                                  "#power-domain-cells",handles,1,1)
    if strings(hs_phy.props.get("clock-names")) != ["ref"]:
        raise ValueError("USB1 HS PHY needs the declared ref clock")
    hs_clock = resolve_specs(hs_phy,"clocks","#clock-cells",
                             handles,1,1)
    hs_reset = resolve_specs(hs_phy,"resets","#reset-cells",
                             handles,1,1)
    # Frequency constraints in the public DTS are NOT readings.
    assigned = resolve_specs(wrapper,"assigned-clocks","#clock-cells",
                             handles,2,2)
    rates = wrapper.props.get("assigned-clock-rates")
    if rates is None or len(rates) != 8 or [
        int.from_bytes(rates[i:i+4], "big") for i in (0,4)
    ] != [19_200_000, 200_000_000]:
        raise ValueError("USB1 assigned-clock-rates do not match pinned DTS")
    return {
        "usb1_wrapper_clocks_declared": wrapper_clocks,
        "usb1_wrapper_resets_declared": wrapper_resets,
        "usb1_wrapper_power_domains_declared": power_domains,
        "usb1_phy_reference_clocks_declared": hs_clock,
        "usb1_phy_resets_declared": hs_reset,
        "usb1_wrapper_assigned_clocks_declared": assigned,
        "usb1_declared_19m2_and_200m_clock_rates": True,
        "actual_clock_reset_and_power_state_verified": False,
    }


def verify_typec_graph(entries, handles, usb_path: str, typec_path: str) -> None:
    # The public nabu DTS ties USB1's HS endpoint to the PM8150B Type-C
    # role-switch endpoint in both directions.
    usb_prefix = usb_path.rstrip("/") + "/"
    typec_prefix = typec_path.rstrip("/") + "/"
    usb_eps = [(p,n) for p,n,parent,a in entries
               if p.startswith(usb_prefix) and
               n.name.startswith("endpoint") and
               "remote-endpoint" in n.props]
    typec_eps = [(p,n) for p,n,parent,a in entries
                 if p.startswith(typec_prefix) and
                 n.name.startswith("endpoint") and
                 "remote-endpoint" in n.props]
    if not usb_eps or not typec_eps:
        raise ValueError("USB1 or PM8150B Type-C role graph endpoint missing")
    for upath, unode in usb_eps:
        uhandle = optional_word(unode, "phandle")
        remote_id = one_word(unode, "remote-endpoint")
        mapped = handles.get(remote_id)
        if mapped is None or not mapped[0].startswith(typec_prefix):
            continue
        for tpath, tnode in typec_eps:
            if tpath != mapped[0] or uhandle is None:
                continue
            if one_word(tnode, "remote-endpoint") != uhandle:
                raise ValueError("Type-C role graph is not bidirectional")
            return
    raise ValueError("No USB1 <-> PM8150B Type-C endpoint pair")


def validate_board(root: Node) -> dict:
    # Reuse Stage 9 hardening for the exact nabu USB2-only PHY and
    # 0xa600000 OTG core; do not assume any controller is actually on.
    usb = inspect_usb(root, require_public_contract=True)
    dwc, phys, usb_entries = find_usb(root)
    entries, handles = inventory(root)
    tpath, tnode, tanc = sole_compatible(entries, TYPEC)
    vpath, vnode, vanc = sole_compatible(entries, VBUS)
    cpath, connector, canc = sole_compatible(entries, CONNECTOR)
    if not cpath.startswith(tpath.rstrip("/") + "/"):
        raise ValueError("USB-C connector must be a child of PM8150B Type-C")
    for key in ("power-role", "data-role"):
        if strings(connector.props.get(key)) != ["dual"]:
            raise ValueError(f"USB-C connector must declare dual {key}")
    if not ("usb-role-switch" in next(
        node.props for path,node,parent,anc in entries if path == dwc[USB1]["path"]
    )):
        raise ValueError("USB1 must declare usb-role-switch")

    phy_path = phys[USB1_HSPHY]["path"]
    hs_phy = next(n for p,n,parent,anc in entries if p == phy_path)
    power = {}
    for key, expected_uv in SUPPLIES.items():
        ident, provider = supply_phandle(hs_phy, key, handles)
        minimum = optional_word(provider, "regulator-min-microvolt")
        maximum = optional_word(provider, "regulator-max-microvolt")
        if minimum is None or maximum is None or not minimum <= expected_uv <= maximum:
            raise ValueError(f"HS PHY {key} must resolve to expected voltage limits")
        power[key] = {"expected_microvolts": expected_uv,
                      "declared_voltage_limits_valid": True}

    # The PM8150B PD PHY uses the same L2 3.072V board rail.
    pd_handle, pd_supply = supply_phandle(tnode, "vdd-pdphy-supply", handles)
    if pd_handle != one_word(hs_phy, "vdda33-supply"):
        raise ValueError("PM8150B PD PHY must reference the expected L2 rail")
    # VBUS is available in the board's device tree, but this does NOT
    # authorize toggling its PMIC source regulator in peripheral mode.
    verify_typec_graph(entries, handles, dwc[USB1]["path"], tpath)
    clock_reset = validate_clocks_and_resets(
        root, entries, handles, dwc[USB1]["path"], phy_path)
    return {
        "clock_reset": clock_reset,
        "usb1_otg_hsphy_dtb_contract": bool(usb["passes_compiled_dtb_contract"]),
        "pm8150b_typec_enabled_in_public_dtb": True,
        "pm8150b_vbus_source_regulator_enabled_in_public_dtb": True,
        "usb_c_connector_dual_power_and_data_roles": True,
        "usb1_hs_to_pm8150b_role_graph_reciprocal": True,
        "usb1_phy_supply_constraints": power,
        "pm8150b_pdphy_shares_usb1_phy_3v072_supply": True,
    }


def analyze(root: Node, config: str, tcpm_make: str, tcpm_sources: str,
            pmic_vbus_driver: str, hs_phy_driver: str) -> dict:
    board = validate_board(root)
    flags = config_values(config)

    if "obj-$(CONFIG_TYPEC_FUSB302) += fusb302.o" not in tcpm_make:
        raise ValueError("Unexpected pinned U-Boot Type-C driver build rules")
    vbus_match = bool(re.search(r'\.compatible\s*=\s*"qcom,pm8150b-vbus-reg"',
                                pmic_vbus_driver))
    vbus_writes = ("pmic_clrsetbits(" in pmic_vbus_driver
                   and "qcom_usb_vbus_regulator_probe" in pmic_vbus_driver)
    if not vbus_match or not vbus_writes:
        raise ValueError("Expected PM8150B VBUS source driver/writes not found")

    typec_compat_match = bool(re.search(
        r'\.compatible\s*=\s*"qcom,pm8150b-typec"', tcpm_sources
    ))
    if re.search(r'\.compatible\s*=\s*"qcom,pm8150b-typec"',
                 pmic_vbus_driver):
        typec_compat_match = True

    # The 2026.07 Synopsys HS PHY source does not explicitly request the
    # LDO supplies named in the public DTS. An independent clock/PMIC
    # bring-up path may exist; this check cannot assert the rails are off.
    phy_explicit_regulator_lookup = bool(re.search(
        r"\b(regulator_get|regulator_set_enable|devm_regulator_get|"
        r"device_get_supply_regulator)\s*\(", hs_phy_driver
    ))
    if "reset_assert_bulk(&priv->resets)" not in hs_phy_driver:
        raise ValueError("Unexpected HS PHY reset path, review code again")
    if "writel_relaxed(reg, base + offset)" not in hs_phy_driver:
        raise ValueError("Expected HS PHY MMIO setup not visible")

    unresolved = [
        "PM8150B Type-C/CC/PD driver for the nabu port is not validated",
        "USB gadget's role/CC/VBUS and PHY supply state at ABL entry unknown",
        "HS PHY regulator rail initialization path not verified on nabu",
        "U-Boot memory relocation and recovery path at ABL entry unknown",
        "XNU needs a logger that survives U-Boot handoff",
    ]
    if not typec_compat_match:
        unresolved.insert(0, "No qcom,pm8150b-typec compatible match in inspected U-Boot TCPM/PMIC C sources")

    return {
        "schema": "ios-nabu-stage11-typec-power-host-audit-v1",
        "device": "xiaomi,nabu",
        "uboot_pinned_commit": UPSTREAM_SHA,
        "source_kind": "pinned public board DTB and pinned U-Boot C files",
        "dtb": board,
        "uboot": {
            "typec_pm8150b_driver_match_in_inspected_source": typec_compat_match,
            "typec_tcpm_kconfig": flags.get("CONFIG_TYPEC_TCPM", "unknown"),
            "typec_fusb302_kconfig": flags.get("CONFIG_TYPEC_FUSB302", "unknown"),
            "pm8150b_vbus_regulator_driver_source_present": vbus_match,
            "pm8150b_vbus_regulator_final_kconfig": flags.get(
                "CONFIG_DM_REGULATOR_QCOM_USB_VBUS", "unknown"),
            "pm8150b_vbus_driver_writes_spmi": vbus_writes,
            "rpmh_regulator_final_kconfig": flags.get(
                "CONFIG_DM_REGULATOR_QCOM_RPMH", "unknown"),
            "hs_phy_driver_explicit_regulator_lookup": phy_explicit_regulator_lookup,
            "hs_phy_reset_and_mmio_writes_require_review": True,
        },
        "unresolved": unresolved,
        "android_usb1_enumeration_proven_by_this_audit": False,
        "abl_usb1_enumeration_proven": False,
        "bootloader_ram_safety_proven": False,
        "xnu_usb_logging_proven": False,
        "safe_to_boot": False,
        "decision": "blocked-until-runtime-evidence",
    }


def read_usb_typec_sources(uboot: Path) -> str:
    # Static pinned USB/PMIC source; nothing from the user's filesystem.
    # Names/paths are not exported, and source is not embedded in the report.
    result = []
    count = 0
    for directory in (uboot / "drivers/usb/tcpm", uboot / "drivers/power/pmic"):
        for path in sorted(directory.glob("*.c")):
            count += 1
            if count > 400 or path.stat().st_size > 1_000_000:
                raise ValueError("Unexpected U-Boot source inventory size")
            result.append(path.read_text(encoding="utf-8"))
    if count < 2:
        raise ValueError("Missing Type-C/PMIC source tree")
    return "\n".join(result)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dtb", required=True, type=Path)
    ap.add_argument("--uboot", required=True, type=Path)
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    try:
        uboot = args.uboot
        report = analyze(
            parse_dtb(args.dtb.read_bytes()),
            args.config.read_text(encoding="utf-8"),
            (uboot / "drivers/usb/tcpm/Makefile").read_text(encoding="utf-8"),
            read_usb_typec_sources(uboot),
            (uboot / "drivers/power/regulator/qcom_usb_vbus_regulator.c").read_text(encoding="utf-8"),
            (uboot / "drivers/phy/qcom/phy-qcom-snps-femto-v2.c").read_text(encoding="utf-8"),
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except (ValueError, OSError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1
    print("PASS: public Type-C/PHY/PMIC dependency audit produced")
    print("Device boot decision:", report["decision"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
