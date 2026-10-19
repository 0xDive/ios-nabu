#!/usr/bin/env python3
"""Stage 9: offline DWC3/USB2 PHY topology audit for Xiaomi Pad 5 (nabu).

Reads a compiled *public Linux* nabu DTB or privately held Android DTB.
Reports only hardware topology; raw DTB, serials, MACs, firmware and bootargs
are never exported. This is NOT a U-Boot USB driver probe or a safe-to-boot
test: controller clocks, Type-C voltage/role and ABL allocations are unknown.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "stage4" / "tools"))
from dtb_inspect import Node, parse_dtb, strings

USB1 = 0x0A600000
USB2 = 0x0A800000
USB1_HSPHY = 0x088E2000
USB1_SS_PHY = 0x088E8000
USB1_WRAPPER = 0x0A6F8800
KNOWN_BASES = (USB1, USB2)


def u32(raw: bytes | None, default: int) -> int:
    if raw is None:
        return default
    if len(raw) != 4:
        raise ValueError("Malformed DTB address/size-cell descriptor")
    num = int.from_bytes(raw, "big")
    if num not in (1, 2):
        raise ValueError("Unsupported DTB address/size-cell width")
    return num


def reg_start(node: Node, parent: Node) -> int | None:
    """Decode the first MMIO reg tuple using its parent's address cells."""
    raw = node.props.get("reg")
    if raw is None:
        return None
    address_cells = u32(parent.props.get("#address-cells"), 2)
    size_cells = u32(parent.props.get("#size-cells"), 2)
    stride = 4 * (address_cells + size_cells)
    if len(raw) < stride or len(raw) % stride:
        raise ValueError("Truncated or malformed DWC3/PHY reg")
    addr = int.from_bytes(raw[:4 * address_cells], "big")
    size = int.from_bytes(raw[4 * address_cells:stride], "big")
    if not size or addr + size > (1 << 64):
        raise ValueError("Invalid or overflowing MMIO reg")
    return addr


def catalog(root: Node) -> list[tuple[str, Node, Node | None, tuple[Node, ...]]]:
    result = []
    def descend(n: Node, path: str, parent: Node | None, ancestors: tuple[Node, ...]):
        if len(result) >= 30000 or len(ancestors) >= 96:
            raise ValueError("Device tree exceeds expected node/depth limits")
        result.append((path, n, parent, ancestors))
        for child in n.children:
            descend(child, path.rstrip("/") + "/" + child.name, n, ancestors + (n,))
    descend(root, "/", None, ())
    return result


def effective_status(node: Node, ancestors: tuple[Node, ...]) -> bool:
    # A disabled wrapper cannot magically be enabled by an active DWC3 child.
    for item in ancestors + (node,):
        status = strings(item.props.get("status"))
        if status and status[0] not in ("okay", "ok"):
            return False
    return True


