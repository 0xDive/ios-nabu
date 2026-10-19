# Stage 6 — ABL-time FDT memory audit for Xiaomi Pad 5 (nabu)

**Experimental diagnostic only. This is not XNU, iOS, iPadOS, or a working kernel loader.**

The previous Stage 3 on a real nabu exhibited a ~10-second automatic PSCI reset after the shim attempted to call a tiny ramdisk payload. Stage 6 extends that *read-only diagnostic approach* to inspect the **FDT ABL hands to the temporary ARM64 image**, rather than assuming a DTB captured after Android has booted is identical.

The test parses only the FDT passed in x0 (which might still omit undocumented firmware allocations); it **never dereferences addresses obtained from memory/reg properties or writes to the proposed XNU physical memory region**.

## What gets checked

For the **provisional** `0x100000000..0x1F0000000` high-memory range (end exclusive):

- Entire region falls within a **single RAM bank** described by the bootloader-provided `/memory/reg` 2-address/2-size-cell tuples.
- It does not intersect fixed `/reserved-memory/*/reg` spans or entries in the FDT `/memreserve` header table.
- It does not intersect the actual running Stage 6 diagnostic image, the supplied FDT blob, or the bootloader-supplied `/chosen/linux,initrd-*` range.
- Unplaced `/reserved-memory` nodes that specify a `size` but no `reg` are counted as **unresolved** dynamic carveouts.
- Requires valid FDT structure, `nabu` model and PSCI >= 0.2, with SMC/HVC according to the tree.
- Checks that the MMU is disabled in the expected Stage 3-compatible entry state.

This is **not** a complete audit of every possible ABL, Qualcomm firmware or TrustZone allocation. Even the most favorable result does not prove RAM is safe to write, and it does not warrant loading XNU.

## Observable results

The diagnostic will request a **single automatic PSCI reboot** at one of these delays, counted **from executing our image** (not necessarily from USB transfer completion). The screen can stay black in all cases.

| Time to *automatic* restart | Meaning |
| --- | --- |
| Around **8 seconds** | Candidate inside advertised RAM; no known fixed or currently loaded overlaps, no *declared* unresolved dynamic nodes |
| Around **16 seconds** | Static non-overlap checks passed, **but dynamic reservations remain unknown** |
| Around **24 seconds** | Candidate not in an advertised bank, or a known fixed/currently loaded memory collision |
| Around **32 seconds** | Incomplete/unsupported FDT, missing chosen ramdisk, or incompatible MMU state |
| No autonomous restart | Early failure, absent compatible FDT/PSCI, hang or unsupported boot environment |

The distinction is approximate and not a persistent log; **no outcome proves free memory or XNU execution**. Do not repeat a hung test many times.

## Build on Ubuntu / WSL

```bash
sudo apt-get update
sudo apt-get install -y clang lld llvm binutils python3
bash stage6/build.sh
python3 -m unittest discover -s stage6/tests -v
```

The output is `stage6/out/nabu-stage6-audit.img` plus `stage6/out/SHA256SUMS.txt`. No private DTB, Android partition dump, IPSW or XNU executable is required or included.

For convenience, GitHub Actions uploads the exact same **diagnostic-only** image as an artifact (after cross-compile and tests succeed). Re-check its SHA-256 on your PC.

## Windows preflight and optional temporary boot

From the `stage6` directory, with Google platform-tools installed, the bootloader unlocked and the tablet in the *ordinary* FASTBOOT (not fastbootd):

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\preflight.ps1 -Image .\out\nabu-stage6-audit.img
```

If the dry-run preflight displays `PASS`, the explicit one-time test command is:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\preflight.ps1 -Image .\out\nabu-stage6-audit.img -Boot
```

The script requires typing `BOOT` before invoking **only** `fastboot boot`. It never flashes, formats, erases or resizes partitions. **Temporary boot is still a bare-metal hardware experiment**: it can hang, reset or require a long press of the power button. Have a backup and a recovery path. If the screen remains black without auto reboot, force-restart the tablet with the hardware power button after about 45 seconds.

**Report the elapsed time from “Booting OKAY” to automatic reset**, plus the complete fastboot output. Do **not** post original raw DTBs, serial numbers, private logs or partitions publicly.

## Required follow-up

An actual XNU test must wait for an independently reviewed hardware debugging channel and a memory strategy that accounts for *all* live boot allocations. This diagnostic only narrows down whether ABL provides a plausible RAM map. Its favorable signals **cannot be used as an allocation permission**.
