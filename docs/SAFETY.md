# Safety and data handling

This repository is research only. No functioning iOS or iPadOS port has been demonstrated on Xiaomi Pad 5.

- Never run `fastboot flash`, `erase`, `format`, or partition-resizing operations based on this research.
- Temporary `fastboot boot` *does not write a partition*, but firmware errors and bare-metal code can still hang or reboot hardware. Back up your data and keep a recovery route.
- Do not read or write arbitrary physical memory addresses. A Linux FDT's reserved-memory region does **not** grant safe access to its physical address at ABL handoff.
- Only run test builds after inspecting the exact target device (`product=nabu`, bootloader unlocked, not fastbootd) and matching Android boot format.
- Kernel entry and a black screen are **not equivalent**. Need positive debugging evidence.
- Never upload a personal device DTB, partitions, UFS dumps, proprietary Apple OS binaries, private keys, serial numbers, or logs containing secrets to a public repository.
- Upstream projects may have different licenses. Do not copy code without checking and preserving the license notices.
- CI should only validate source and generate host-side test artifacts. No CI workflow should claim or publish a working bootable image before device verification.
