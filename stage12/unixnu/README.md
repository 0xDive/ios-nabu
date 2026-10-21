# Stage 12b — UniXNU/DarwinBoot integration research for Xiaomi Pad 5

**Current state: source-contract preflight only. No bootable XNU or iOS image.**

UniXNU already boots XNU-derived iPadOS on the different SM8550 `sheng` board. Its hardware-specific ADT, trust cache configuration, device identity, physical DRAM and userdata layout are **not valid for nabu**, even though both are Xiaomi tablets.

## What is already working in our repository

The existing [XNU nabu compile workflow](../../.github/workflows/xnu-nabu.yml) has previously produced a valid **Mach-O AArch64** file for XNU 8796, using mechanically staged Qualcomm sweet research patches. This is compile evidence only. The repository also contains offline ADT, boot_args and Mach-O handoff planning tests. Do not throw these away or mistakenly treat them as a functional native XNU port.

## What UniXNU supplies

- `UniXNUPkg` UEFI application and registrar.
- `DarwinBootPkg/Driver/DarwinBoot.inf`, a UEFI driver publishing `gUniXNULoaderProtocolGuid`.
- Native 4 KiB XNU patches for non-Apple ARM64, including bootstrap table sizing, userspace alignment and the transition from CodeDirectory 16 KiB signed chunks to 4 KiB hardware pages.
- A new kernel base: Apple's **XNU 10063.141.1**, not the existing XNU 8796 compiled for nabu.
- Sheng-only drivers for SM8550, Adreno 740, Novatek NT36532E and its UFS/SMMU layout. They cannot be copied unchanged onto SM8150 / Adreno 640.

The pinned source contracts live in [nabu-reference.toml](nabu-reference.toml). The CI fetches immutable commits, verifies that source patches and DarwinBoot EFI package still exist, and emits `nabu-unixnu-reference-preflight.json` with `safe_to_boot: false`.

## Integration path (no partition modifications)

1. **UEFI branch:** build upstream Mu-Silicium `nabuPkg` and audit the Android boot container. Prove the resulting image reaches a menu via a separately approved *temporary* `fastboot boot` test. The vendor binary/DTB UEFI configuration uses Android boot **header v1**, not our previously tested edk2-msm v3.
2. **Firmware API layer:** build UniXNUPkg and DarwinBoot as separately reviewed EFI modules against the *same* Mu-Basecore revision and ABI used for `nabuPkg`, then validate GOP, SimpleFS, BlockIO, and input protocols. Avoid installing it into nabuPkg before a safe EFI build/hardware baseline.
3. **XNU source layer:** port UniXNU's 4 KiB XNU 10063 changes to nabu using an actual SM8150 machine implementation. Our previously compiled XNU 8796 is **not ABI-compatible by declaration**.
4. **Read-only payload:** build a small RAM-carried test config and verified ADT/boot_args, only once the nabu physical DRAM map at ABL handoff and early kernel logging are proven. No userdata writes or iPadOS system images.
5. **Only then:** a single temporary boot test, with old Android boot preserved and known recovery.

**Do not copy sheng's `first_lba`, `last_lba`, `root_match_volume_uuid`, `chip_id` or IPSW device identity into a nabu target.** Do not add `fastboot flash userdata` from the sheng instructions to our workflow.

This stage is independent of the original EDK2 USB diagnostics. Mu-Silicium's nabu status also reports USB Host Mode unavailable, so a successful firmware build would not fix the keyboard.
