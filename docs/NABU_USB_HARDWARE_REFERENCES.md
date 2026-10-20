# Xiaomi Pad 5 (nabu) USB hardware references — UEFI diagnostics

Research note for the experimental EDK2 firmware branch. Source references are **pinned**; do not assume that downstream Android 4.14, the Linux 7.2.2 branch, and EDK2 initialize hardware identically.

## Pinned third-party sources

1. [MCC45TR/nabu-linux-kernel @ 0b3226f](https://github.com/MCC45TR/nabu-linux-kernel/tree/0b3226fc8f3cab5efb8a47bd17f5d7bd3ed609d1): Linux **7.2.2** `arch/arm64/boot/dts/qcom/sm8150-xiaomi-nabu.dts` and `sm8150.dtsi`.
2. [djo-n/android_device_xiaomi_nabu @ c5bbb2a](https://github.com/djo-n/android_device_xiaomi_nabu/tree/c5bbb2a541226967a69c829142f0e6fb53187717): Android device config, not an EDK2 USB implementation.
3. Current reference EDK2: [edk2-porting/edk2-msm @ e195262](https://github.com/edk2-porting/edk2-msm/tree/e1952621f419f8db60ed28271264e1b5184c571d); pinned binary submodule SHA `d097b8a8bf3641e5e0c8b36ef1ac9d7cc1a0bd94`.

## Grounded USB topology from modern Linux DTS

| Node / location | Hardware and configuration |
| --- | --- |
| `&usb_1` / `usb@a6f8800` | Qualcomm SM8150 DWC3 wrapper; USB2 only on this board; `qcom,select-utmi-as-pipe-clk`; `status = "okay"` |
| `&usb_1_dwc3` / `usb@a600000` | DWC3 core, `dr_mode = "otg"`, `maximum-speed = "high-speed"`, `usb-role-switch`, `phys = <&usb_1_hsphy>` |
| `&usb_1_hsphy` / `phy@88e2000` | USB2 high-speed PHY, supplies: `vreg_l5a_0p8` (PLL), `vreg_l12a_1p8`, `vreg_l2a_3p1` |
| `&pm8150b_typec` / `typec@1500` | PM8150B Type-C; dual data/power roles, `try-power-role = "sink"`, connected to `&usb_1_dwc3_hs` through `&pm8150b_role_switch_in` |
| `&pm8150b_vbus` / `usb-vbus-regulator@1100` | PM8150B VBUS source; current constraints 500 mA–3 A in board DTS |
| `&usb_2_dwc3` / `usb@a800000` | Secondary controller declared `dr_mode = "host"`, USB2 only; **not evidence that the external USB-C connector is attached to this controller** |

Relevant source links:
- [Board DTS](https://github.com/MCC45TR/nabu-linux-kernel/blob/0b3226fc8f3cab5efb8a47bd17f5d7bd3ed609d1/arch/arm64/boot/dts/qcom/sm8150-xiaomi-nabu.dts)
- [SM8150 SoC DTSI](https://github.com/MCC45TR/nabu-linux-kernel/blob/0b3226fc8f3cab5efb8a47bd17f5d7bd3ed609d1/arch/arm64/boot/dts/qcom/sm8150.dtsi)
- [PM8150B Type-C Linux driver](https://github.com/MCC45TR/nabu-linux-kernel/blob/0b3226fc8f3cab5efb8a47bd17f5d7bd3ed609d1/drivers/usb/typec/tcpm/qcom/qcom_pmic_typec.c)
- [PM8150B VBUS Linux driver](https://github.com/MCC45TR/nabu-linux-kernel/blob/0b3226fc8f3cab5efb8a47bd17f5d7bd3ed609d1/drivers/regulator/qcom_usb_vbus-regulator.c)

Linux uses a Type-C Port Manager, PMIC SPMI regmap, Type-C/PD PHY and VBUS regulator. **Do not copy raw PMIC register writes from Linux into EDK2 or force a source role without ensuring current limits, safe power path and controller state.**

## Android device-tree confirmations

[BoardConfig.mk](https://github.com/djo-n/android_device_xiaomi_nabu/blob/c5bbb2a541226967a69c829142f0e6fb53187717/BoardConfig.mk) sets `androidboot.usbcontroller=a600000.dwc3` (the same primary DWC3). `device.mk` installs `android.hardware.usb.host.xml` and `android.hardware.usb@1.3-service.dual_role_usb`. `vendor.prop` sets `persist.sys.oem.otg_support=true`. `rootdir/etc/init.target.rc` sets the USB controller to `a600000.dwc3`, while `init.qcom.usb.rc` handles Android USB gadgets.

The Android config supports a host/OTG capability **only in the context of Android firmware/drivers**. Gadget setup does not initialize the UEFI USB host.

## Physical nabu EDK2 diagnostic evidence

User-tested EDK2 DEBUG variant with OTG hub, EFI Shell startup diagnostics:

- `EFI_USB2_HC = 0`; `EFI_USB_HC_LEGACY = 0`; `EFI_USB_IO = 0`
- `PCI_ROOT_BRIDGE_IO = 0`; `PCI_IO = 0`; `USBFN_DEVICE = 0`.
- 23 Driver Binding handles; matching firmware-file images/bindings for `XhciPciEmulation`, `XhciDxe`, `UsbBusDxe`, `UsbKbDxe`; PciHostBridge `- / -`.
- **Caveat:** diagnostic image/binding matching does **not** prove the driver's entry ran, dependencies were satisfied, or the driver's `Start()` succeeded.

EDK2's SM8150 `PciHostBridge.depex` requires Metronome and PCD protocols; `NABU USB DIAG 03` was built to inspect these protocols and existence of the `PciHostBridge` firmware file. Await the physical screenshot before concluding why PCI root bridge is absent.

## Next investigation order

1. Check DIAG 03 Metronome and PCD counts, PCI bridge firmware file and driver image/binding. Avoid forcing `ConnectController` or arbitrary driver invocation until known-safe.
2. Explain why EDK2's binary `PciHostBridgeDxe` + `XhciPciEmulation` do not expose `EFI_PCI_ROOT_BRIDGE_IO` / `EFI_USB2_HC`. Qualcomm DWC3 in Linux is a platform MMIO controller, while this EDK2 port uses proprietary PCI emulation, so applying Linux DTB alone cannot fix the DXE chain.
3. Only after the host-controller chain exists, test OTG role, PM8150B Type-C attach state, HS PHY clocks/supplies and safe VBUS sourcing.
4. Preserve Android partitions and boot with temporary `fastboot boot boot-nabu.img`; no flashing or blind PMIC MMIO/SPMI writes.

**Hardware evidence > a successful GitHub Actions build.** This document does not establish that USB host or keyboard works in UEFI.
