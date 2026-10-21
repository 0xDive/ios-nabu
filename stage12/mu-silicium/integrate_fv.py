#!/usr/bin/env python3
"""Inject upstream UniXNU and DarwinBoot into Mu-Silicium nabuPkg for *offline linking*.

No BootOrder/Boot#### registration is included; the linked application is not
automatically launched. Does not alter vendor drivers, DTB, memory map or FD size.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

UNI_APP = "UniXNUPkg/Application/UniXNU/UniXNU.inf"
DARWIN = "DarwinBootPkg/Driver/DarwinBoot.inf"
REGISTRAR = "UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf"
UNICORE = "UniXNULib|UniXNUPkg/Library/UniXNULib/UniXNULib.inf"
FDTLIB = "FdtLib|MdePkg/Library/BaseFdtLib/BaseFdtLib.inf"


def replace_once(data: str, old: str, new: str) -> str:
    if data.count(old) != 1:
        raise ValueError(f"Expected exactly one source anchor {old!r}, found {data.count(old)}")
    return data.replace(old, new, 1)


def overlay(workspace: Path) -> dict:
    dsc = workspace / "Platforms/Xiaomi/nabuPkg/nabu.dsc"
    fdf = workspace / "Platforms/Xiaomi/nabuPkg/nabu.fdf"
    for path in (
        dsc, fdf, workspace / UNI_APP, workspace / DARWIN,
        workspace / "UniXNUPkg/UniXNUPkg.dec",
    ):
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f"Missing pinned source: {path}")
    original_dsc = dsc.read_text()
    original_fdf = fdf.read_text()
    for label in (UNI_APP, DARWIN, REGISTRAR, UNICORE):
        if label in original_dsc or label in original_fdf:
            raise ValueError(f"Unexpected preexisting UniXNU item {label}")
    if "SOC_TYPE                       = 2" not in original_dsc:
        raise ValueError("This must remain the original Snapdragon 860 nabu DSC")
    if "[FD.SILICIUM_UEFI]" not in original_fdf:
        raise ValueError("Unexpected Mu-Silicium FDF layout")

    patched_dsc = replace_once(
        original_dsc,
        "[Components]\n",
        "  # Upstream UniXNU libraries (used solely by this offline-link variant)\n"
        f"  {UNICORE}\n  {FDTLIB}\n\n[Components]\n"
    )
    patched_dsc += f"\n  # UEFI application and loader; NO UniXNUDxe boot-order registrar.\n  {UNI_APP}\n  {DARWIN}\n"
    patched_fdf = replace_once(
        original_fdf,
        "  !include QcomPkg/Extra.fdf.inc\n",
        "  !include QcomPkg/Extra.fdf.inc\n\n"
        "  # Embed only UniXNU app and DarwinBoot. No Boot####/BootOrder writer.\n"
        f"  INF {UNI_APP}\n  INF {DARWIN}\n"
    )

    if REGISTRAR in patched_dsc or REGISTRAR in patched_fdf:
        raise ValueError("Autostart/BootOrder registrar must not be included")
    if patched_dsc.count(UNI_APP) != 1 or patched_fdf.count(UNI_APP) != 1:
        raise ValueError("UniXNU must appear exactly once per DSC/FDF")
    if patched_dsc.count(DARWIN) != 1 or patched_fdf.count(DARWIN) != 1:
        raise ValueError("DarwinBoot must appear exactly once per DSC/FDF")

    dsc.write_text(patched_dsc)
    fdf.write_text(patched_fdf)
    return {
        "schema": "nabu-unixnu-fv-static-link-v1",
        "device": "nabu",
        "upstream_board_patched_in_ci_only": True,
        "build_produces_bootable_xnu": False,
        "boots_unixnu_automatically": False,
        "writes_uefi_boot_order": False,
        "changes_fd_base_or_size": False,
        "changes_qualcomm_drivers": False,
        "nabu_soc_type": 2,
        "components": [UNI_APP, DARWIN],
        "excluded": [REGISTRAR],
        "safe_to_flash": False,
        "note": "Source-level link integration, not XNU boot and not even app execution on nabu.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = overlay(args.workspace)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("nabu DSC/FDF: UniXNU.efi + DarwinBoot.efi linked, registrar excluded.")


if __name__ == "__main__":
    main()
