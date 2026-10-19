# ios-nabu — experimental XNU / iOS port for Xiaomi Pad 5

> **Research project. Not a working iOS/iPadOS port or an installable ROM.**
>
> **Проект экспериментальный:** iOS пока **не загружается**. Не прошивайте Android-разделы и не считайте черновые ADT или boot images готовыми прошивками.

Target device: **Xiaomi Pad 5 (codename `nabu`, Qualcomm Snapdragon 860 / SM8150)**.

The project explores booting an ARM64 XNU kernel on nabu, using a minimal ABL-compatible boot chain inspired by [ios-sweet](https://github.com/dipa-studio/ios-sweet) (Redmi Note 10 Pro) and hardware information from [android_device_xiaomi_nabu](https://github.com/dev-harsh1998/android_device_xiaomi_nabu). [UniXNU](https://github.com/UniXNU/UniXNU) is another useful reference; this repository currently follows the direct-ABL approach.

## Progress (2026-10-19)

| Milestone | State | Evidence |
|---|---|---|
| Stage 1 — temporary Android boot v3 diagnostic | Observed black screen | `fastboot boot` reported OKAY. Not evidence of framebuffer output. |
| Stage 2.1 — bare-metal FDT + PSCI reset | **Observed** | Device reportedly rebooted without pressing buttons, approximately seven seconds after start. |
| Stage 3 — payload in initrd, second-stage handoff | **Likely** | Device reportedly rebooted automatically after ~10 s; distinct failure path waits ~27 s. Timing is indicative, not a trace. |
| Stage 4 — offline ADT draft and Mach-O inspection | **Host-side only** | Prototype tools and local tests; **no XNU boot image**. |
| Stage 5 — actual XNU entry on nabu | **Not started / not demonstrated** | Requires adapted kernel, memory placement, boot_args, logging. |
| iOS userland, graphics, touch, network | **Not implemented** | Requires much more platform and driver work. |

## Hardware observations

Based on a locally inspected user-provided Linux FDT (not uploaded to this repository):

- PSCI 1.0 through `smc`, GICv3, 8 CPU nodes.
- GIC distributor `0x17a00000`; redistributor `0x17a60000`.
- ARM timer frequency 19.2 MHz; UFS controller `0x01d84000`.
- `cont_splash_region` at `0x9c000000` is **reserved memory**, **not** a proven writable framebuffer.
- Draft memory selection is **not** a runtime-safe allocation.
- A DTB obtained from **running Android** is not guaranteed to match the one passed by the bootloader.

## Repository layout

- `stage3/` — conservative diagnostic ABL shim + separate ARM64 payload from Android ramdisk.
- `stage4/` — offline-only DTB/ADT/Mach-O analysis tools (not a bootable OS).
- `docs/` — porting notes, safety limits, roadmap.
- `.github/workflows/` — host-side Python tests and LLVM ARM64 build checks.

## Building and experimenting

For the Stage 3 diagnostic source and build, see [stage3/README.md](stage3/README.md). For the Stage 4 offline utilities, see [stage4/NOTES.md](stage4/NOTES.md). **Do not flash any partition** from this repository. Temporary `fastboot boot` can still hang or reset the device and does not eliminate hardware risk.

No Apple proprietary firmware, IPSW, decrypted system image, device dumps, keys, private serials, personally sourced DTB, or custom boot images are distributed here. Use legal, appropriately licensed inputs and review any third-party code/licenses before redistribution.

## Immediate engineering tasks

1. Add broader negative tests for malformed FDT, ADT, Mach-O and boot images; run Stage 3/4 tests and LLVM cross-compilation in GitHub Actions.
2. Audit RAM layout and bootloader ABI; establish a reliable diagnostic output path (UART/USB/log buffer with verified mapping).
3. Create an XNU kernel source/patch strategy for SM8150 based on public XNU and upstream research; **do not** copy non-redistributable Apple components.
4. Validate Mach-O structure and segment mapping offline before even considering a temporary boot.
5. Bring up XNU in single-CPU diagnostic mode, then platform devices, storage, display and userland.

Contributions and careful hardware reverse-engineering are welcome. **No claims of working iOS on nabu yet.**
