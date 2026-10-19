#!/usr/bin/env python3
"""Prepare an experimental NABU XNU *compile* from pinned ios-sweet patches.

This is a mechanical identifier-only rename for an initial build experiment.
It deliberately does NOT adapt any hardware driver or prove a safe boot path.
Upstream patches remain in their own repository and are not committed here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

# Pin git repository to an exact immutable commit in the calling workflow.
SOURCE_REPO = "https://github.com/dipa-studio/ios-sweet"
SOURCE_COMMIT = "fdad0de8dc0e75c5ea84762adc03f7232dc91f19"
EXTENSIONS = {".patch", ".sh"}
REQUIRED_PATCHES = {
    "0004-sweet-machine-config.patch",
    "0016-sweet-device-tree-platform-expert.patch",
    "0017-sweet-device-tree-virtual-timer-irq.patch",
    "0018-sweet-boot-cpu-driver.patch",
}

# Identifiers only. Do NOT mechanically replace physical addresses,
# device IDs, driver protocols, memory reservations or boot ABI.
REPLACEMENTS = (
    ("SWEET", "NABU"),
    ("Sweet", "Nabu"),
    ("sweet", "nabu"),
)


def convert_text(source: str) -> str:
    out = source
    for before, after in REPLACEMENTS:
        out = out.replace(before, after)
    return out


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stage(source: Path, destination: Path, manifest: Path) -> dict:
    source = source.resolve()
    destination = destination.resolve()
    manifest = manifest.resolve()
    if not source.is_dir():
        raise ValueError(f"No upstream patch directory: {source}")
    if source == destination or source in destination.parents:
        raise ValueError("Destination must not be nested inside upstream source")
    paths = sorted(
        (p for p in source.iterdir() if p.is_file() and p.suffix in EXTENSIONS),
        key=lambda p: p.name,
    )
    names = {p.name for p in paths}
    missing = REQUIRED_PATCHES - names
    if missing:
        raise ValueError(f"Source lacks required baseline patches: {sorted(missing)}")
    if len(paths) < 40:
        raise ValueError(f"Unexpectedly small upstream patch set: {len(paths)} files")

    # Fail closed on odd names; each generated patch is unique. No .git or
    # shell expansion, and no dependency on a user's private device files.
    result = []
    used = set()
    for entry in paths:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", entry.name):
            raise ValueError(f"Unexpected filename: {entry.name}")
        if entry.stat().st_size > 4 * 1024 * 1024:
            raise ValueError(f"Unexpectedly large patch: {entry.name}")
        original = entry.read_bytes()
        try:
            decoded = original.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Non-UTF-8 upstream file: {entry.name}") from exc
        output_name = convert_text(entry.name)
        if output_name in used or (destination / output_name).is_file():
            raise ValueError(f"Generated patch collides with existing file: {output_name}")
        used.add(output_name)
        transformed = convert_text(decoded).encode("utf-8")
        result.append((entry, output_name, original, transformed))

    destination.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "ios-nabu-xnu-experimental-patch-staging-v1",
        "reference_repo": SOURCE_REPO,
        "reference_commit": SOURCE_COMMIT,
        "target_machine_config": "NABU",
        "stage": "compile-only",
        "warning": (
            "Mechanical SWEET-to-NABU identifier conversion; hardware accesses, "
            "driver implementations and memory layout are NOT validated for SM8150. "
            "NEVER BOOT the resulting kernel."
        ),
        "files": [],
    }
    for entry, output_name, original, transformed in result:
        target = destination / output_name
        target.write_bytes(transformed)
        if target.suffix == ".sh":
            target.chmod(0o755)
        report["files"].append({
            "upstream_filename": entry.name,
            "generated_filename": output_name,
            "upstream_sha256": digest(original),
            "generated_sha256": digest(transformed),
        })
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--source", type=Path, required=True, help="Pinned ios-sweet/xnu/patches")
    cli.add_argument("--dest", type=Path, required=True, help="dxb/patches")
    cli.add_argument(
        "--manifest", type=Path, default=Path("xnu/out/staged-patches.json")
    )
    args = cli.parse_args(argv)
    try:
        result = stage(args.source, args.dest, args.manifest)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Prepared {len(result['files'])} experimental NABU patch files")
    print("WARNING: compile-only; no nabu-specific drivers were validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
