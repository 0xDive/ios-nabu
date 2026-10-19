#!/usr/bin/env python3
"""Offline, read-only Xiaomi nabu GENI UART inventory from a *local* Linux DTB.

Exports only controller/pinctrl/clock/IRQ topology, not bootargs, identifiers,
calibration, MACs, serial numbers, addresses of personal memory dumps, etc.
An Android DTB is NOT proof of ABL-time clock or pin state.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "stage4" / "tools"))
from dtb_inspect import Node, parse_dtb, strings

UART_COMPAT = frozenset({
    "qcom,msm-geni-console", "qcom,msm-geni-serial-hs",
    "qcom,geni-debug-uart", "qcom,geni-uart",
})
TARGET_BASE = 0x00A90000
MAX_CONTROLLERS = 32


def cells(raw: bytes | None) -> list[int]:
    if raw is None:
        return []
    if len(raw) % 4:
        raise ValueError("Bad cell-encoded DTB property")
    return list(struct.unpack(">" + "I" * (len(raw) // 4), raw))


def cell_count(parent: Node, property: str, fallback: int) -> int:
    parts = cells(parent.props.get(property))
    if not parts:
        return fallback
    if len(parts) != 1 or not 0 <= parts[0] <= 2:
        raise ValueError(f"Unsupported {property}")
    return parts[0]


def index_nodes(root: Node) -> tuple[dict[str, Node], dict[int, tuple[str, Node]]]:
    nodes = {}
    handles = {}

    def walk(n: Node, path: str):
        if len(nodes) >= 30000:
            raise ValueError("Device tree node cap exceeded")
        nodes[path] = n
        for prop in ("phandle", "linux,phandle"):
            value = n.props.get(prop)
            if value is not None:
                ids = cells(value)
                if len(ids) != 1 or not ids[0]:
                    raise ValueError("Malformed phandle")
                if ids[0] in handles and handles[ids[0]][0] != path:
                    raise ValueError("Duplicate phandle")
                handles[ids[0]] = (path, n)
        for child in n.children:
            walk(child, path.rstrip("/") + "/" + child.name)
    walk(root, "/")
    return nodes, handles


def reg_ranges(n: Node, parent: Node) -> list[dict]:
    a = cell_count(parent, "#address-cells", 2)
    s = cell_count(parent, "#size-cells", 2)
    if a not in (1, 2) or s not in (1, 2):
        raise ValueError("Unsupported UART reg cell width")
    raw = n.props.get("reg")
    if raw is None:
        return []
    words = cells(raw)
    stride = a + s
    if len(words) % stride:
        raise ValueError("Malformed UART reg")
    result = []
    for at in range(0, len(words), stride):
        address = 0
        size = 0
        for part in words[at:at+a]:
            address = (address << 32) | part
        for part in words[at+a:at+stride]:
            size = (size << 32) | part
        if address + size > (1 << 64) or not size:
            raise ValueError("Invalid UART register interval")
        result.append({"base": hex(address), "size": hex(size)})
    return result


def mux_description(state: Node) -> dict:
    pins = set()
    functions = set()

    def visit(n: Node, depth: int):
        if depth > 3:
            return
        for pin in strings(n.props.get("pins")):
            # Only report GPIO/pad names; no arbitrary vendor string values.
            if pin.startswith("gpio") and pin[4:].isdigit() and len(pin) <= 10:
                pins.add(pin)
        for function in strings(n.props.get("function")):
            if function.startswith(("qup", "gpio")) and len(function) <= 24:
                functions.add(function)
        for child in n.children:
            visit(child, depth + 1)
    visit(state, 0)
    return {"pins": sorted(pins), "functions": sorted(functions)}


def pinctrl(n: Node, handles: dict[int, tuple[str, Node]]) -> list[dict]:
    names = strings(n.props.get("pinctrl-names"))
    result = []
    for idx, state_name in enumerate(names[:8]):
        phandles = cells(n.props.get(f"pinctrl-{idx}"))
        targets = []
        for handle in phandles:
            entry = handles.get(handle)
            if entry is None:
                raise ValueError(f"Unresolved UART pinctrl phandle {handle}")
            topo = mux_description(entry[1])
            targets.append({"node": entry[0], **topo})
        result.append({"state": state_name, "targets": targets})
    return result


def clock_dependencies(n: Node, handles: dict[int, tuple[str, Node]]) -> list[dict]:
    names = strings(n.props.get("clock-names"))
    raw = cells(n.props.get("clocks"))
    if not raw:
        return [{"name": name, "available_in_dtb": False} for name in names]
    cursor = 0
    decoded = []
    while cursor < len(raw):
        handle = raw[cursor]
        cursor += 1
        entry = handles.get(handle)
        if entry is None:
            raise ValueError("Unresolved UART clock provider")
        count = cell_count(entry[1], "#clock-cells", -1)
        if count not in (0, 1, 2) or cursor + count > len(raw):
            raise ValueError("Unsupported/truncated clock specifier")
        args = raw[cursor:cursor+count]
        cursor += count
        decoded.append({
            "provider": entry[0],
            "specifier": [hex(x) for x in args],
        })
        if len(decoded) > 32:
            raise ValueError("Excessive UART clocks")
    if names and len(names) != len(decoded):
        raise ValueError("UART clock-name count mismatch")
    for i, item in enumerate(decoded):
        item["name"] = names[i] if i < len(names) else f"unnamed-{i}"
    return decoded


def inspect(root: Node) -> dict:
    identity = " ".join(strings(root.props.get("model")) +
                        strings(root.props.get("compatible"))).lower()
    if "nabu" not in identity or "qcom,sm8150" not in strings(root.props.get("compatible")):
        raise ValueError("Input must identify Xiaomi Pad 5 / nabu / SM8150")
    nodes, handles = index_nodes(root)
    records = []
    for path, node in nodes.items():
        compatibles = strings(node.props.get("compatible"))
        if not any(x in UART_COMPAT for x in compatibles):
            continue
        if len(records) >= MAX_CONTROLLERS:
            raise ValueError("Unexpected UART node count")
        parent_path = path.rsplit("/", 1)[0] or "/"
        parent = nodes.get(parent_path)
        if not parent:
            raise ValueError("UART parent missing")
        regs = reg_ranges(node, parent)
        irq_cells = cells(node.props.get("interrupts"))
        irq = None
        if len(irq_cells) == 3 and irq_cells[0] in (0, 1):
            irq = {"type": "SPI" if irq_cells[0] == 0 else "PPI",
                   "index": irq_cells[1],
                   "gic_intid": irq_cells[1] + (32 if irq_cells[0] == 0 else 16)}
        status = strings(node.props.get("status"))
        name = " ".join(compatibles)
        records.append({
            "path": path,
            "status_in_android_fdt": status[0] if status else "unspecified",
            "compatible": [x for x in compatibles if x in UART_COMPAT],
            "reg": regs,
            "interrupt": irq,
            "pinctrl": pinctrl(node, handles),
            "clocks": clock_dependencies(node, handles),
            "is_candidate_early_console": any(int(r["base"], 16) == TARGET_BASE for r in regs),
            "driver_equivalence_proven": False,
            "pins_physically_accessible": None,
            "clock_enabled_at_abl_entry": None,
        })
    records.sort(key=lambda x: x["path"])
    chosen = nodes.get("/chosen")
    uart_console = next((record for record in records
                         if record["is_candidate_early_console"]), None)
    return {
        "schema": "ios-nabu-stage7-uart-inventory-v1",
        "device": "nabu",
        "soc": "qcom,sm8150",
        "source": "running-Android FDT; not an ABL-time measurement",
        "stdout_path_declared": bool(chosen and chosen.props.get("stdout-path")),
        "candidate_console_found": uart_console is not None,
        "controllers": records,
        "warnings": [
            "FDT pinctrl only identifies SoC functions, not exposed test points, voltage or TX/RX order.",
            "Android device driver state does not establish ABL-time UART configuration.",
            "Vendor qcom,msm-geni-console is not the same binding as mainline qcom,geni-debug-uart.",
            "No physical UART probing, pin writes, UART initialization or kernel boot performed.",
            "No raw DTB, bootargs, serial, MAC, keys or kernel dumps are included.",
        ],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dtb", required=True, type=Path, help="Private local nabu.dtb")
    ap.add_argument("--out", type=Path, required=True, help="Sanitized JSON report")
    args = ap.parse_args(argv)
    try:
        report = inspect(parse_dtb(args.dtb.read_bytes()))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    except (OSError, ValueError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1
    print("Candidate console present:", report["candidate_console_found"])
    print("UART controllers:", len(report["controllers"]))
    print("Saved sanitized report to:", args.out)
    print("NOT proof of physical UART access or ABL-time status")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
