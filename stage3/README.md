# Stage 3 — ABL-compatible ARM64 diagnostic handoff

**Observed on Xiaomi Pad 5 (nabu):** tester reported an autonomous reboot roughly 10 seconds after launching the temporary diagnostic Android boot v3 image. This supports—but does not conclusively prove—that the separate payload was executed. The failure/fallback code resets after approximately 27 seconds. This is **not XNU or iOS**.

The chain is:
1. Qualcomm ABL loads temporary Android boot v3 Linux-compatible ARM64 Image.
2. The shim validates `/chosen` in the boot-time FDT and checks the PSCI interface.
3. It locates a very small custom `NABU3PAY` payload in the ramdisk.
4. It verifies version, length, CRC32 and an expected token.
5. It copies five position-independent ARM64 instructions to a private buffer, runs them, checks the return token and requests a PSCI reboot.

The shim accesses no block devices. There is no UFS write or framebuffer write. Physical DRAM banks come from a running-Android nabu DTB, and the actual runtime address map **requires independent verification**.

## Offline build

On Ubuntu or WSL:

```bash
sudo apt-get update
sudo apt-get install -y clang lld llvm binutils python3
bash stage3/build.sh
python3 -m unittest discover -s stage3/tests -v
```

The build produces a temporary test image in `stage3/out`. It is excluded from version control and is not a tested production or XNU image. **Do not flash device partitions.** See [safety guidance](../docs/SAFETY.md).

Code is independently developed for the diagnostic. Influences: [ios-sweet](https://github.com/dipa-studio/ios-sweet) and the Android boot image format in AOSP.
