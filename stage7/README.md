# Stage 7 — read-only Qualcomm GENI UART discovery for nabu

**Goal:** find a trustworthy early-boot log channel for a future XNU loader on Xiaomi Pad 5. **No UART output from ABL or XNU is demonstrated yet.**

The black-screen Stage 6 and 6.1 diagnostics each reportedly auto-restarted after roughly 8–10 seconds. That timing is indirect and does not reveal which firmware nodes or hardware resources were active. We will **not** assume an unknown framebuffer address, probe arbitrary physical memory, change clocks/pins, or attach a USB-UART adapter to unverified motherboard test points.

## The concrete candidate in the user's Android DTB

A privately inspected Xiaomi Pad 5 `nabu.dtb` contains:

| Observation | Running-Android FDT value |
| --- | --- |
| Controller path | `/soc/qcom,qup_uart@0xa90000` |
| Vendor compatible | `qcom,msm-geni-console` |
| Status | `ok` |
| Register range | `0x00A90000` + `0x4000` |
| Interrupt | GIC SPI 357 (architectural INTID 389) |
| Clock names | `se-clk`, `m-ahb`, `s-ahb` |
| Pin state 0 | `qupv3_se12_2uart_active`: `qup12` on `gpio85` and `gpio86` |
| Pin state 1 | `qupv3_se12_2uart_sleep`: GPIO mode for the same pins |
| `/chosen/stdout-path` | Not specified in the inspected DTB |

In mainline Linux's `sm8150.dtsi`, the same controller base `0x00A90000` is described as `qcom,geni-debug-uart`, IRQ 357, clock `GCC_QUPV3_WRAP1_S4_CLK`, and **disabled by default** at SoC level. Vendor Android code uses another compatible and can enable the controller in a board-specific way. **Matching the MMIO address does not prove that either driver can run from ABL, that UART clocks are enabled, or that any test pad exposes TX.**

