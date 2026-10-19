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

## Stage 9.1: observe actual Android USB gadget state via rooted Termux

The [read-only Termux helper](tools/termux_usb_status.sh) enumerates only
selected USB1/USB2 platform devices, kernel USB Device Controllers (UDCs)
and Type-C port role/status values. It does **not** mount debugfs, read
serial numbers/descriptors/bootargs, rebind drivers, write gadget settings,
or modify PHY/PMIC/GPIO registers.

On a nabu running **normal Android**, with KernelSU root if needed:

```sh
su -c 'sh -s' < "$HOME/termux_usb_status.sh" > "$HOME/nabu-usb-status.txt" 2>&1
```

Useful fields are UDC names such as `a600000.dwc3`, `state`,
`current_speed`, `maximum_speed`, and (if exposed by the kernel's
Type-C class) `data_role`/`power_role`/`port_type`.
Unavailable data means **unknown**; it is not a failure or reason to
force a clock/PHY/role switch.

A successfully configured Android USB gadget would show that the
hardware/controller is usable by the running Android kernel. It **cannot**
prove that Qualcomm ABL hands the controller to U-Boot in the same state,
that U-Boot's USB drivers work, or that XNU can continue logging after
U-Boot exits. Host tests execute the script only on synthetic sysfs
fixtures; no tablet is accessed in CI.

## Stage 9.2: measured nabu USB gadget registration, not yet an active link

The user supplied a **read-only rooted Termux** observation from running
Android:

| Kernel sysfs path or attribute | Observed value |
| --- | --- |
| `/sys/class/udc/` | `a600000.dwc3` |
| `state` | `not attached` |
| `current_speed` | `UNKNOWN` |
| `maximum_speed` | `high-speed` |
| `is_otg` | `1` |
| `/sys/class/typec/port*` | No matching ports reported |

This **confirms UDC registration, hardware OTG capability reported by the
driver and a High-Speed maximum**, consistently with the USB1 public DTB.
It does **not** confirm an active host connection, USB gadget driver binding,
USB enumeration or even whether the cable was connected at the snapshot
time. `/sys/class/typec` being empty also does not mean the physical
Type-C port or PM8150B Type-C controller is missing; Qualcomm vendor
kernels may expose roles through other classes.

Linux defines these statuses in
[`sysfs-class-udc`](https://github.com/torvalds/linux/blob/master/Documentation/ABI/stable/sysfs-class-udc).
Actual state reporting varies between UDC implementations.

The new [read-only link snapshot helper](tools/termux_usb_link.sh)
records **only** the allowlisted UDC state, speed and OTG fields, whether a
gadget driver name is nonempty (without exposing it), optional
`/sys/class/power_supply/usb/online` and optional
`/sys/class/usb_role/*/role`. It never reads USB serials/descriptors,
changes USB gadget configuration, switches Type-C roles or uses raw MMIO.

Run once with the cable disconnected and once with an ordinary, known
data-capable USB cable connected to a PC. To execute the repository script
from Termux, copy it into the Termux home directory first; no download is
required if you use the equivalent inline commands from the project
discussion:

```sh
su -c 'sh -s disconnected' < "$HOME/termux_usb_link.sh" > "$HOME/usb-disconnected.txt" 2>&1
# Connect normally to the PC; don't modify USB settings.
su -c 'sh -s connected' < "$HOME/termux_usb_link.sh" > "$HOME/usb-connected.txt" 2>&1
```

The `connected`/ `disconnected` labels are **operator-supplied**; they do
not prove the cable state. If USB remains `not attached`, investigate
Android gadget binding, power detection and data cable/host conditions
before blaming the DWC3 controller. A `configured` status on the running
Android kernel is useful but **still not proof** that U-Boot can enumerate
at ABL handoff or that XNU can log over USB.

## Remaining hard blockers

1. We have no confirmed physical memory allocation/relocation contract from ABL. Stage 6.1's reset timing cannot prove a range is free.
2. Bootloader-time PM8150B Type-C / HS PHY regulator/clock/reset behavior has not been validated on nabu.
3. USB gadget enumeration and Fastboot-recorded-console output on nabu are **not tested**.
4. Even functioning U-Boot USB logs end when handing off; XNU needs its own transport.
5. The compile-only XNU kernel still has unreviewed SM7150-derived platform code.

Until these are resolved, **no host-built U-Boot or XNU ELF should be passed to `fastboot boot` or flashed**.
