# nabu EDK2 diagnostic 06: Disable firmware image-protection policy (temporary only)

**WARNING — Experimental boot-only firmware. Never flash. Never merge this PCD override as a production change.**

## Why

A physical Xiaomi Pad 5 (nabu) running Android has working USB-C OTG. The user's early UEFI diagnostics reached EFI Shell but did not expose a PCI root bridge or USB host-controller protocol. Later `pci-first` and `PCI LOAD ONLY 05` images both crashed **before UEFI Shell** with the same ARM64 synchronous exception (`ELR 0x13FE0C440`, `ESR 0x02000000`).

The fault was offline-symbolized using debug symbols for the pinned EDK2 commit:
- `ArmCpuDxe +0x2440` -> `UpdateRegionMappingRecursive` in `ArmMmuLibCore.c`.
- `DxeCore +0x87AC` -> `SetUefiImageMemoryAttributes`.
- `DxeCore +0x8C18` -> `ProtectUefiImage`.

At baseline, `MdeModulePkg/MdeModulePkg.dec` supplies `PcdImageProtectionPolicy = 0x00000002` (enable protection of firmware-volume PE/COFF images). `PcdDxeNxMemoryProtectionPolicy=0` separately.

## Controlled comparison with crashing 05

This branch is based on the **exact same revision of `NabuUsbDiag.c` as crashing 05** and uses the **original Qualcomm DXE driver order**. Its only firmware behavioral change is to append one fixed-build PCD override to `Platform/Xiaomi/sm8150/nabu.dsc`:

```ini
[PcdsFixedAtBuild.common]
  gEfiMdeModulePkgTokenSpaceGuid.PcdImageProtectionPolicy|0x00000000
```

Other firmware driver binaries, memory map, USB-C/PMIC settings, and DXE order are unchanged. The workflow checks the generated EDK2 auto-header to verify the override took effect.

The build publishes `nabu-edk2-imageprot-off-06` with `boot-nabu.img`, checksums and instructions. **It is not hardware-tested**. It weakens firmware image memory isolation (read-only code and NX data policy), so it is strictly a fault-isolation experiment, not a USB solution.

## Test and interpretation

Use `fastboot boot boot-nabu.img` on an already unlocked bootloader — **never `fastboot flash`**. The user has verified Android still boots after the prior exception. Keep the known-working USB DIAG 04 image at hand.

- If the same early exception returns: image protection *alone* does not eliminate the observed fault.
- If the Boot Menu / EFI Shell now starts: memory image-protection interactions become a much stronger cause candidate. This does **not** establish that USB keyboard works or that disabling image protection is acceptable as a final fix.
- If Shell appears, the existing `PCI BRIDGE LOAD-ONLY TEST` runs, temporarily allocating an EFI image handle and calling `LoadImage` then `UnloadImage`. It does **not** invoke `StartImage` or initialize the PCI driver.
- If the boot hangs at a different stage, photograph the screen. Do not repeatedly boot the image.

Next work if successful: find the underlying MMU mapping/attributes bug and restore secure image protections instead of leaving them disabled.
