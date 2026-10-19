# Porting XNU to Xiaomi Pad 5 (nabu / SM8150)

## Upstream and reproducible baseline

The most useful reference is [dipa-studio/ios-sweet](https://github.com/dipa-studio/ios-sweet) at commit `fdad0de8dc0e75c5ea84762adc03f7232dc91f19` (2026-10-18), which uses [blacktop/darwin-xnu-build](https://github.com/blacktop/darwin-xnu-build) pinned to `663906528d1cd5ea8fde7de6f16de73db9511549`.

The sweet workflow builds XNU 8796 (macOS 13.5 / iOS 16 generation), with a dedicated `SWEET` machine configuration, on macOS arm64. The sweet patch series is **not vendored** here pending review of provenance, license and which hunks are actually required for SM8150. We will not copy or republish proprietary Apple firmware/system images.

## Patch groups to adapt

| Sweet reference | What nabu needs |
| --- | --- |
| 0004 machine config | New `NABU` target; ARMv8.2 cores without Apple implementation registers/PAC; investigate 16K pages, pmap and cache line assumptions |
| 0016 PlatformExpert | An independent `NabuPlatformExpert`, registration matched to `xiaomi,nabu`, and valid ADT node properties |
| 0017 virtual timer | Virtual timer PPI: INTID 19 from the running-Android nabu DTB, confirm firmware entry state |
| 0018 CPU bring-up | Single boot CPU, then PSCI SMP; check MPIDR and GICR mapping before secondary CPUs |
| 0028 / 0034 / 0069 UFS | SM8150 UFS registers and DMA/IOMMU setup; read-only proof before any writes |
| 0046 / 0056 display | No framebuffer format/stride established; **never write to splash reservation based on its address alone** |
| 0060 / 0063 / 0071 touch | Sweet's Goodix input stack is not the nabu Novatek SPI device driver |
| 0065 / 0078 SMP | Secondary CPU startup and interrupt routing must be verified separately |
| 0072–0077 USB | Independent Qualcomm USB controller, clocks and endpoint setup; no assumption that sweet works unchanged |

## Verified from user-supplied running-Android DTB

See [include/nabu_hw.h](include/nabu_hw.h). Eight CPU nodes, PSCI 1.0 via SMC, GICv3 GICD PA `0x17A00000`, GICR PA `0x17A60000`, virtual timer INTID 19 and UFS PA `0x01D84000` were observed. The raw DTB stays on the user's computer, not in GitHub.

**These are evidence about Linux FDT, NOT bootloader/runtime guarantees.** In particular, Stage 4's proposed DRAM region `0x100000000..0x1F0000000` has not been proven free at the early kernel entry point.

## First XNU-specific milestones

1. Pin upstream references and verify that all needed patches may legally be used and modified.
2. Make a minimal `NABU` build target, no framebuffer, UFS, touch or userland.
3. Compile raw ARM64 XNU Mach-O in a macOS workflow and inspect segments/entry/relocations offline.
4. Establish a trustworthy diagnostic channel and prove bootloader-time free memory before doing kernel relocation.
5. Prepare a versioned `boot_args` and complete ADT that matches the kernel build. Use one CPU.
6. Only then consider a temporary fastboot image that transfers control to XNU.

**Not done yet:** an adapted or compiled NABU XNU kernel, kernel-entry hardware trace, iOS userland launch, touch/display operation or an installable image.

## Safety

No partition flash operations; no moving the user's Android OS or userdata. Treat all device-specific data as potentially private. See [../docs/SAFETY.md](../docs/SAFETY.md).
