#!/usr/bin/env python3
"""Validate an *unverified* Mu-Silicium nabu Android boot image offline.

Never reads block devices or performs a fastboot/flash operation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inspect(boot: Path, fd: Path, dtb: Path) -> dict:
    data = boot.read_bytes()
    firmware = fd.read_bytes()
    tree = dtb.read_bytes()
    if len(data) < 4096 or data[:8] != b"ANDROID!":
        raise ValueError("Not an Android boot image")
    kernel_size = struct.unpack_from("<I", data, 8)[0]
    page_size = struct.unpack_from("<I", data, 36)[0]
    header_version = struct.unpack_from("<I", data, 40)[0]
    if header_version != 1:
        raise ValueError(f"Mu nabu currently expects boot header v1; found {header_version}")
    if page_size not in (2048, 4096, 8192, 16384):
        raise ValueError(f"Invalid boot page size {page_size}")
    if not kernel_size or page_size + kernel_size > len(data):
        raise ValueError("Boot kernel field invalid/truncated")
    if len(firmware) != 0x300000:
        raise ValueError(f"Firmware size differs from nabu FD_SIZE=3 MiB: {len(firmware)}")
    if len(tree) < 40 or tree[:4] != bytes.fromhex("d00dfeed"):
        raise ValueError("DTB is not an FDT")
    kernel = data[page_size:page_size + kernel_size]
    if not kernel.startswith(bytes.fromhex("1f8b")):
        raise ValueError("Expected compressed BootShim + FD")
    decompressor = zlib.decompressobj(31)
    unpacked = decompressor.decompress(kernel) + decompressor.flush()
    if not decompressor.eof:
        raise ValueError("Incomplete gzip UEFI payload")
    appended_dtb = decompressor.unused_data
    if appended_dtb != tree:
        raise ValueError("Appended DTB differs from pinned nabu.dtb")
    if not unpacked.endswith(firmware):
        raise ValueError("Uncompressed UEFI FD mismatch inside BootShim payload")
    if len(unpacked) == len(firmware):
        raise ValueError("BootShim not found before firmware FD")
    return {
        "schema": "nabu-mu-uefi-boot-container-audit-v1",
        "device": "nabu",
        "hardware_verified": False,
        "safe_to_flash": False,
        "android_boot_header_version": header_version,
        "boot_kernel_bytes": kernel_size,
        "android_page_bytes": page_size,
        "bootshim_bytes": len(unpacked) - len(firmware),
        "firmware_base_expected": "0x9FC00000",
        "firmware_bytes": len(firmware),
        "appended_dtb_bytes": len(tree),
        "sha256": {"boot_image": sha(data), "firmware_fd": sha(firmware), "dtb": sha(tree)},
        "note": "Host-side consistency only; ABL acceptance, MMU, USB and XNU startup are untested.",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--boot", type=Path, required=True)
    p.add_argument("--fd", type=Path, required=True)
    p.add_argument("--dtb", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args()
    report = inspect(args.boot, args.fd, args.dtb)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
