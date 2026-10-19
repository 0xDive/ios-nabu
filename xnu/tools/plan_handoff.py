#!/usr/bin/env python3
"""Stage 5 OFFLINE XNU Mach-O -> ADT/boot_args handoff planner.

Inputs: host-side Mach-O report, static-only memory-layout report,
locally generated ADT binary and boot_args v2 bytes. The output is a
validated *list of proposed operations*, NOT a bootable image.

No memory writes, Mach-O copying, Apple image creation or device access.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "stage4" / "tools"))
from adt_format import unpack as unpack_adt
from boot_args import inspect as inspect_boot_args

MAX_U64 = (1 << 64) - 1
MAX_KERNEL = 256 * 1024 * 1024
XNU_L2_BLOCK = 32 * 1024 * 1024
PAGE = 16 * 1024
FILE_ONLY = frozenset(("__CTF", "__DWARF", "__LLVM"))


def integer(value, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name}: boolean is not an address")
    try:
        result = int(value, 0) if isinstance(value, str) else int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name}: invalid integer {value!r}") from exc
    if not 0 <= result <= MAX_U64:
        raise ValueError(f"{name}: not a valid unsigned 64-bit integer")
    return result


def add(a: int, b: int) -> int:
    if a < 0 or b < 0 or a + b > MAX_U64:
        raise ValueError("64-bit address overflow")
    return a + b


def plan(macho: dict, layout: dict, adt_bytes: bytes, boot_args: bytes) -> dict:
    """Verify consistency of proposed physical operations without executing."""
    if macho.get("format") != "Mach-O 64-bit ARM64":
        raise ValueError("Only a raw ARM64 Mach-O is supported")
    if macho.get("filetype") != "0x00000002":
        raise ValueError("Expected a kernel MH_EXECUTE Mach-O")
    if macho.get("entry_in_segment") is not True:
        raise ValueError("Mach-O entry has not been validated")
    if macho.get("chained_fixups") is not None:
        raise ValueError("Chained fixups require a separate, audited rebase pass")
    if (layout.get("status") != "STATIC_ONLY" or
        layout.get("static_no_known_collision") is not True or
        layout.get("safe_to_boot") is not False or
        layout.get("runtime_free_verified") is not False):
        raise ValueError("Require an offline-only static layout with no boot approval")
    file_length = integer(macho.get("file_bytes"), "Mach-O length")
    if not 0 < file_length <= MAX_KERNEL:
        raise ValueError("Mach-O size outside supported bounds")

    virt = integer(layout.get("virtual_base"), "virtBase")
    phys = integer(layout.get("physical_base"), "physBase")
    if virt % XNU_L2_BLOCK or phys % XNU_L2_BLOCK:
        raise ValueError("XNU virtBase/physBase must be aligned to 32 MiB")
    entry_va = integer(macho.get("entry_va"), "entry VA")
    entry_pa = add(phys, entry_va - virt) if entry_va >= virt else None
    if entry_pa is None or entry_pa != integer(layout.get("entry_physical"), "entry PA"):
        raise ValueError("XNU entry physical address mismatch")

    ba = inspect_boot_args(boot_args)
    if ba["safe_to_boot"] is not False or any(ba["video"]):
        raise ValueError("Only an offline boot_args with no framebuffer is supported")
    if ba["virt_base"] != hex(virt) or ba["physical_base"] != hex(phys):
        raise ValueError("boot_args physical/virtual base mismatch")
    if ba["top_of_kernel_data"] != layout.get("allocation_end_exclusive"):
        raise ValueError("boot_args topOfKernelData disagrees with layout")

    if not isinstance(adt_bytes, bytes) or not 0 < len(adt_bytes) <= 8 * 1024 * 1024:
        raise ValueError("Invalid ADT data")
    root = unpack_adt(adt_bytes)
    chosen = root.child("chosen")
    if root.name != "device-tree" or chosen is None:
        raise ValueError("Missing ADT device-tree/chosen")
    compatibles = root.props.get("compatible", b"").split(bytes(1))
    if b"xiaomi,nabu" not in compatibles or b"qcom,sm8150" not in compatibles:
        raise ValueError("ADT does not identify nabu / SM8150")
    dram_base = chosen.props.get("dram-base", b"")
    dram_size = chosen.props.get("dram-size", b"")
    if len(dram_base) != 8 or len(dram_size) != 8:
        raise ValueError("ADT has invalid DRAM bounds")
    if struct.unpack("<Q", dram_base)[0] != phys or struct.unpack("<Q", dram_size)[0] != ba["mem_size"]:
        raise ValueError("ADT and boot_args DRAM bounds disagree")

    adt_pa = integer(layout.get("adt_physical"), "ADT PA")
    args_pa = integer(layout.get("boot_args_physical"), "boot_args PA")
    top = integer(layout.get("allocation_end_exclusive"), "allocation end")
    if any(x % PAGE for x in (adt_pa, args_pa, top)) or not (
        phys < adt_pa < args_pa < top and top <= add(phys, ba["mem_size"])
    ):
        raise ValueError("ADT/boot_args allocation bounds are invalid")
    if len(adt_bytes) > args_pa - adt_pa:
        raise ValueError("ADT overlaps boot_args")
    if args_pa + PAGE > top:
        raise ValueError("boot_args page is not allocated")
    expected_adt_va = add(virt, adt_pa - phys)
    if ba["device_tree_va"] != hex(expected_adt_va) or ba["device_tree_length"] != len(adt_bytes):
        raise ValueError("ADT virtual pointer or byte count does not match")

    segments = macho.get("segments")
    mapped_in_layout = layout.get("mapped_segments")
    if not isinstance(segments, list) or not isinstance(mapped_in_layout, list):
        raise ValueError("Missing Mach-O or mapped segment table")
    if not 1 <= len(segments) <= 1024:
        raise ValueError("Invalid Mach-O segment count")
    mappings = []
    operations = []
    entry_is_executable = False
    for seg in segments:
        name = seg["name"]
        vmaddr = integer(seg["vmaddr"], f"{name}.vmaddr")
        vmsize = integer(seg["vmsize"], f"{name}.vmsize")
        fileoff = integer(seg["fileoff"], f"{name}.fileoff")
        filesize = integer(seg["filesize"], f"{name}.filesize")
        if add(fileoff, filesize) > file_length:
            raise ValueError(f"{name}: file content outside Mach-O")
        if vmsize == 0:
            if filesize and name not in FILE_ONLY:
                raise ValueError(f"{name}: unrecognized file-only segment")
            continue
        if filesize > vmsize or vmaddr < virt:
            raise ValueError(f"{name}: invalid mapped VM/file size")
        dest = add(phys, vmaddr - virt)
        end = add(dest, vmsize)
        if not phys <= dest < end <= adt_pa:
            raise ValueError(f"{name}: overlaps ADT, boot_args or memory bounds")
        mappings.append((name, dest, end))
        if filesize:
            operations.append({
                "operation": "copy_from_macho",
                "segment": name,
                "source_file_offset": fileoff,
                "bytes": filesize,
                "destination_physical": hex(dest)
            })
        if vmsize > filesize:
            operations.append({
                "operation": "zero_bss",
                "segment": name,
                "bytes": vmsize - filesize,
                "destination_physical": hex(add(dest, filesize))
            })
        if name == "__TEXT_EXEC" and vmaddr <= entry_va < add(vmaddr, vmsize):
            entry_is_executable = True

    if not entry_is_executable:
        raise ValueError("Entry is not in __TEXT_EXEC (required for this NABU kernel)")
    mappings.sort(key=lambda x: x[1])
    for left, right in zip(mappings, mappings[1:]):
        if left[2] > right[1]:
            raise ValueError("Mach-O mapped segments physically overlap")

    from_layout = sorted((
        (x["name"], integer(x["start"], "segment start"),
         integer(x["end_exclusive"], "segment end"))
        for x in mapped_in_layout
    ), key=lambda x: x[1])
    if mappings != from_layout:
        raise ValueError("Mach-O segments and static layout mapping disagree")

    return {
        "schema": "ios-nabu-stage5-offline-handoff-v1",
        "status": "OFFLINE_PLAN_ONLY",
        "safe_to_boot": False,
        "runtime_memory_verified": False,
        "kernel_macho_file_size": file_length,
        "virtual_base": hex(virt),
        "physical_base": hex(phys),
        "entry_va": hex(entry_va),
        "entry_physical": hex(entry_pa),
        "mapped_segment_count": len(mappings),
        "operations": operations,
        "adt_physical": hex(adt_pa),
        "boot_args_physical": hex(args_pa),
        "boot_args_cmdline": ba["command_line"],
        "unresolved_dynamic_reservations": layout.get("dynamic_reservations_unresolved", []),
        "limitations": [
            "Operations are a proposed manifest, not executed copies or relocations.",
            "Kernel Mach-O bytes are NOT part of this report.",
            "Linux Device Tree inventory does not prove ABL runtime free memory.",
            "No early logging, cache/MMU transitions, device initialization or XNU entry proven.",
            "DO NOT create a fastboot/flash image from this report."
        ]
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--macho-report", required=True, type=Path)
    parser.add_argument("--layout", required=True, type=Path)
    parser.add_argument("--adt", required=True, type=Path)
    parser.add_argument("--boot-args", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = plan(json.loads(args.macho_report.read_text(encoding="utf-8")),
                      json.loads(args.layout.read_text(encoding="utf-8")),
                      args.adt.read_bytes(), args.boot_args.read_bytes())
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError, KeyError, struct.error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Created offline handoff plan ({result['mapped_segment_count']} mapped segments)")
    print("DO NOT BOOT OR FLASH: this is not an executable image")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
