# Offline XNU memory-layout audit

[tools/validate_layout.py](../tools/validate_layout.py) checks whether a **proposed** 16 KiB-aligned physical load address for ARM64 XNU Mach-O segments, an ADT blob, and boot_args fits inside a contiguous RAM bank described by a *Linux Device Tree*.

This is a conservative host-side analysis. It **never** writes memory, contacts the device, flashes firmware, or proves any address is actually free at early boot.

## Inputs

Generate inputs from your own locally available files, **outside the public GitHub repository**:

1. Read a non-proprietary, compatible ARM64 Mach-O using `stage4/tools/inspect_kernel.py` to produce `macho-report.json`.
2. Read your own nabu DTB using `stage4/tools/dtb_inspect.py` to produce the memory inventory JSON (no serials/bootargs).
3. Know the proposed physical load address, the ADT byte length, and optionally the actual initrd physical bounds.

Example:

```bash
python3 stage4/tools/inspect_kernel.py /private/kernel.development --out /private/macho-report.json
python3 stage4/tools/dtb_inspect.py /private/nabu.dtb -o /private/dtb-memory.json
python3 tools/validate_layout.py --macho-report /private/macho-report.json \
  --memory-report /private/dtb-memory.json --base 0x100000000 --adt-size 0x4000 \
  --out /private/layout-report.json
```

The example address is **illustrative only**, not a recommendation for real hardware loading. The output always reports `safe_to_boot: false` and `runtime_free_verified: false`.

The checks reject malformed or overlapping kernel segments, invalid entry VA, unaligned base, integer overflow, placement outside RAM, FDT reserved-memory collisions and optional initrd collisions. They cannot detect allocations from ABL or running firmware not represented in the provided DTB.

Before any XNU boot experiment, separately verify ABL's live allocations, loaded FDT, ramdisk, cache/MMU behavior, actual kernel ABI and an independent debugging output path. No command in this repository currently authorizes XNU execution or partition flashing.

Run the synthetic unit tests: `python3 -m unittest discover -s tools/tests -v`.
