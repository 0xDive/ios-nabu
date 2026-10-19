# Experimental XNU build for Xiaomi Pad 5 (nabu)

**Status: early host-side compile experiment only. Nothing here is a bootable iOS or iPadOS image.**

The project's first goal is to see whether XNU 8796 (iOS 16 generation) can be cross-compiled with a dedicated `NABU` machine identifier on a macOS GitHub Actions runner.

## Provenance and reproducibility

- Base XNU build environment: [blacktop/darwin-xnu-build](https://github.com/blacktop/darwin-xnu-build), revision `663906528d1cd5ea8fde7de6f16de73db9511549`.
- Experimental platform and dependency patches: [dipa-studio/ios-sweet](https://github.com/dipa-studio/ios-sweet), revision `fdad0de8dc0e75c5ea84762adc03f7232dc91f19`.
- Compiler workflow: [xnu-nabu.yml](../.github/workflows/xnu-nabu.yml).
- Preparation and checks: [stage_upstream.py](tools/stage_upstream.py), [tests](tests/).

The experiment fetches upstream source at exact revisions into GitHub's ephemeral runner. It does **not** check in or redistribute ios-sweet's patch collection, whose repository currently does not advertise a standard license. This is research; check upstream rights before reusing or shipping a derivative.

## What the transformation does

For this first compiler smoke test, the preparation script translates platform names `SWEET/Sweet/sweet` into `NABU/Nabu/nabu` within upstream patch text and filenames, then corrects the user-visible chipset/CPU name to Snapdragon 860/Kryo 485. This allows the compiler to **attempt** a `NABU` configuration without assuming that any hardware backend works.

It does **not** translate:
- framebuffer ownership, format, pitch or physical mapping;
- GPIO/pinctrl, Novatek SPI touch, clocks or power sequences;
- interrupt routing details for every SM8150 device;
- UFS DMA/IOMMU descriptors, Wi-Fi/BT, GPU or display controller;
- Apple Device Tree completeness, boot_args physical addresses, Mach-O segment placement or device trust;
- iOS userland services, SpringBoard, boot policy or code-signing infrastructure.

**Any kernel produced by this compile-only workflow must NOT be sent to the tablet.**

## Running CI

The workflow is intentionally separate from the Stage 3 diagnostics and runs from its own Pull Request or by manual GitHub Actions dispatch. It uses a macOS 14 runner, XNU development configuration and `MACHINE_CONFIG=NABU`, with `MAKEFLAGS=-k` to collect compiler errors.

The workflow always uploads **only provenance, an abbreviated build log, and hashes of any kernels found**. It never uploads an XNU executable, firmware image, Apple system image, or personal device dump. Build failures are genuine failures, not reported as successes.

Local offline tests can be run without macOS:

```bash
python3 -m unittest discover -s xnu/tests -v
```

For now, the tests use synthetic data. Private `nabu.dtb`, userdata, serial numbers and boot logs should remain outside the Git repository.

## Next genuine porting work

The important next step is to replace this *mechanical compile smoke test* with nabu-specific source patches and reviewed low-level drivers, and to separately establish trusted early-boot logging and proof of free RAM. The initial ADT prototype has a `qcom,kryo485` CPU compatible string to match the experimental CPU service, but that does not make the entire ADT fit for XNU.

The actual boot milestone requires a separately reviewed loader and **temporary** boot sequence (without flashing partitions) only after a proven memory map, verified Mach-O and debugging channel are available.
