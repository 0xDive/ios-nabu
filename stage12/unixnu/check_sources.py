#!/usr/bin/env python3
"""Offline UniXNU + DarwinBoot compatibility preflight for nabu.

No payload, boot.img, IPSW, UFS dump or partition write is produced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import tomllib

REQUIRED_UNIXNU = (
    "feeds.toml",
    "package/UniXNUPkg/UniXNUPkg.dec",
    "package/UniXNUPkg/Application/UniXNU/UniXNU.inf",
    "package/UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf",
    "patches/xnu/native-4k-bootstrap-capacity.patch",
    "patches/xnu/native-4k-user-abi.patch",
    "patches/xnu/native-4k-signature-hash-cache.patch",
    "patches/xnu/zzx-pmap-sync-64bit-pa.patch",
)
REQUIRED_DARWIN = (
    "DarwinBootPkg/Driver/DarwinBoot.inf",
    "DarwinBootPkg/Driver/DarwinBoot.c",
    "DarwinBootPkg/Driver/BootArgs.h",
)
EXPECTED_XNU = "d8b80295118ef25ac3a784134bcf95cd8e88109f"


def validate_plan(data: dict) -> None:
    if data["target"]["codename"] != "nabu" or data["target"]["soc"] != "SM8150-AC":
        raise ValueError("Manifest must be dedicated to Snapdragon 860 / nabu")
    if data["target"]["safe_to_boot"] is not False:
        raise ValueError("No validated XNU payload exists for nabu")
    if data["target"]["android_partitions_modified"] is not False:
        raise ValueError("The offline test must not change partitions")
    refs = data["references"]
    for field in ("unixnu_commit", "darwinboot_commit", "uefi_commit"):
        if not re.fullmatch(r"[0-9a-f]{40}", refs[field]):
            raise ValueError(f"Must pin immutable {field} SHA-1 commit")
    xnu = data["xnu"]
    if not (xnu["existing_smoke_generation"] == 8796
            and xnu["unixnu_generation"] == 10063
            and xnu["abi_compatible"] is False
            and xnu["native_page_bytes"] == 4096
            and xnu["source_commit"] == EXPECTED_XNU
            and xnu["built_for_nabu_hardware"] is False):
        raise ValueError("Cannot claim old compile and UniXNU XNU 10063 share an ABI")
    if any(data["handoff"].values()):
        raise ValueError("Handoff fields must remain unverified until device evidence")
    if any(data["safety"].values()):
        raise ValueError("Dangerous partition/payload operations must remain forbidden")
    if "userdata" in data or "ipsw" in data:
        raise ValueError("Do not copy sheng's IPSW or userdata layout to nabu")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(plan_file: Path, unixnu: Path, darwinboot: Path) -> dict:
    with plan_file.open("rb") as f:
        plan = tomllib.load(f)
    validate_plan(plan)
    files: dict[str, dict] = {}
    for prefix, root, paths in (
        ("unixnu", unixnu, REQUIRED_UNIXNU),
        ("darwinboot", darwinboot, REQUIRED_DARWIN),
    ):
        for name in paths:
            path = root / name
            if not path.is_file() or not path.stat().st_size:
                raise ValueError(f"Missing upstream source: {prefix}/{name}")
            files[f"{prefix}/{name}"] = {"bytes": path.stat().st_size, "sha256": digest(path)}

    with (unixnu / "feeds.toml").open("rb") as file:
        feeds = tomllib.load(file)
    kernels = [entry for entry in feeds["source"] if entry.get("name") == "xnu"]
    if len(kernels) != 1 or kernels[0]["commit"] != EXPECTED_XNU:
        raise ValueError("UniXNU reference XNU source pin unexpectedly changed")

    driver = (darwinboot / "DarwinBootPkg/Driver/DarwinBoot.inf").read_text()
    if "gUniXNULoaderProtocolGuid" not in driver or "UEFI_DRIVER" not in driver:
        raise ValueError("DarwinBoot firmware loader protocol or module type changed")
    if "UniXNUPkg/UniXNUPkg.dec" not in driver:
        raise ValueError("DarwinBoot still needs the UniXNUPkg package")

    return {
        "schema": "nabu-unixnu-darwinboot-offline-preflight-v1",
        "target": plan["target"],
        "references": plan["references"],
        "source_xnu_commit": EXPECTED_XNU,
        "existing_nabu_xnu_generation": 8796,
        "unixnu_xnu_generation": 10063,
        "native_4k_source_patches_present": True,
        "darwinboot_uefi_loader_protocol_present": True,
        "sources_verified_offline": True,
        "abi_compatible": False,
        "hardware_verified": False,
        "safe_to_boot": False,
        "missing_before_kernel_handoff": [
            "nabu hardware XNU 10063 build and reviewed drivers",
            "firmware-specific protected RAM/MMU entry map",
            "nabu Apple Device Tree and boot_args hardware contract",
            "verified matching DarwinBoot + UniXNUPkg EFI build",
            "trust policy and kernelcache provenance",
        ],
        "inspected_files": files,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--unixnu", required=True, type=Path)
    parser.add_argument("--darwinboot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = inspect(args.manifest, args.unixnu, args.darwinboot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"Preflight passes: {len(result['inspected_files'])} reference files. safe_to_boot=false")


if __name__ == "__main__":
    main()
