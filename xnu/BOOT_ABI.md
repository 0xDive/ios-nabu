# Experimental boot-args contract for XNU on NABU

This project now has an **offline-only** implementation of XNU ARM64 `boot_args` Revision 2 / Version 2 in [tools/boot_args.py](tools/boot_args.py). This is for studying the handoff from a Qualcomm ABL-compatible loader into an XNU Mach-O executable, **not** for loading an OS yet.

The ABI and field offsets are based on the publicly available XNU header `pexpert/pexpert/arm64/boot.h` and the implementation investigated by [ios-sweet](https://github.com/dipa-studio/ios-sweet). The 736-byte struct contains:

| Offset | Data | Purpose |
|---:|---|---|
| 0 | `Revision=2, Version=2` | XNU ARM64 ABI selector |
| 8–39 | `virtBase, physBase, memSize, topOfKernelData` | Virtual-to-physical mapping |
| 40–87 | `Video` (6 × u64, **all zero**) | Disabled: display/framebuffer format unverified |
| 88 | `machineType=0` | Provisional, verify for target build |
| 96 | `deviceTreeP` | ADT **virtual** address after MMU enable |
| 104 | `deviceTreeLength` | Exact binary ADT size |
| 108–715 | `CommandLine` | Initial single-CPU diagnostic flags |
| 720–735 | `bootFlags, memSizeActual` | Flags and actual RAM size |

The serializer requires:
- a static layout report from [tools/validate_layout.py](../tools/validate_layout.py) with no known collision; `safe_to_boot` remains **false**;
- a well-formed ADT which contains `xiaomi,nabu`, `qcom,sm8150`, `chosen/dram-base` and `chosen/dram-size`;
- matching base/size in both ADT and `boot_args`;
- aligned addresses, a dedicated 16 KiB boot-args page and an ADT that does not overlap it;
- no framebuffer access or unconfirmed MMIO access.

Example **offline-only** invocation, provided you have generated your own valid ADT and a non-executable static layout JSON:

```sh
python3 xnu/tools/boot_args.py --layout /private/layout-report.json \
  --adt /private/nabu-draft.adt --ram-size 0xf0000000 \
  --cmdline 'cpus=1 -v' --out xnu/out/boot-args-v2.bin
```

This produces data only. It does not load or relocate Mach-O segments, enable the MMU, set exception vectors, initialize the SoC, create ramdisk mounts or jump to XNU. **Do not use the generated binary in a hardware boot image.**

The nabu Device Tree was captured from *running Android*; this does not prove the same RAM carveouts or addresses exist during Qualcomm ABL's experimental entry. The very next runtime milestone must establish a trustworthy early-boot diagnostic channel and validate actual available memory before attempting XNU entry.
