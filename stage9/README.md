# Stage 9 — nabu USB2 OTG / HS PHY preflight (host-only)

**This is an offline DTB audit, not a USB hardware test and not a bootable kernel.**

The preceding stages proved two separate facts: pinned U-Boot v2026.07 compiles for AArch64, and a publicly sourced `sm8150-xiaomi-nabu.dts` can be compiled and embedded in a U-Boot ELF. Neither proves DWC3, PM8150B Type-C, early clocks/PHY resets, safe RAM relocation or XNU logging on the real tablet.

## Hardware topology and sources

| Observation | Public mainline nabu DTS (host-built) | User's running-Android vendor DTB (private, offline) |
| --- | --- | --- |
| USB1 DWC3 register base | `0x0A600000` | `0x0A600000` |
| USB1 mode | OTG | OTG |
| USB1 maximum speed | High-Speed (USB 2.0) | High-Speed (USB 2.0) |
| USB1 PHY | `0x088E2000` HS PHY, sole `phys` entry; QMP SuperSpeed PHY disabled | HS PHY at `0x088E2000`, QMP SS PHY `0x088E8000` disabled; downstream driver uses different PHY properties |
| USB1 wrapper | `0x0A6F8800` | Downstream Qualcomm USB controller with wrapper at `0x0A600000`, different binding |
| USB2 DWC3 register base | `0x0A800000` | `0x0A800000` |
| USB2 mode | Host-only | Host-only |
| USB2 maximum speed | High-Speed (in published mainline board DTS) | SuperSpeed Plus (in Android vendor DTB) |
| Type-C role mechanism | `usb-role-switch`/PM8150B | Qualcomm downstream USB-PD/charger bindings; not interchangeable |

The public nabu DTS is pinned to [SeimoDev/linux-xiaomi-nabu, commit `4e6d08bb`](https://github.com/SeimoDev/linux-xiaomi-nabu/blob/4e6d08bb1b467c721e19cd693e4ec7388d982d73/arch/arm64/boot/dts/qcom/sm8150-xiaomi-nabu.dts). The Android DTB was supplied privately by the owner and is not committed or uploaded. Its values describe running Android, **not necessarily the earlier ABL firmware state**.

## What the gate does

[usb_dtb_gate.py](tools/usb_dtb_gate.py) parses **compiled FDT bytes**, not just Linux DTS text, and checks:

- The root identifies `xiaomi,nabu` / `qcom,sm8150`.
- Both DWC3 cores exist at their exact physical addresses, with enabled parent wrappers.
- USB1 is OTG, High-Speed, its single `usb2-phy` is resolved by phandle to the enabled PHY at `0x088E2000`, with no active SuperSpeed PHY.
- `usb-role-switch` is declared for USB1; USB2 stays in host mode.
- The Qualcomm USB1 wrapper uses the expected `0x0A6F8800` base.

**The checks do not verify that Type-C actually negotiates peripheral mode, or that the PMIC enables necessary rails and clocks from ABL.** A DTB can contain complete data and still fail to drive any hardware in U-Boot.

## Run the tools

From the repository root with Python 3:

```bash
python3 -m unittest discover -s stage9/tests -v
python3 stage9/tools/usb_dtb_gate.py \
  --kind public --dtb /private/sm8150-xiaomi-nabu-public.dtb \
  --out /private/nabu-public-usb-report.json
```

The U-Boot Stage 8.1 GitHub Actions workflow generates this report in CI from its *temporary* compiled public nabu DTB. Only the sanitized JSON, not the raw DTB, is uploaded.

To inspect a **personal Android** DTB locally, without sending it anywhere:

```bash
python3 stage9/tools/usb_dtb_gate.py \
  --kind android --dtb /private/nabu.dtb \
  --out /private/nabu-android-usb-report.json
```

The Android report deliberately does not demand the mainline `phys` and `usb-role-switch` bindings, because the downstream USB driver uses different properties. This is not a certificate of early-boot usability.

## Remaining hard blockers

1. We have no confirmed physical memory allocation/relocation contract from ABL. Stage 6.1's reset timing cannot prove a range is free.
2. Bootloader-time PM8150B Type-C / HS PHY regulator/clock/reset behavior has not been validated on nabu.
3. USB gadget enumeration and Fastboot-recorded-console output on nabu are **not tested**.
4. Even functioning U-Boot USB logs end when handing off; XNU needs its own transport.
5. The compile-only XNU kernel still has unreviewed SM7150-derived platform code.

Until these are resolved, **no host-built U-Boot or XNU ELF should be passed to `fastboot boot` or flashed**.
