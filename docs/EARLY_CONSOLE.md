# Finding a non-visual early-boot diagnostic channel on Xiaomi Pad 5 (nabu)

## Motivation

Stage 6.1 reportedly triggered an autonomous reset **within roughly eight seconds** after `fastboot boot` of the temporary FDT diagnostic image. The screen remains black because the diagnostic has no framebuffer output. Reset timing is indirect evidence; it cannot distinguish individual FDT properties or prove an address range is writable by XNU.

This research is deliberately **read-only**. The next step is to identify a trustworthy output channel that survives the transition out of Qualcomm ABL and lets us see messages from a tiny shim and later from XNU.

## Serial-console candidates in a locally inspected Android DTB

The user-provided Xiaomi Pad 5 / SM8150 FDT describes these platform nodes (hardware-only facts; the original device DTB stays private):

| Node | Compatible | MMIO range in the Linux FDT | `status` |
| --- | --- | --- | --- |
| `/soc/qcom,qup_uart@0xa90000` | `qcom,msm-geni-console` | `0x00A90000` + `0x4000` | `ok` |
| `/soc/qcom,qup_uart@0xc8c000` | `qcom,msm-geni-serial-hs` | `0x00C8C000` + `0x4000` | `ok` |
| `/soc/qcom,qup_uart@a84000` | `qcom,msm-geni-serial-hs` | `0x00A84000` + `0x4000` | `disabled` |

The candidate `0x00A90000` console has clock names `se-clk`, `m-ahb`, `s-ahb`, and pinctrl states `default` and `sleep`. The working-Android FDT has **no** explicit `/chosen/stdout-path`.

The `pinctrl-0` phandle of this console resolves to `qupv3_se12_2uart_active`, whose mux selects `gpio85` and `gpio86` for `qup12`; its `sleep` state selects ordinary GPIO mode. **These are SoC GPIO names, not identified motherboard pads or a confirmed TX/RX ordering**. Do not attach hardware or toggle the pins from this fact alone.

These facts **do not prove** any UART is already enabled or clocked when ABL enters our bare-metal image; that the pins are available on exposed test points; or that voltage, signal routing, pin mux and clock configuration are correct. The `0x00C8C000` high-speed serial engine may be in use by another peripheral and is not a default debug path.

## Stage 7 reproducible read-only inventory

The [Stage 7 tools](../stage7/README.md) now parse Qualcomm GENI UART
topology from the private device FDT, resolve clock and pinctrl phandles,
and optionally query currently running Android over ADB. The ADB collector
does **not** mount debugfs, read full bootargs/dmesg, toggle GPIOs or access
MMIO. If any kernel debug information is unavailable, it reports an unknown
state rather than trying to enable the interface.

The host-side analyzer has been executed on the original user-provided
`nabu.dtb`. It successfully found three serial nodes: console
`0x00A90000` (`ok`, GPIO85/86), high-speed port `0x00C8C000`
(`ok`) and port `0x00A84000` (`disabled`). For the console, the
FDT's `/soc/qcom,gcc` clock indices are `0x69` (`se-clk`),
`0x7b` (`m-ahb`) and `0x7c` (`s-ahb`). This is decoded FDT
topology, **not clock-on evidence at ABL handoff**.

Mainline Linux SM8150 describes address `0x00A90000` as
`qcom,geni-debug-uart`, with `GCC_QUPV3_WRAP1_S4_CLK` and SPI 357.
The vendor DTB instead describes `qcom,msm-geni-console` plus a separate
bus-clock arrangement; changing the `compatible` string would not
initialize clocks or prove the registers/pin layout can be safely used by
XNU. See the mainline
[SM8150 DTS](https://code.googlesource.com/linux/torvalds/linux/+/9f7853d7609d59172eecfc5e7ccf503bc1b690bd/arch/arm64/boot/dts/qcom/sm8150.dtsi)
and [GENI serial implementation](https://code.googlesource.com/linux/torvalds/linux/+/23eb7901811a06805ec7d6e766dd82f083d03204/drivers/tty/serial/qcom_geni_serial.c).

## Safe bring-up requirements

1. Establish *independently* whether an accessible and electrically suitable UART TX/GND pair exists on the physical tablet. Do **not** connect USB-UART adapters to unspecified motherboard pads. Determine I/O voltage first; never connect 5 V or feed an unverified voltage into a test pad.
2. Correlate that port with the **specific** GENI serial engine, correct pinctrl states and clock/reset controls using device tree and upstream Qualcomm GENI driver code.
3. Inspect the firmware entry state without assuming Android's later configuration still holds. Avoid arbitrary writes to `0xA90000` or any MMIO register until the controller, clocks and physical port have been verified.
4. If suitable physical serial access cannot be established, research a separate USB-based diagnostic protocol with a minimal USB stack and complete host tests. USB enumeration on `fastboot boot` is not itself an XNU execution log.
5. Design a short, fail-safe, **read-only** trace format (timestamp, FDT identity, RAM layout summary, loader stage, error code), then validate on synthetic/mock peripherals before live device I/O.

## Current limits

- A roughly eight-second **PSCI reset is not equivalent to a captured log**.
- The ABL FDT may not include all TrustZone and boot firmware allocations. Static `/memory` containment cannot authorize kernel relocation or physical RAM writes.
- Android's `ramoops` and `cont_splash` regions are reserved; using them as writable diagnostic storage would require an independently verified interface and risk analysis. Do not poke them directly.
- Device is still running Android after each test. No XNU execution, display or iOS userland has been demonstrated.

## Research references

- [nabu Android device tree](https://github.com/dev-harsh1998/android_device_xiaomi_nabu)
- [Qualcomm SM8150 Android kernel tree](https://github.com/crdroidandroid/android_kernel_xiaomi_sm8150)
- [ios-sweet direct-ABL shim](https://github.com/dipa-studio/ios-sweet)

This document identifies **possible** diagnostics, not wiring instructions or a validated UART driver.
