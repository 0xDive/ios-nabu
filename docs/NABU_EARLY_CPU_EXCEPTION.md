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
