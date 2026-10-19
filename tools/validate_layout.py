#!/usr/bin/env python3
"""Offline ARM64 Mach-O placement check against a *Linux* DTB inventory.

Consumes JSON produced by stage4/tools/inspect_kernel.py and
stage4/tools/dtb_inspect.py. No device access or memory writes.

Static collision checks NEVER prove a physical region is free at ABL entry.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

PAGE = 0x4000
LIMIT = 1 << 64
MAX_VM_SIZE = 256 * 1024 * 1024
# XNU on ARM64 maps the kernel at a 32 MiB-aligned virtual L2 block base.
# This is lower than the Mach-O __TEXT segment VA in the current NABU build.
XNU_L2_BLOCK = 0x2000000


def number(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not an address")
    try:
        n = int(value, 0) if isinstance(value, str) else int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Invalid integer: {value!r}") from exc
    if not 0 <= n < LIMIT:
        raise ValueError("Address or size exceeds unsigned 64-bit limit")
    return n


def add(a, b):
    if a < 0 or b < 0 or a + b > LIMIT:
        raise ValueError("64-bit physical address overflow")
    return a + b


def aligned(value):
    return add(value, (-value) % PAGE)


def intersects(a, b, c, d):
    return a < d and c < b


def ranges(table):
    result = []
    if not isinstance(table, dict):
        raise ValueError("Memory inventory must be an object")
    for name, entries in table.items():
        # dtb_inspect.summarize emits {"ranges":[...],"no_map":true},
        # whereas older synthetic reports contained bare lists.
        if isinstance(entries, dict):
            entries = entries.get("ranges")
        if not isinstance(entries, list):
            raise ValueError(f"{name} has no valid ranges list")
        for i, entry in enumerate(entries):
            start, end = number(entry["address"]), number(entry["end_exclusive"])
            if end <= start:
                raise ValueError(f"Invalid address range {name}[{i}]")
            result.append((f"{name}[{i}]", start, end))
    return result


def assess(macho, device_tree, base, adt_size, initrd=None):
    """Propose an offline layout or fail closed; never authorize execution."""
    base = number(base)
    if base % PAGE:
        raise ValueError("Physical kernel base must be aligned to 16 KiB")
    if not 0 < adt_size <= 8 * 1024 * 1024:
        raise ValueError("Unknown/invalid ADT size")
    if macho.get("entry_in_segment") is not True:
        raise ValueError("Kernel Mach-O entry was not validated")
    segments = macho.get("segments")
    if not isinstance(segments, list) or not 1 <= len(segments) <= 1024:
        raise ValueError("No valid kernel segments")
    mapped = []
    for segment in segments:
        start, size = number(segment["vmaddr"]), number(segment["vmsize"])
        file_size = number(segment["filesize"])
        if not size:
            # The successfully built XNU kernel has a file-only __CTF
            # segment. No RAM mapping is assigned to file-only metadata.
            if file_size and segment["name"] not in ("__CTF", "__DWARF", "__LLVM"):
                raise ValueError("Unknown file-only Mach-O segment")
            continue
        if file_size > size:
            raise ValueError("Segment file bytes exceed mapped memory")
        mapped.append((segment["name"], start, add(start, size)))
    if not mapped:
        raise ValueError("No nonempty Mach-O segments")
    mapped.sort(key=lambda s: s[1])
    for left, right in zip(mapped, mapped[1:]):
        if left[2] > right[1]:
            raise ValueError("Overlapping Mach-O VM segments")
    first_vmaddr = mapped[0][1]
    # Match the 32 MiB block mapping used by the pinned XNU/ios-sweet
    # handoff: virtBase is NOT the first __TEXT vmaddr.
    virt_base = first_vmaddr & ~(XNU_L2_BLOCK - 1)
    prefix_size = first_vmaddr - virt_base
    vm_end = mapped[-1][2]
    if vm_end - virt_base > MAX_VM_SIZE:
        raise ValueError("Kernel exceeds conservative 256 MiB limit")
    entry_va = number(macho["entry_va"])
    if not any(start <= entry_va < end for _, start, end in mapped):
        raise ValueError("Kernel entry VA outside executable layout")
    phys_end = add(base, vm_end - virt_base)
    adt_start = aligned(phys_end)
    args_start = aligned(add(adt_start, adt_size))
    allocation_end = add(args_start, PAGE)
    dram = ranges(device_tree.get("memory_banks", {}))
    if not dram or not any(start <= base and allocation_end <= end
                           for _, start, end in dram):
        raise ValueError("Kernel, ADT and boot_args do not fit in a single RAM bank")
    reserved = device_tree.get("reserved_memory", {})
    if not isinstance(reserved, dict):
        raise ValueError("Reserved-memory inventory must be an object")
    dynamic_unresolved = sorted(name for name, props in reserved.items()
                                if isinstance(props, dict)
                                and props.get("dynamic_size_bytes", 0)
                                and not props.get("ranges"))
    collision = [name for name, start, end in ranges(reserved)
        if intersects(base, allocation_end, start, end)]
    if collision:
        raise ValueError(f"Reserved-memory collision: {', '.join(collision)}")
    if initrd is not None:
        start, end = map(number, initrd)
        if end <= start:
            raise ValueError("Invalid initrd reservation")
        if intersects(base, allocation_end, start, end):
            raise ValueError("Bootloader initrd collision")
    return {
        "status": "STATIC_ONLY",
        "static_no_known_collision": True,
        "runtime_free_verified": False,
        "safe_to_boot": False,
        "virtual_base": hex(virt_base),
        "virtual_mapping_block_bytes": XNU_L2_BLOCK,
        "first_segment_va": hex(first_vmaddr),
        "first_segment_physical": hex(add(base, prefix_size)),
        "mapping_prefix_bytes": prefix_size,
        "dynamic_reservations_unresolved": dynamic_unresolved,
        "physical_base": hex(base),
        "entry_physical": hex(add(base, entry_va - virt_base)),
        "kernel_end_exclusive": hex(phys_end),
        "adt_physical": hex(adt_start),
        "boot_args_physical": hex(args_start),
        "allocation_end_exclusive": hex(allocation_end),
        "mapped_segments": [
            {"name": name, "start": hex(add(base, lo - virt_base)),
             "end_exclusive": hex(add(base, hi - virt_base))}
            for name, lo, hi in mapped
        ],
        "limitations": [
            "Linux DTB reservations may differ from those present at ABL handoff.",
            "Dynamic firmware allocations and boot-time FDT placement are unknown.",
            "Locations for dynamic reserved-memory entries cannot be inferred from Android FDT.",
            "No safe memory allocation, Mach-O relocation or XNU execution is proven.",
            "This report MUST NOT be used to boot or flash an experimental kernel."
        ]
    }


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--macho-report", required=True, type=Path)
    cli.add_argument("--memory-report", required=True, type=Path)
    cli.add_argument("--base", required=True, type=lambda v: int(v, 0))
    cli.add_argument("--adt-size", required=True, type=lambda v: int(v, 0))
    cli.add_argument("--initrd-start", type=lambda v: int(v, 0))
    cli.add_argument("--initrd-end", type=lambda v: int(v, 0))
    cli.add_argument("--out", type=Path)
    args = cli.parse_args()
    if (args.initrd_start is None) != (args.initrd_end is None):
        cli.error("Specify both initrd bounds or neither")
    try:
        macho = json.loads(args.macho_report.read_text(encoding="utf-8"))
        device = json.loads(args.memory_report.read_text(encoding="utf-8"))
        bounds = ((args.initrd_start, args.initrd_end)
                  if args.initrd_start is not None else None)
        report = assess(macho, device, args.base, args.adt_size, bounds)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        cli.exit(1, f"ERROR: {exc}\n")
    formatted = json.dumps(report, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(formatted, encoding="utf-8")
        print(f"Static-only report: {args.out} — NOT SAFE TO BOOT")
    else:
        print(formatted)


if __name__ == "__main__":
    main()
