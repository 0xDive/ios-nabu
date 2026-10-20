# Xiaomi Pad 5 EDK2 early exception — symbolization

## Confirmed physical observations

- **Host hardware:** Android 4.14 OTG and keyboard operate normally. Faults occur only in experimental EDK2 UEFI.
- Original diagnostic **USB DIAG 04** reached EFI Shell with USB/PCI protocol counts 0.
- Experimental `pci-first` DXE ordering: pre-UEFI/Shell ARM64 synchronous exception and hang.
- Experimental `usb-stack-first` ordering: EFI Shell still works but PCI/USB protocol counts remain 0.
- Experimental `PCI LOAD ONLY 05`, based on **original DXE order**: pre-UEFI/Shell synchronous exception and hang.
- The last test's `ReportPciLoadOnly()` is reachable **only** from `NabuUsbDiag.efi` automatically launched by `startup.nsh` when entering EFI Shell. **It never ran** in the failed boot. No `LoadImage` test result exists.

## Exception photographed on two builds

- `Synchronous Exception at 0x000000013FE0C440`
- `ELR = 0x000000013FE0C440`
- `ESR = 0x02000000`, `EC = 0x00`, `IL = 0x1`, `ISS = 0x0`
- `FAR = 0x0000000000000000`
- Top image is `ArmCpuDxe.dll`; stack includes `DxeCore.dll`.
- A preceding log line mentions `ReplaceTableEntry: splitting block entry with MMU disabled`.

**Interpretation:** the fault's module/PC may be a caller or exception handling artifact, not necessarily the first bad hardware access; EC 0x00 is an unknown/uncategorized synchronous exception, not automatically a data abort. The same ELR in two differently modified builds is a strong reason to inspect the precise compiled source locations and memory attributes. It is **not** evidence that the PCI driver failed `LoadImage`; this test did not execute.

## Offline debug plan

1. Build the exact pinned `edk2-msm` commit `e1952621f419f8db60ed28271264e1b5184c571d` with the `PCI LOAD ONLY 05` overlay in GitHub Actions, **without offering a new boot image**.
2. Export `ArmCpuDxe.debug`, `ArmCpuDxe.dll`, `DxeCore.debug`, `DxeCore.dll` and reproducible `nm`, `readelf`, `addr2line`, `objdump` reports.
3. Resolve the photographed offsets (first ArmCpuDxe PC apparent offset `0x2440` or nearby; DxeCore frames `0x87ac`, etc.). Confirm the PE vs ELF address conversion before trusting any source line.
4. Inspect relevant `ArmMmuLib`, `CpuDxe`, and platform memory-map paths. Consider PE/COFF image placement or memory-map stability, **not** a blind driver-reordering change.
5. Do not re-run `pci-first` or `PCI LOAD ONLY 05` on hardware. Keep known working `USB DIAG 04` as the baseline. No partition flashing.

This file records observations; it does not claim a fix or successful USB enumeration.

## Offline symbolization result (GitHub Actions 39472373483)

GitHub Actions completed the exact pinned host build and published artifact `nabu-armcpu-exception-symbols`:
https://github.com/0xDive/ios-nabu/actions/runs/39472373483

The extracted `ArmCpuDxe.debug` and `DxeCore.debug` were independently checked with `aarch64-linux-gnu-nm`, `addr2line`, `readelf` and `objdump`:

| Observed/expected PE image offset | Mapped function in exact ELF build | Evidence |
| --- | --- | --- |
| ArmCpuDxe `+0x2440` | `UpdateRegionMappingRecursive()` | `ArmPkg/Library/ArmMmuLib/AArch64/ArmMmuLibCore.c` around line 230 |
| ArmCpuDxe `+0x2434` | `UpdateRegionMappingRecursive()` | Same function; branch immediately before `+0x2440` |
| DxeCore `+0x87AC` | `SetUefiImageMemoryAttributes()` | `MdeModulePkg/Core/Dxe/Misc/MemoryProtection.c` around line 229 |
| DxeCore `+0x8C18` | `ProtectUefiImage()` | Same source file |

`ArmCpuDxe` ELF `.text` is `0x1000..0x7218`. The instruction at `0x2440` is **valid AArch64** `0x92800008: mov x8,#-1`, so the source machine code is not an inherently undefined opcode. The `ArmReplaceLiveTranslationEntry()` assembly symbol is at ELF `0x4B14` (not `0x2440`); the warning about temporarily disabling MMU may have been printed earlier but is not proof that this helper is the faulting instruction. Confirm actual PE/ELF load-relative offsets on device before drawing a definitive CPU-corruption conclusion.

**Working hypothesis:** when DxeCore loads/protects a PE/COFF image, `ProtectUefiImage -> SetUefiImageMemoryAttributes -> CpuSetMemoryAttributes -> UpdateRegionMappingRecursive` updates AArch64 translation-table mappings; the page table/memory attribute path can become unstable in certain memory or image placement configurations. The observed failure predates execution of the custom Shell application and PCI LoadImage probe, so it should not be attributed to USB, keyboard or the PCI binary alone.

**Next action should be offline analysis of image memory protection PCD policy, memory map and actual runtime images; do not change permissions on the tablet or test a new image without a rationale and rollback.** The host job does not upload a firmware boot image.
