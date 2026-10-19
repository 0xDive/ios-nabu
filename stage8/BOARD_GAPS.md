# Why a working SM8150 U-Boot build is NOT a nabu boot image

Hardware-specific analysis of the **published sources** below. It is not a measurement of the user's ABL handoff, and none of these sources authorizes a register or RAM write on the tablet.

## Source pinning

- U-Boot `v2026.07`, commit `ece349ade2973e220f524ce59e59711cc919263f`: [`sm8150-mtp.dts`](https://github.com/u-boot/u-boot/blob/v2026.07/dts/upstream/src/arm64/qcom/sm8150-mtp.dts).
- Public nabu Linux board DTS: [`sm8150-xiaomi-nabu.dts`](https://github.com/SeimoDev/linux-xiaomi-nabu/blob/4e6d08bb1b467c721e19cd693e4ec7388d982d73/arch/arm64/boot/dts/qcom/sm8150-xiaomi-nabu.dts), commit `4e6d08bb1b467c721e19cd693e4ec7388d982d73` (2026-08-25). This public board source uses SPDX BSD-3-Clause; its included platform DTS files retain their own licenses.
- Separate device-derived **vendor** DTB was analyzed privately and is not redistributed. Its older downstream USB nodes/bootloader state may differ from the mainline nabu DTS.

## Side-by-side boot-critical differences

| Aspect | Stock U-Boot reference: SM8150 MTP | Public nabu Linux board DTS | Porting implication |
| --- | --- | --- | --- |
| Root compatible | `qcom,sm8150-mtp`, `qcom,sm8150` | `xiaomi,nabu`, `qcom,sm8150` | MTP is **not** a nabu device identity |
| `serial0` | `&uart2` | `&uart2` | Shared alias does not prove clocks, pinmux or accessible pins |
| `/chosen/stdout-path` | `serial0:115200n8` | No equivalent node in the inspected public nabu board DTS | Do not assume UART logs will appear |
| USB1 controller | `&usb_1` enabled | `&usb_1` enabled, with `qcom,select-utmi-as-pipe-clk` | Both mention USB, **different PHY/clock assumptions** |
| USB1 DWC3 mode | `dr_mode = "peripheral"` | `dr_mode = "otg"`, `maximum-speed = "high-speed"`, `usb-role-switch` | Role selection/Type-C path needs nabu-specific validation |
| USB PHY | HS PHY plus `&usb_1_qmpphy` for SuperSpeed | USB 2.0-only, `phys = <&usb_1_hsphy>`, `phy-names = "usb2-phy"`, regulator supplies vary | Blindly using the MTP SuperSpeed configuration risks nonworking USB |
| USB2 controller | Not described by this board DTS as a second port | `&usb_2` enabled, `&usb_2_dwc3` host mode | Can't treat USB2 host controller as USB device console |
| Reserved firmware RAM | Not a nabu-specific memory inventory | Board-specific TrustZone/DSP/modem carveouts, including fixed reserved-memory spans | Review actual ABL FDT and live allocations; never use MTP's memory assumptions |
| Boot image handoff | Generic U-Boot documentation shows Android boot examples for some boards | nabu ABL uses Android boot header v3 and `vendor_boot`, already observed via Stage 3 | A generic U-Boot ELF does not form a nabu `fastboot boot` image |

Both SM8150 platform configuration and nabu public mainline DTS are useful **references**. Neither guarantees that the Qualcomm XBL/ABL USB controllers, SMMU, regulator rails, memory map or cache/MMU state meet U-Boot's expectations.

## Verified host-side build milestone

[PR #21](https://github.com/0xDive/ios-nabu/pull/21) now embeds a
**publicly sourced nabu DTB** into a host-built AArch64 U-Boot ELF. The
[successful CI run](https://github.com/0xDive/ios-nabu/actions/runs/39322222486)
verifies `xiaomi,nabu qcom,sm8150` with `fdtget` and computes the ELF
SHA-256; U-Boot's generic Qualcomm phone gadget configuration has a
separate passing audit with flashing/OEM arbitrary commands disabled.

This is stronger than compiling only the SM8150 MTP reference or running
`dtc` alone, but still does **not** provide a tested tablet boot chain. The
device-specific USB PHY and Type-C policy, boot-time clock and power
dependencies, memory relocation and handoff to XNU are all unverified. The
full U-Boot source builds via an ephemeral one-board DTS workaround in the
CI runner; no claim of mainline U-Boot nabu support or suitable firmware
image is made.

## Gate before considering USB-based on-device debug

1. **Partially completed:** compile public `qcom/sm8150-xiaomi-nabu` DTS and embed it in a host-built U-Boot ELF; **still required:** review U-Boot-specific DT properties and bootloader-time clock/PHY/pinctrl/regulator/Type-C driver operation without reusing MTP board hardware assumptions.
2. Establish a trustworthy RAM and DTB relocation plan at the exact ABL entry point. Stage 6.1's approximately eight-second reset does not prove writable free RAM.
3. Establish that `usb_1` can act as a device while preserving reset/recovery and that Type-C role switching does not disrupt power.
4. With suitable hardware precautions, only then test a **temporary** `fastboot boot` image. Absolutely no partition flashing or bootloader replacement.
5. A running U-Boot gadget could provide **its own** boot log. Getting **XNU** messages after handoff still requires a distinct diagnostic transport.

The current Stage 8 CI only tests a compiler and the configuration for an **MTP reference**, without supplying any executable output or board-specific image for the tablet.
