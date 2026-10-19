# Stage 11 — PM8150B Type-C, USB2 PHY supplies and early-boot gaps

**Host-only inspection of public Xiaomi Pad 5 Device Tree and pinned U-Boot source. No MMIO, hardware writes, boot image or XNU device execution.**

## Why

On a real Xiaomi Pad 5 (`nabu`) with stock Android running, the owner verified that the **primary USB gadget works**:

```text
UDC: a600000.dwc3
state=configured
current_speed=high-speed
maximum_speed=high-speed
is_otg=1
gadget_driver=assigned
usb_power_online=0
```

This proves the Linux/Android USB1 DWC3 gadget reached an active configured state over a data cable connected to a PC. `usb_power_online=0` belongs to the charging/power supply subsystem and must **not** be interpreted as a failed USB data connection. This says nothing about what ABL leaves on at U-Boot entry.

## Board wiring documented by the *public Linux nabu DTS*

Source: [SeimoDev/linux-xiaomi-nabu, exact commit `4e6d08bb1b467c721e19cd693e4ec7388d982d73`](https://github.com/SeimoDev/linux-xiaomi-nabu/blob/4e6d08bb1b467c721e19cd693e4ec7388d982d73/arch/arm64/boot/dts/qcom/sm8150-xiaomi-nabu.dts). The pinned board and matching SoC/PMIC source DTSI are compiled into the Stage 8.1 host-only DTB; the owner's vendor DTB stays private.

| Dependency | Published nabu DTS description | What is actually established |
| --- | --- | --- |
| USB1 core | DWC3 `0x0A600000`; OTG; High-Speed (USB 2.0), `usb-role-switch` | Android runtime enumeration independently observed |
| Qualcomm USB wrapper | `0x0A6F8800`, `qcom,select-utmi-as-pipe-clk` | Source addresses and compatible match; not clock/reset state |
| Primary HS PHY | `0x088E2000`, `qcom,sm8150-usb-hs-phy` | Driver match exists in U-Boot |
| PHY PLL rail | `vdda-pll-supply` -> `vreg_l5a_0p8`, **0.880 V** | Regulator voltage *constraint in DTB*, not measured rail power |
| PHY digital rail | `vdda18-supply` -> `vreg_l12a_1p8`, **1.800 V** | Same limitation |
| PHY analog rail | `vdda33-supply` -> `vreg_l2a_3p1`, **3.072 V** | Same limitation |
| USB-PD PHY rail | PM8150B `vdd-pdphy-supply` -> same `vreg_l2a_3p1` | Shared regulator graph, no runtime probe |
| Type-C controller | `qcom,pm8150b-typec`, enabled | Enabled in board DTB, **not** proof of a U-Boot driver |
| Connector | `usb-c-connector` with dual data/power roles; reciprocal `remote-endpoint` graph to USB1 HS endpoint | DTB graph only; CC/role negotiated state at ABL entry is unknown |
| USB VBUS source | `qcom,pm8150b-vbus-reg`, enabled | A **source-mode power regulator**, not the same as host-provided VBUS detection |

## What pinned U-Boot v2026.07 actually implements

Pinned SHA: `ece349ade2973e220f524ce59e59711cc919263f`.

- [`drivers/usb/dwc3/dwc3-generic.c`](https://github.com/u-boot/u-boot/blob/ece349ade2973e220f524ce59e59711cc919263f/drivers/usb/dwc3/dwc3-generic.c): Qualcomm generic DWC3 glue, clocks/resets, UTMI switch and software VBUS override. **It writes QSCRATCH registers**.
- [`drivers/phy/qcom/phy-qcom-snps-femto-v2.c`](https://github.com/u-boot/u-boot/blob/ece349ade2973e220f524ce59e59711cc919263f/drivers/phy/qcom/phy-qcom-snps-femto-v2.c): matching SM8150 HS PHY, but the inspected PHY implementation does **not explicitly acquire the board's `vdda-*` regulators**. This does not rule out supplies being handled elsewhere or by earlier firmware.
- [`drivers/power/regulator/qcom_usb_vbus_regulator.c`](https://github.com/u-boot/u-boot/blob/ece349ade2973e220f524ce59e59711cc919263f/drivers/power/regulator/qcom_usb_vbus_regulator.c): **real** PM8150B `qcom,pm8150b-vbus-reg` driver exists. Importantly, its probe and enable/disable methods **write Qualcomm PMIC registers through SPMI**. This is mostly about sourcing VBUS in host mode, **not** proof that nabu can operate as a USB gadget with a PC acting as the source.
- [`drivers/usb/tcpm/Makefile`](https://github.com/u-boot/u-boot/blob/ece349ade2973e220f524ce59e59711cc919263f/drivers/usb/tcpm/Makefile) and [TCPM Kconfig](https://github.com/u-boot/u-boot/blob/ece349ade2973e220f524ce59e59711cc919263f/drivers/usb/tcpm/Kconfig): generic TCPM and FUSB302 support. The inspected Type-C/TCPM and Qualcomm PMIC C sources have **no `qcom,pm8150b-typec` match**. Qualcomm's PM8150B Type-C/CC driver integration remains an engineering gap.

The presence of source code does **not** prove the corresponding driver is compiled: Stage 11 also records the actual final `CONFIG_DM_REGULATOR_QCOM_USB_VBUS`, `CONFIG_DM_REGULATOR_QCOM_RPMH`, `CONFIG_TYPEC_TCPM` and `CONFIG_TYPEC_FUSB302` flags without inventing absent values.

Crucially, even **if** ABL leaves Type-C sink role established, U-Boot's driver model or the process of resetting/initializing the PHY could disrupt it. Forcing PMIC source-mode VBUS or directly toggling PHY registers would be an unjustified risk.

## Repeatable host-only gate

[`stage11/tools/typec_power_gate.py`](tools/typec_power_gate.py) consumes **only** a compiled *public* `nabu` DTB, pinned U-Boot tree and generated `.config`. It checks all three HS PHY supply phandles and their voltage constraints, PM8150B PD PHY's shared L2 rail, enabled Type-C and VBUS nodes, dual-role connector and bidirectional Type-C/USB1 endpoint graph. It separately checks source code evidence for VBUS support and the lack of a native PM8150B Type-C match in the inspected U-Boot drivers.

The output `nabu-pm8150b-typec-power-blockers.json` is a sanitized **blocker report**, with **`safe_to_boot: false`** regardless of how many static checks pass. It is uploaded by [the Stage 8.1 host-only CI workflow](../.github/workflows/uboot-nabu-dtb.yml). No U-Boot ELF, DTB, firmware, private Android image or owner's device data is distributed.

To run unit tests without accessing a device:

```bash
python3 -m unittest discover -s stage11/tests -v
```

## Still required before even a temporary `fastboot boot` of U-Boot

1. Prove safe physical RAM relocation and a recovery path **at actual ABL handoff**, not just from the Stage 6.1 PSCI reset.
2. Establish PM8150B Type-C device/sink role handling and the state left by ABL, accounting for Qualcomm USB QSCRATCH and PHY reset side effects.
3. Review the specific RPMh/SNPS HS PHY supply powering and clocks; their DTB voltage constraints are not runtime measurements.
4. Test U-Boot's actual USB gadget under a separately verified, recoverable device test — **not** by blindly reusing the host-compiled ELF.
5. Provide separate early logs for XNU itself after U-Boot exits. A U-Boot Fastboot console cannot observe subsequent XNU execution by itself.

The correct next code task is an **early-memory and Type-C/PHY initialization plan** with fail-closed checks, not a blind boot image or a speculative MMIO write experiment.
