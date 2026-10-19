#!/usr/bin/env python3
"""Build or inspect a host-side XNU ARM64 boot_args v2 data structure.

No executable image is produced. The output is NOT approved for booting.
Layout follows pexpert/pexpert/arm64/boot.h (Revision 2, Version 2)
as used by the ios-sweet research shim.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

BASE_OFFSET = 8
VIDEO_OFFSET = 40
MACHINE_TYPE_OFFSET = 88
ADT_PTR_OFFSET = 96
ADT_SIZE_OFFSET = 104
CMDLINE_OFFSET = 108
CMDLINE_LENGTH = 608
FLAGS_OFFSET = 720
MEMORY_ACTUAL_OFFSET = 728
STRUCT_SIZE = 736
PAGE = 0x4000
MAX_ADT = 8 * 1024 * 1024
U64_MAX = (1 << 64) - 1


def bounded(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= U64_MAX:
        raise ValueError(f"{name}: invalid unsigned 64-bit integer")
    return value


def from_hex(value, name):
    try:
        number = int(value, 0) if isinstance(value, str) else int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name}: invalid address") from exc
    return bounded(number, name)


def make(layout, adt_bytes, ram_size, cmdline="cpus=1 -v"):
    if not isinstance(layout, dict):
        raise ValueError("Layout report must be an object")
    # A static-only report is mandatory: this tool never authorizes execution.
    if layout.get("status") != "STATIC_ONLY" or layout.get("safe_to_boot") is not False:
        raise ValueError("Use only the offline STATIC_ONLY layout report")
    if layout.get("runtime_free_verified") is not False:
        raise ValueError("Runtime memory claims cannot be inferred by this script")
    if not isinstance(adt_bytes, bytes) or not 0 < len(adt_bytes) <= MAX_ADT:
        raise ValueError("Invalid ADT length")
    phys = from_hex(layout.get("physical_base"), "physical_base")
    virt = from_hex(layout.get("virtual_base"), "virtual_base")
    adt_pa = from_hex(layout.get("adt_physical"), "adt_physical")
    args_pa = from_hex(layout.get("boot_args_physical"), "boot_args_physical")
    top = from_hex(layout.get("allocation_end_exclusive"), "allocation_end_exclusive")
    ram_size = bounded(ram_size, "ram_size")
    if not ram_size or phys % PAGE or adt_pa % PAGE or args_pa % PAGE or top % PAGE:
        raise ValueError("Physical addresses must be 16KiB aligned")
    if not phys <= adt_pa < args_pa < top <= phys + ram_size or top > U64_MAX:
        raise ValueError("Inconsistent address order or outside RAM")
    if adt_pa + len(adt_bytes) > args_pa:
        raise ValueError("ADT overlaps boot_args")
    if args_pa + PAGE > top:
        raise ValueError("No 16KiB boot_args page reserved")
    if virt + (adt_pa - phys) > U64_MAX:
        raise ValueError("ADT VA overflow")
    if not isinstance(cmdline, str) or "\0" in cmdline:
        raise ValueError("Invalid NUL in command line")
    raw_cmdline = cmdline.encode("ascii", "strict")
    if len(raw_cmdline) >= CMDLINE_LENGTH:
        raise ValueError("Command line too long")
    packed = bytearray(STRUCT_SIZE)
    struct.pack_into("<HH", packed, 0, 2, 2)
    struct.pack_into("<QQQQ", packed, BASE_OFFSET, virt, phys, ram_size, top)
    # Video intentionally absent: no known writable framebuffer on nabu.
    struct.pack_into("<6Q", packed, VIDEO_OFFSET, 0, 0, 0, 0, 0, 0)
    struct.pack_into("<I", packed, MACHINE_TYPE_OFFSET, 0)
    device_tree_va = virt + (adt_pa - phys)
    struct.pack_into("<Q", packed, ADT_PTR_OFFSET, device_tree_va)
    struct.pack_into("<I", packed, ADT_SIZE_OFFSET, len(adt_bytes))
    packed[CMDLINE_OFFSET:CMDLINE_OFFSET + len(raw_cmdline)] = raw_cmdline
    struct.pack_into("<Q", packed, FLAGS_OFFSET, 0)
    struct.pack_into("<Q", packed, MEMORY_ACTUAL_OFFSET, ram_size)
    return bytes(packed)


def inspect(data: bytes) -> dict:
    if len(data) != STRUCT_SIZE:
        raise ValueError("Expected 736-byte ARM64 boot_args v2")
    revision, version = struct.unpack_from("<HH", data, 0)
    if (revision, version) != (2, 2):
        raise ValueError("Unsupported boot_args revision/version")
    virt, phys, ram_size, top = struct.unpack_from("<QQQQ", data, BASE_OFFSET)
    video = struct.unpack_from("<6Q", data, VIDEO_OFFSET)
    adt_va, = struct.unpack_from("<Q", data, ADT_PTR_OFFSET)
    adt_size, = struct.unpack_from("<I", data, ADT_SIZE_OFFSET)
    cmd_bytes = data[CMDLINE_OFFSET:CMDLINE_OFFSET + CMDLINE_LENGTH].split(bytes(1), 1)[0]
    try:
        cmd = cmd_bytes.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("Command line not ASCII") from exc
    return {
        "revision": revision,
        "version": version,
        "virt_base": hex(virt),
        "physical_base": hex(phys),
        "mem_size": ram_size,
        "top_of_kernel_data": hex(top),
        "device_tree_va": hex(adt_va),
        "device_tree_length": adt_size,
        "video": list(video),
        "command_line": cmd,
        "status": "OFFLINE_ONLY",
        "safe_to_boot": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--layout", required=True, type=Path)
    p.add_argument("--adt", required=True, type=Path)
    p.add_argument("--ram-size", required=True, type=lambda x: int(x, 0))
    p.add_argument("--cmdline", default="cpus=1 -v")
    p.add_argument("--out", type=Path, default=Path("xnu/out/boot-args-v2.bin"))
    args = p.parse_args()
    try:
        data = make(json.loads(args.layout.read_text()), args.adt.read_bytes(),
                    args.ram_size, args.cmdline)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(data)
        print(json.dumps(inspect(data), indent=2))
        print("Experimental data only. DO NOT FLASH OR BOOT.")
    except (OSError, ValueError, UnicodeError) as exc:
        p.exit(1, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
