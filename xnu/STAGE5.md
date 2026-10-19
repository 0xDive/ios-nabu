# Stage 5: offline Mach-O handoff planning for nabu

**This is not a bootloader and does not boot iOS.** Stage 5 connects the compiler's actual `kernel.development.nabu` metadata to our static memory planner and the XNU ARM64 `boot_args` data structure.

The host-side [plan_handoff.py](tools/plan_handoff.py) creates a JSON description of **hypothetical** segment copies and BSS zero-initializations that a *future, separately audited* loader might need. It never reads or writes tablet memory, relocates/executes a Mach-O, or generates a fastboot image.

## Inputs

1. `macho-report.json` from the successful [XNU macOS Actions run](https://github.com/0xDive/ios-nabu/actions/runs/39295105141), downloaded from its `nabu-xnu-compile-diagnostics` artifact. This contains metadata **only**, not the kernel executable.
2. A **privately stored** Xiaomi Pad 5 Linux DTB, collected from your own nabu.
3. An experimental `nabu-draft.adt` generated locally from that DTB.
4. A static-only memory-placement report and its corresponding 736-byte ARM64 `boot_args`.

## Offline pipeline

Run from the repository root with Python 3. All `private/` paths below are **local** and should remain ignored or outside the repository.

```bash
python3 stage4/tools/dtb_inspect.py private/nabu.dtb -o private/nabu-memory.json

python3 stage4/tools/mkadt_nabu.py --dtb private/nabu.dtb \
  --out private/nabu-draft.adt --report private/nabu-adt-report.json

# Use the exact ADT size in bytes, not an arbitrary 16 KiB placeholder:
python3 -c "from pathlib import Path; print(hex(Path('private/nabu-draft.adt').stat().st_size))"

python3 tools/validate_layout.py \
  --macho-report private/macho-report.json \
  --memory-report private/nabu-memory.json \
  --base 0x100000000 --adt-size <EXACT_ADT_SIZE> \
  --out private/xnu-layout.json

python3 xnu/tools/boot_args.py \
  --layout private/xnu-layout.json --adt private/nabu-draft.adt \
  --ram-size 0xf0000000 --cmdline 'cpus=1 -v' \
  --out private/boot-args-v2.bin

python3 xnu/tools/plan_handoff.py \
  --macho-report private/macho-report.json \
  --layout private/xnu-layout.json --adt private/nabu-draft.adt \
  --boot-args private/boot-args-v2.bin \
  --out private/nabu-stage5-plan.json
```

Replace `<EXACT_ADT_SIZE>` with the hex byte length printed above; this example is **not** a script to run unchanged. `0x100000000` is a provisional high-DRAM address only. Running Android's FDT is not a proof that ABL will make it available.

## Validations

Stage 5 rejects inconsistent mapping assumptions, unsupported Mach-O fixups, invalid ABI versions, wrong device identity, unverified or mismatched boot_args/ADT pointer and size, overlapping mapping entries, truncated segment file ranges, unexpected file-only segments, and an entry outside the executable `__TEXT_EXEC` segment. The generated plan includes copy/zero operations **as text only**, and maintains `safe_to_boot: false`.

The current XNU `__TEXT` virtual address is `0xFFFFFE0007004000`, but its 32 MiB-aligned `virtBase` is `0xFFFFFE0006000000`. With the **unverified** example `physBase = 0x100000000`, `__TEXT` would map to `0x101004000`, and the entry to `0x10148B488`. These are calculated values, **not** a safe memory map for the real tablet.

## Remaining before trying XNU on hardware

The XNU build still derives many hardware drivers and startup assumptions from Qualcomm SM7150 (`sweet`). SM8150-specific memory allocation at ABL handoff, ADT completeness, GIC/CPU initialization, cache/MMU transition semantics, safe logging, and peripheral drivers remain unverified. We must establish those before any new `fastboot boot` test. **Do not flash partitions or build a runnable image from this plan.**

Synthetic tests: `python3 -m unittest discover -s xnu/tests -v`.
