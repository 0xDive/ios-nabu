#!/usr/bin/env python3
"""Reject accidentally tracked personal dumps and firmware artifacts."""
import pathlib
import subprocess
import sys

DISALLOWED = {".dtb", ".dtbo", ".img", ".bin", ".ipsw", ".dmg", ".im4p", ".img4"}
DISALLOWED_NAMES = {"nabu-hardware.json", "nabu-hw-plan.json", "nabu-dtb-summary.json"}

def main():
    root = pathlib.Path(__file__).resolve().parent.parent
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    rejected = [
        name for name in files if name and
        (pathlib.PurePosixPath(name).suffix.lower() in DISALLOWED or
         pathlib.PurePosixPath(name).name.lower() in DISALLOWED_NAMES)
    ]
    if rejected:
        print("Private or binary device artifacts must not be committed:", file=sys.stderr)
        for name in rejected:
            print(" -", name, file=sys.stderr)
        return 1
    print(f"PASS: {len([f for f in files if f])} tracked files; no forbidden device artifacts")
    return 0

if __name__ == "__main__":
    sys.exit(main())