def find_usb(root: Node) -> tuple[dict[int, dict], dict[int, dict], list]:
    entries = catalog(root)
    dwc = {}
    phy = {}
    for path, node, parent, ancestors in entries:
        if parent is None:
            continue
        compat = strings(node.props.get("compatible"))
        is_dwc = "snps,dwc3" in compat
        is_phy = node.name.startswith(("phy@", "hsphy@", "ssphy@")) and (
            "phy" in " ".join(compat) or "hsphy" in node.name or "ssphy" in node.name
        )
        if not is_dwc and not is_phy:
            continue
        address = reg_start(node, parent)
        if address is None:
            continue
        if is_dwc and address in KNOWN_BASES:
            if address in dwc:
                raise ValueError(f"Multiple DWC3 nodes at {address:#x}")
            wrapper_addr = reg_start(parent, ancestors[-1]) if ancestors else None
            dwc[address] = {
                "path": path, "active": effective_status(node, ancestors),
                "mode": (strings(node.props.get("dr_mode")) or ["unspecified"])[0],
                "maximum_speed": (strings(node.props.get("maximum-speed")) or ["unspecified"])[0],
                "phy_names": strings(node.props.get("phy-names")),
                "phys_cells": list(struct.unpack(">" + "I" * (len(node.props["phys"]) // 4),
                                           node.props["phys"])) if node.props.get("phys") and
                                           len(node.props["phys"]) % 4 == 0 else [],
                "usb_role_switch": "usb-role-switch" in node.props,
                "wrapper_base": hex(wrapper_addr) if wrapper_addr is not None else None,
                "wrapper_compatible": strings(parent.props.get("compatible")),
            }
        elif is_phy and address in (USB1_HSPHY, USB1_SS_PHY):
            if address in phy:
                raise ValueError(f"Duplicate PHY at {address:#x}")
            h = node.props.get("phandle", node.props.get("linux,phandle"))
            if h is not None and len(h) != 4:
                raise ValueError("Malformed USB PHY phandle")
            n = node.props.get("#phy-cells")
            if n is not None and len(n) != 4:
                raise ValueError("Malformed USB PHY #phy-cells")
            phy[address] = {
                "path": path,
                "active": effective_status(node, ancestors),
                "phandle": int.from_bytes(h, "big") if h else None,
                "phy_cells": int.from_bytes(n, "big") if n else None,
                "compatible": compat[:3],
            }
    return dwc, phy, entries


def inspect(root: Node, *, require_public_contract: bool) -> dict:
    model = " ".join(strings(root.props.get("model"))).lower()
    compat = strings(root.props.get("compatible"))
    if "qcom,sm8150" not in compat or not ("xiaomi,nabu" in compat or "nabu" in model):
        raise ValueError("USB report source is not a nabu / SM8150 DTB")

    dwc, phy, entries = find_usb(root)
    if any(addr not in dwc for addr in KNOWN_BASES):
        raise ValueError("Both primary and secondary DWC3 nodes must be present")
    first, second = dwc[USB1], dwc[USB2]
    hs = phy.get(USB1_HSPHY)
    ss = phy.get(USB1_SS_PHY)
    if first["mode"] not in ("otg", "peripheral"):
        raise ValueError("USB1 must support a device/OTG role")
    if second["mode"] != "host":
        raise ValueError("USB2 must remain host-only")
    if not first["active"] or not second["active"]:
        raise ValueError("DWC3 wrapper/child status not enabled")

    if require_public_contract:
        if first["mode"] != "otg":
            raise ValueError("nabu public DT requires USB1 OTG")
        if first["maximum_speed"] != "high-speed":
            raise ValueError("nabu USB1 must be limited to USB2 high-speed")
        if first["phy_names"] != ["usb2-phy"]:
            raise ValueError("nabu USB1 must not use MTP's SuperSpeed QMP PHY")
        if not first["usb_role_switch"]:
            raise ValueError("nabu USB1 must declare an OTG role switch")
        if first["wrapper_base"] != hex(USB1_WRAPPER):
            raise ValueError("Invalid Qualcomm primary USB wrapper base")
        if not hs or not hs["active"]:
            raise ValueError("USB1 HS PHY missing or disabled")
        if hs["phy_cells"] != 0 or hs["phandle"] is None:
            raise ValueError("USB1 HS PHY phandle or #phy-cells not valid")
        if first["phys_cells"] != [hs["phandle"]]:
            raise ValueError("USB1 phys must reference exactly the primary HS PHY")
        if ss is not None and ss["active"]:
            raise ValueError("USB1 SuperSpeed PHY must not be enabled")
    return {
        "schema": "ios-nabu-stage9-usb-dtb-readonly-v1",
        "device": "xiaomi,nabu",
        "report_kind": "public-dtb-bootloader-configuration" if require_public_contract
                      else "running-android-vendor-dtb",
        "usb1": {
            "controller_base": hex(USB1), "wrapper_base": first["wrapper_base"],
            "role": first["mode"], "maximum_speed": first["maximum_speed"],
            "phy_names": first["phy_names"], "phy_reference_cells": len(first["phys_cells"]),
            "role_switch_declared": first["usb_role_switch"],
            "usb2_hsphy_base": hex(USB1_HSPHY), "usb2_hsphy_active": hs["active"] if hs else None,
            "super_speed_phy_active": ss["active"] if ss else None,
        },
        "usb2": {
            "controller_base": hex(USB2),
            "role": second["mode"], "maximum_speed": second["maximum_speed"],
            "role_switch_declared": second["usb_role_switch"],
        },
        "unresolved_gates": [
            "ABL-time clocks and PHY resets", "PM8150B Type-C role/CC state",
            "USB device enumeration from bare metal", "TrustZone/SMMU and ABL RAM map",
            "How logs cross the U-Boot to XNU handoff",
        ],
        "passes_compiled_dtb_contract": bool(require_public_contract),
        "actual_usb_logging_proven": False,
        "safe_to_boot": False,
        "note": "Read-only DTB metadata, not a driver, PHY test, or executable image.",
    }


def compare(compiled: dict, android: dict) -> dict:
    if compiled["report_kind"] != "public-dtb-bootloader-configuration":
        raise ValueError("First input must pass the compiled nabu contract")
    if android["report_kind"] != "running-android-vendor-dtb":
        raise ValueError("Second input must be a vendor DTB inspection")
    changes = []
    for controller in ("usb1", "usb2"):
        for key in ("role", "maximum_speed", "role_switch_declared", "phy_names"):
            if key in compiled[controller] and key in android[controller] and (
                compiled[controller][key] != android[controller][key]
            ):
                changes.append({
                    "controller": controller, "property": key,
                    "compiled_public": compiled[controller][key],
                    "running_android": android[controller][key],
                })
    return {
        "schema": "ios-nabu-stage9-usb-compare-v1",
        "differences": changes,
        "source_fdt_same_as_abl": False,
        "bootloader_usb_initialized": False,
        "safe_to_boot": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dtb", type=Path, required=True, help="Local FDT only")
    parser.add_argument("--kind", choices=["public", "android"], required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = inspect(parse_dtb(args.dtb.read_bytes()),
                         require_public_contract=args.kind == "public")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except (ValueError, OSError, struct.error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("PASS:", result["report_kind"])
    print("Still NOT safe to boot or initialize USB hardware")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
