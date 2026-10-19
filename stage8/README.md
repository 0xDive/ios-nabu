# Stage 8 — evaluate USB bootloader logging without physical UART

**Host-only feasibility work. No bootable Xiaomi Pad 5 image. Do not flash or `fastboot boot` the compiled reference binary.**

## Why this is useful

Our Stage 6/6.1 test images automatically rebooted after roughly eight seconds, but remained black throughout. Later Android sysfs inspection showed the vendor GENI console at `0x00A90000` has no bound Linux driver; the working `ttyHS0` is a *different* serial engine (`0x00C8C000`). No physically accessible console TX, serial voltage, or ABL-time UART clock/pin state has been demonstrated.

**U-Boot has an independent USB-based diagnostic path.** In upstream Qualcomm `qcom-phone.config`, `CONFIG_USB_FUNCTION_ACM=y` can provide a serial console gadget, while `CONFIG_CONSOLE_RECORD=y` and `CONFIG_FASTBOOT_CMD_OEM_CONSOLE=y` allow an initialized U-Boot Fastboot gadget to return its recorded console output to a host. The latter uses `fastboot oem console` when supported by that U-Boot build; it is **not a command for Xiaomi's stock ABL Fastboot**.

This can help verify early **U-Boot** startup, DTB parsing and potential loader-stage errors on USB. It does **not** automatically keep collecting messages after control has been passed to XNU. Reliable **XNU** logging will still need a separately implemented USB gadget/logger, independently verified UART output, or another robust channel.

## Pinned reference and hardware limitations

- Upstream: [U-Boot](https://github.com/u-boot/u-boot) tagged `v2026.07`, commit `ece349ade2973e220f524ce59e59711cc919263f`.
- Cross-compile target: Qualcomm **SM8150 MTP reference** `qcom/sm8150-mtp`; **not** a Xiaomi Pad 5 device tree.
- Stock U-Boot v2026.07 includes SM8150 clocks and generic Qualcomm USB gadget drivers, but its bundled upstream DT files have no `sm8150-xiaomi-nabu.dts`. Whether USB enumerates on our tablet is **untested**.
- A public [nabu mainline Linux DTS](https://github.com/SeimoDev/linux-xiaomi-nabu/blob/nabu/6.14.11/arch/arm64/boot/dts/qcom/sm8150-xiaomi-nabu.dts) exists outside upstream U-Boot. It is not automatically compatible with U-Boot or its pre-relocation pin/clock/PHY and reserved-RAM handling. None of the owner's original proprietary device DTBs are committed.

## Host-only build and safety conditions

[The experimental workflow](../.github/workflows/uboot-usb-console.yml) pins source commits, configures the Qualcomm phone reference, **disables** risky fastboot flashing and arbitrary-command functions (`CONFIG_FASTBOOT_FLASH` and `CONFIG_FASTBOOT_OEM_RUN`), disables EFI capsule updates and USB mass storage / DFU commands, then runs the [fail-closed configuration audit](tools/audit_uboot_config.py).

The audit requires console recording, USB ACM, USB Fastboot and the SM8150 clock driver to be present. It refuses to proceed if prohibited commands are still enabled, even if the compiler would succeed.

CI compiles a **reference ELF** but publishes **only** the config audit, compiler log tail, optional kernel ELF checksum (hash only) and a `DO_NOT_BOOT_OR_FLASH` warning. Neither a `boot.img` nor U-Boot executable gets distributed.

For the small unit-test suite (does not need a compiler):

```bash
python3 -m unittest discover -s stage8/tests -v
```

## Important distinction: old ABL vs U-Boot Fastboot

Do not run `fastboot oem run`, `fastboot flash`, `fastboot erase`, `fastboot oem console` or `fastboot oem log` against the Xiaomi stock fastboot based on these notes. The console commands documented here concern a **future, independently validated U-Boot USB gadget**, not the stock Xiaomi bootloader.

Current Stage 8 output is strictly a **development research result**. Before any temporary on-device experiment we need:

1. A reviewed nabu-specific DTB compatible with U-Boot (not the SM8150 MTP stand-in).
2. A verified ABL-to-U-Boot temporary Android boot v3 packaging/handoff and live RAM/USB PHY/clock safety review.
3. Confirmation that the nabu USB DWC3/PHY can be initialized from this context without disrupting boot recovery.
4. Explicit informed device-testing decision with recovery and zero partition writes.
5. A separate plan for reading loader traces after transferring to XNU. U-Boot's recorded-console buffer cannot simply continue running alongside XNU.

Other relevant upstream documentation: [Qualcomm phones](https://docs.u-boot.org/en/v2026.04/board/qualcomm/phones.html), [Qualcomm debugging](https://docs.u-boot.org/en/stable/board/qualcomm/debugging.html), [Fastboot and OEM console](https://docs.u-boot.org/en/latest/android/fastboot.html).
