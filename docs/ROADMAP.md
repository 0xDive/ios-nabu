# Porting roadmap

## Observed and reproducible milestones

- [x] Temporary Android boot v3 accepted by nabu ABL (`fastboot boot` reported OKAY).
- [x] Stage 2.1 PSCI system reset after approximately seven seconds, observed on one device.
- [x] Stage 3 second-stage payload hypothesis supported by ~10-second automatic reboot. It is *not* proof of XNU entry.
- [x] Host-side Apple Device Tree draft and Mach-O inspection prototype in Stage 4.
- [x] Import Stage 3 and Stage 4 research source and host test suites; exclude private DTB and device dumps.
- [x] Set up reproducible LLVM ARM64 diagnostic build with artifact integrity checks.
- [x] Build and test a read-only, temporary [Stage 6](../stage6/README.md) ARM64 ABL-time FDT memory probe; it classifies FDT-advertised RAM and known/dynamic reservations (host-side CI success, device outcome pending).
- [x] Observe an autonomous reset after approximately 8–10 seconds on real nabu with the first Stage 6 image (timing only, no persistent log; see [PR #14](https://github.com/0xDive/ios-nabu/pull/14) for subsequent FDT completeness fix).
- [x] Observe an approximately 8-second automatic restart with the strengthened Stage 6.1 parser on a real nabu; black screen, no persistent execution trace, no proof of runtime-writable RAM.
- [ ] Independently verify free RAM at ABL handoff; the FDT alone cannot prove all live firmware allocations.
- [x] Identify and decode the nabu Android-DTB GENI UART console (`0x00A90000` / GPIO85/86), including clock/pinctrl phandles; add [read-only Stage 7 tools](../stage7/README.md) and CI mocks.
- [x] Host-compile Qualcomm SM8150 U-Boot v2026.07 with the USB ACM and recorded-console options, with Fastboot flash/OEM arbitrary commands and capsule updates disabled ([PR #20](https://github.com/0xDive/ios-nabu/pull/20)).
- [x] Host-compile publicly sourced Xiaomi Pad 5 DTS/DTB with matching SM8150 SoC/PMIC files and a full ARM64 U-Boot ELF that embeds that DTB. Validate `xiaomi,nabu qcom,sm8150` separately in the DTB and the U-Boot build. [Passing CI](https://github.com/0xDive/ios-nabu/actions/runs/39322222486); **not tested on tablet**.
- [ ] Establish an electrically and firmware-verified early-boot UART or USB logging transport independent of unverified framebuffer addresses. Building a U-Boot ELF with nabu DTS is not proof of safe USB controller/Type-C role, ROM/ABL ABI, RAM or XNU logging.
- [x] Compile `kernel.development.nabu` as an ARM64 Mach-O on macOS, using **mechanically adapted SWEET identifiers**, and verify 19 segments and entry VA. ([CI](https://github.com/0xDive/ios-nabu/actions/runs/39295105141))
- [ ] Replace mechanical identity changes with validated SM8150-specific PlatformExpert and driver implementations.
- [x] Implement offline-only ADT and `boot_args` v2 schema with independent tests.
- [x] Validate the compiled XNU Mach-O file-only `__CTF` segment, 32 MiB virtual-base mapping, real DTB inventory schema, and offline Stage 5 proposed copy/BSS operation plan ([#9](https://github.com/0xDive/ios-nabu/pull/9), [#10](https://github.com/0xDive/ios-nabu/pull/10)).
- [ ] Verify *runtime* Mach-O placement and any required rebases against firmware/ABL allocations before executing an XNU payload.
- [ ] Controlled temporary XNU entry test using `fastboot boot`, no partition writes.
- [ ] Bring up IRQ/clock/CPU on SM8150 with `cpus=1` initially.
- [ ] UFS read-only proof of concept; subsequently display, touch, networking.
- [ ] Investigate lawful iOS userland and driver requirements; *not a short-term deliverable*.

## Technical checkpoints

**Boot ABI:** nabu uses Android boot image header v3 and `vendor_boot`. Do not directly reuse sweet v2 boot packaging or its ramdisk assumptions.

**Firmware interface:** on the running Android FDT, PSCI 1.0 uses `smc`; confirm equivalent configuration at experimental image entry.

**Interrupts/timers:** observed GICD `0x17a00000`, GICR `0x17a60000`, 19.2 MHz arch timer.

**RAM:** candidate `0x100000000..0x1f0000000` was an offline non-intersecting *draft*, not validated runtime-free RAM. Do not use it for kernel writes without collision proof.

**Display:** `cont_splash_region=0x9c000000` does not establish a safely writable framebuffer. No raw writes to this region.

**References:** [ios-sweet](https://github.com/dipa-studio/ios-sweet), [UniXNU](https://github.com/UniXNU/UniXNU), [nabu device tree](https://github.com/dev-harsh1998/android_device_xiaomi_nabu).
