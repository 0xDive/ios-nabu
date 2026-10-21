# Stage 12c — UniXNU + DarwinBoot linked inside the nabu firmware volume (host-only)

The photographed [Project Silicium UEFI build](https://github.com/0xDive/ios-nabu/actions/runs/39621575550) **did boot on Xiaomi Pad 5**. The firmware drew its logo and reached BDS, which reported `MsBootPolicy.efi: Not Found` and then tried USB storage with no devices. These are **BDS findings**, not an ARM64 exception, and do not prove that any operating system booted.

We now integrate upstream [UniXNU](https://github.com/UniXNU/UniXNU) firmware application and [DarwinBoot](https://github.com/UniXNU/DarwinBoot) loader **without the UniXNUDxe registrar**. The registrar writes `Boot####` and `BootOrder` variables; to protect the user's original Android boot and preserve the proven baseline, it is intentionally excluded. Accordingly the linked `UniXNU.efi` is **not auto-started** and this milestone is purely an offline FV/link test.

## Pinned code
- [UniXNU 97de9e7](https://github.com/UniXNU/UniXNU/commit/97de9e715e06d77b8ebe7b80f6e556ee7ab9a7e9).
- [DarwinBoot 85332b3](https://github.com/UniXNU/DarwinBoot/commit/85332b317ee80898fc78939ea64e6ca52d3837a3).
- [Mu-Silicium 0eb4514](https://github.com/UniXNU/uefi-sheng/commit/0eb4514db0744b8136a3897ab1af93b713c2c27b).
- In CI, source packages are copied under `mu-silicium/UniXNUPkg` and `mu-silicium/DarwinBootPkg`. Our `integrate_fv.py` adds the application and loader to nabu DSC and FDF (same FV), plus required libraries. It does **not** modify RAM region tables, USB PHY, PMIC, GPT, the FD allocation, or the Qualcomm binaries.

## Output (only after successful EDK2 link + FD size audit)
The Actions artifact contains `UniXNU.efi`, `DarwinBoot.efi`, source hashes and a host-only audit JSON. A boot image is built for validation inside CI **but deliberately is not published**, since nothing on the tablet can launch the application yet without additional, reviewed BDS work. We refuse to increase FD_SIZE beyond the original 3 MiB just to make the link pass.

## Not yet accomplished
- No registered UniXNU boot entry or automatic boot.
- No XNU Mach-O, IPSW, Apple iOS system image, trustcache or userdata root.
- No safe/validated nabu XNU 10063 kernel hardware entry.
- No USB Host or touch driver fix for UEFI.

Next step after a successful link: design a **volatile-only** / strictly nonpersistent boot-selection method, compare the proprietary QcomBds behavior and validate in CI before offering another temporary fastboot image. Absolutely **no flashing**, BootOrder NVRAM writes, or permanent bootloader changes.
