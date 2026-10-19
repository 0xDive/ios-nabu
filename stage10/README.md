# Stage 10 — U-Boot USB gadget driver contract for Xiaomi Pad 5 (nabu)

**Host-only source, final Kconfig and compiled nabu DTB audit. No live PHY test, no boot image and no XNU execution.**

## Why Stage 10 exists

The real `nabu` has now been observed (with rooted Termux on **running Android**) using the exact primary USB Device Controller expected from the public DTB:

| Android USB1 observation (connected to PC) | Value |
| --- | --- |
| UDC | `a600000.dwc3` |
| `state` | `configured` |
| `current_speed` / `maximum_speed` | `high-speed` / `high-speed` |
| `is_otg` | `1` |
| Gadget driver | Assigned (identifier deliberately not exported) |
| `/sys/class/power_supply/usb/online` | `0` (charger/power supply status, not a USB enumeration verdict) |

These values prove **Android's** DWC3 USB gadget was successfully configured by the PC. They say nothing about a future U-Boot build running at ABL entry, the availability of PM8150B Type-C/USB PHY clocks at that moment, or continued XNU output after a U-Boot handoff.

## Pinned U-Boot driver findings

The [U-Boot v2026.07](https://github.com/u-boot/u-boot/tree/ece349ade2973e220f524ce59e59711cc919263f) source contains relevant support, but it is conditional and uses hardware writes:

| Source | Host-side result | Remaining caveat |
| --- | --- | --- |
| [`drivers/usb/dwc3/dwc3-generic.c`](https://github.com/u-boot/u-boot/blob/ece349ade2973e220f524ce59e59711cc919263f/drivers/usb/dwc3/dwc3-generic.c) | The Qualcomm wrapper's fallback `qcom,dwc3` compatible selects `qcom_ops`. `dr_mode=otg` binds the generic **peripheral** driver when `DM_USB_GADGET=y` | Clock/reset driver dependencies and actual probe outcome on nabu untested |
| Same DWC3 generic driver | Understands `qcom,select-utmi-as-pipe-clk` (needed by nabu's USB2-only configuration), toggles QSCRATCH UTMI and VBUS override registers | **Writes MMIO**; cannot be called on the tablet without reviewing ABL-time clock/PHY and recovery |
| [`drivers/phy/qcom/phy-qcom-snps-femto-v2.c`](https://github.com/u-boot/u-boot/blob/ece349ade2973e220f524ce59e59711cc919263f/drivers/phy/qcom/phy-qcom-snps-femto-v2.c) | The `qcom,sm8150-usb-hs-phy` compatible is explicitly listed | PHY init asserts resets and writes MMIO; vendor firmware clock/power state is not verified |
| [`configs/qcom_defconfig`](https://github.com/u-boot/u-boot/blob/ece349ade2973e220f524ce59e59711cc919263f/configs/qcom_defconfig) + `qcom-phone.config` | Generic DWC3/gadget and USB ACM/console logging options are available | `DM_USB_GADGET` must be enabled and verified in the **final generated** `.config` |

**Critical distinction:** a Linux DTB with `usb-role-switch` does *not* automatically imply that this U-Boot driver handles PM8150B Type-C/CC/PD negotiations. The generic DWC3 glue may bind its peripheral mode for OTG, but that says nothing about real cable role/power readiness.

## New validation

The [read-only audit](tools/uboot_usb_driver_gate.py):

1. Reuses Stage 9's checks against **compiled** public `sm8150-xiaomi-nabu.dtb`: correct USB1 wrapper/DWC3, enabled HS PHY `0x088E2000` with the right phandle, correct USB1 OTG and USB2 host-only, disabled SuperSpeed PHY.
2. Checks the original Qualcomm `qcom,dwc3` compatible fallback and `qcom,select-utmi-as-pipe-clk` are present in the compiled DTB, not only DTS text.
3. Checks exact source code patterns for fallback wrapper, OTG-to-peripheral mode binding, the SNPS HS PHY driver and known reset/MMIO-writing behavior.
4. Requires the **final resolved U-Boot Kconfig** to have `USB_DWC3`, `USB_DWC3_GENERIC`, `USB_DWC3_GADGET`, `DM_USB_GADGET`, `PHY_QCOM_USB_SNPS_FEMTO_V2`, `USB_FUNCTION_ACM`, `CONSOLE_RECORD`, `FASTBOOT_CMD_OEM_CONSOLE`, and necessary clocks.
5. Fails if firmware update, Fastboot partition flashing or arbitrary OEM commands are enabled.
6. Emits only narrow JSON conclusions and sets `safe_to_boot=false` regardless of success.

The [Stage 8.1 U-Boot workflow](../.github/workflows/uboot-nabu-dtb.yml) explicitly requests `DM_USB_GADGET` and `USB_DWC3_GADGET` in its host-only build. CI rejects disabled flags after `olddefconfig` (even if requesting the flag succeeded syntactically). No U-Boot executable, `boot.img`, private raw DTB or firmware image is uploaded.

Synthetic tests:

```bash
python3 -m unittest discover -s stage10/tests -v
```

## Remaining conditions before *any* live test

- Audit PM8150B Type-C/CC/role, VBUS, HS PHY regulators, power and reset dependencies **at early boot**. Android USB success cannot establish these at ABL entry.
- Validate boot-time memory ownership, U-Boot stack/relocations, MMU/cache, secure reservations, and the physical recovery path. Stage 6.1's approximately eight-second reset remains indirect only.
- Review all DWC3/PHY/QSCRATCH **register writes** before a device test. Compiling these drivers does not prove that executing their init routines is safe.
- Design a persistence/transport for XNU logs that outlives the U-Boot firmware handoff. `fastboot oem console` is a U-Boot command, **not** an instruction to send to the Xiaomi stock ABL bootloader.
- Never flash Android/ABL/UFS partitions. Do not pass these host-compiled U-Boot and XNU artifacts to `fastboot boot`.

Hardware task: [issue #22](https://github.com/0xDive/ios-nabu/issues/22).
