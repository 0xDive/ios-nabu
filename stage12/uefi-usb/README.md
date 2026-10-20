# Stage 12 — nabu EDK2 UEFI USB diagnostics

**Device status:** Working display, boot menu and EFI Shell on Xiaomi Pad 5 (`nabu`). Hardware USB keyboard **not yet working**. Original `edk2-msm` SM8150 firmware **already contains** XhciDxe, UsbBusDxe, UsbKbDxe, UsbInitDxe and UsbPwrCtrlDxe (APR) so a missing keyboard driver is *not* yet demonstrated.

## Purpose

Build an alternative experimental `boot-nabu.img` in GitHub Actions that runs a read-only screen diagnostic automatically when entering EFI Shell.

The CI job overlays an additional UEFI application (`NabuUsbDiag.efi`) and an FV-embedded `startup.nsh` on pinned upstream `edk2-msm`. The application reports EFI_USB2_HC, EFI_USB_IO, SimpleTextInput, filesystem handle counts; USB host port status; USB VID/PID and interface class where readable. It performs no firmware variable or disk/partition writes. It does query existing USB controller and descriptor APIs.

## Important limitations

- CI can show that this variant compiles and contains the script; **only a physical nabu test proves that startup.nsh actually executes and USB protocols work**.
- Shell `startup.nsh` autostart depends on the firmware volume being exposed as a SimpleFileSystem and Shell finding the script on the default search path.
- No keyboard, touch or Type-C driver is added or fixed by this change.
- Do **not** flash any partitions. Only consider a **temporary** `fastboot boot boot-nabu.img` if the bootloader is unlocked and a working return-to-Android recovery path has already been verified.
- Keep the working base image backed up. Don't mistake a successful GitHub Action for validated hardware functionality.

## Device-side test

1. Download `nabu-edk2-usb-diag` artifact from GitHub Actions.
2. Extract `boot-nabu.img`.
3. Boot temporarily via `fastboot boot boot-nabu.img`; **never use `fastboot flash`**.
4. Select `UEFI Shell` with hardware buttons. Photograph `=== NABU USB DIAG 01 ===` section with the USB-C OTG keyboard connected.
5. If the report does not appear, photograph the Shell prompt, because Shell's startup path did not find the script.

Critical interpretation: `EFI_USB2_HC: 0` suggests host controller not exposed in UEFI; `EFI_USB_IO: 0` with host controller available suggests enumeration, Type-C role/VBUS/power or other transport issue. A nonzero input count can reflect volume keys, not necessarily a USB keyboard.
