# Porting roadmap

## Observed and reproducible milestones

- [x] Temporary Android boot v3 accepted by nabu ABL (`fastboot boot` reported OKAY).
- [x] Stage 2.1 PSCI system reset after approximately seven seconds, observed on one device.
- [x] Stage 3 second-stage payload hypothesis supported by ~10-second automatic reboot. It is *not* proof of XNU entry.
- [x] Host-side Apple Device Tree draft and Mach-O inspection prototype in Stage 4.
- [ ] Import and audit original Stage 3 and Stage 4 source and host test suites.
- [ ] Set up reproducible cross-compiler build and artifact integrity checks.
- [ ] Validate exact boot ABI, runtime memory reservations, and FDT placement from ABL.
- [ ] Establish a logging transport independent of unverified framebuffer addresses.
- [ ] Build an ARM64 XNU Mach-O with target-specific PlatformExpert changes.
- [ ] Verify all Mach-O segments and rebases against non-overlapping physical RAM.
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