Relevant public source:
- [SM8150 Device Tree (mainline kernel)](https://code.googlesource.com/linux/torvalds/linux/+/9f7853d7609d59172eecfc5e7ccf503bc1b690bd/arch/arm64/boot/dts/qcom/sm8150.dtsi)
- [GENI UART driver, console and earlycon setup](https://code.googlesource.com/linux/torvalds/linux/+/23eb7901811a06805ec7d6e766dd82f083d03204/drivers/tty/serial/qcom_geni_serial.c)

## 1. Inspect a *local* nabu DTB, entirely offline

With Python 3 installed, from the repository root:

```powershell
py -3 .\stage7\tools\uart_dtb.py --dtb C:\private\nabu.dtb --out C:\private\uart-dtb-summary.json
```

Linux:

```bash
python3 stage7/tools/uart_dtb.py --dtb /private/nabu.dtb --out /private/uart-dtb-summary.json
```

The report describes only supported UART nodes, their mapped registers, IRQ, clock dependencies and pinctrl phandles. It deliberately excludes bootargs, private serial numbers, MAC addresses, user data and raw vendor DT properties. **The input DTB must remain outside the public repository.**

## 2. Observe the *running Android* UART driver, without changing anything

Boot the tablet into normal Android (not FASTBOOT), enable authorized ADB debugging and use Google platform-tools. No root is required for basic checks:

```powershell
py -3 .\stage7\tools\adb_uart_readonly.py --out C:\private\uart-android-status.json
```

If the tablet permits KernelSU root, optionally collect extra **read-only** debugfs information:

```powershell
py -3 .\stage7\tools\adb_uart_readonly.py --root --out C:\private\uart-android-root-status.json
```

The script first requires exactly one authorized connected Android device with `ro.product.device=nabu`. It reads only `/proc/consoles`, names from `/sys/class/tty`, already-mounted `/sys/kernel/debug/clk/clk_summary`, and pinmux listing files underneath an existing `/sys/kernel/debug/pinctrl/` directory. It returns a **filtered summary**, not full debugfs files. It will **never** run mount/insmod/setprop/su writes, `fastboot`, `devmem`, raw `dmesg`, `/proc/cmdline`, or GPIO operations.

If debugfs isn't mounted or permissions deny access, the information is **unknown**, not a reason to enable it or alter Android. Android `ttyMSM0` existence is not proof that ABL leaves the same serial engine initialized.

## 2a. Termux follow-up: map TTY to physical UART (read-only)

The user's rooted Termux snapshot found that `ttyHS0` is **not** the
debug-console candidate: its sysfs `device` resolves to
`/sys/devices/platform/soc/c8c000.qcom,qup_uart`, driver
`msm_geni_serial`, OF compatible `qcom,msm-geni-serial-hs` and
`status=ok`. No UART entry appeared in `/proc/consoles`. Debugfs was
**not mounted**, so clock and GPIO pinmux status remain unknown.

For a more precise look, [termux_uart_sysfs.sh](tools/termux_uart_sysfs.sh)
reads *only* platform-device binding symlinks, selected safe DTB properties
(`status`, `compatible`, `clock-names`, `pinctrl-names`) and
UART-like tty mappings for `0xA90000`, `0xC8C000` and `0xA84000`.

Download or copy this reviewed script to your Termux home directory, then run:

```sh
su -c 'sh -s' < "$HOME/termux_uart_sysfs.sh" > "$HOME/nabu-uart-map.txt" 2>&1
```

Nothing is mounted or modified. The script does **not** probe MMIO or
physically touch GPIO85/86; its stdout is suitable for review after checking
for any local details you prefer not to share. A platform device with
`driver=unbound-or-not-available` is **not** proof a UART is electrically
disabled or unavailable to the bootloader.

## Termux follow-up: controller binding clarification

A second owner-supplied rooted-Termux read-only snapshot further resolved the
same three physical QUP addresses:

- **`0xA90000`**: `a90000.qcom,qup_uart` platform device present;
  its FDT node declares `qcom,msm-geni-console`, `status=ok`,
  `se-clk/m-ahb/s-ahb` and pinctrl `default/sleep`.
  A plain `readlink -f .../driver` returned the `driver` path itself,
  **not a resolved platform driver**. This is insufficient to claim the
  device is Linux-driver-bound. Use `test -L .../driver` first.
- **`0xC8C000`**: `c8c000.qcom,qup_uart` is driver-bound to
  `msm_geni_serial`; `ttyHS0` maps here, not to `0xA90000`.
- **`0xA84000`**: the *active* platform device is `a84000.i2c`,
  driver `i2c_geni`. The separate UART DT node at the same address is
  `disabled`. **Same QUP address does not mean active UART**.
- Debugfs remains unmounted, so clock runtime state and GPIO85/86 pinmux
  status remain unknown. Do not mount it merely to force a result.

[The updated Termux checker](tools/termux_uart_sysfs.sh) now treats a driver
binding as confirmed only when a real `driver` symlink and target are
present, and separately labels the I²C protocol device rather than counting
it as a UART. These are facts about *running Android*, not ABL entry.

## 3. Interpretation and future work

Useful evidence is agreement across the private DTB, Android's active UART console device (if present), and a clock/pinmux reading that refers specifically to the `0xA90000` controller. Even that only proves a **running-Android state**. It does not reveal the electrical pin voltage, board test points or the UART state at ABL handoff.

Before emitting bytes from bare metal we still need to confirm actual pin accessibility or choose a different supported output channel, establish the UART clock/reset/voltage configuration and model the GENI driver through host tests. Never probe unverified physical pads or write registers by guessing. Raw `ramoops`/splash memory reservations are not writable logging scratchpads.

This stage intentionally has **no boot.img** and does not load XNU. Source and unit tests are in `stage7/tools` and `stage7/tests`; run `python3 -m unittest discover -s stage7/tests -v`.

See also [early-console research](../docs/EARLY_CONSOLE.md) and [issue #15](https://github.com/0xDive/ios-nabu/issues/15).
