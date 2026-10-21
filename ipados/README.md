# iPadOS / XNU build experiment for Xiaomi Pad 5 (nabu)

This branch is isolated from the existing UEFI port.

- Source: https://github.com/mytiantian001/iPadOS-nabu at commit 057b7f53fc7fef46626c81bbe3e1dbbc328c8f34
- XNU harness: https://github.com/blacktop/darwin-xnu-build at commit 663906528d1cd5ea8fde7de6f16de73db9511549
- CI: .github/workflows/ipados-nabu.yml
- Local compatibility patches: ipados/patches/
- Same-device boot-image packer: ipados/assemble-boot.sh

## Verified CI milestone (2026-10-21)

GitHub Actions run https://github.com/0xDive/ios-nabu/actions/runs/39676913328
completed successfully on commit 8932274ed615f1d5d9348b78e81aa567325aabd0.

- Shim / ADT: ipados-nabu-shim-parts (artifact 12382142073), success.
- XNU: ipados-nabu-xnu-kernel (artifact 12382014390), DEVELOPMENT ARM64 NABU, success, kernel.development.nabu about 16 MiB.
- Packed payload: ipados-nabu-payload-parts (artifact 12382782910), success, payload.bin 16,610,944 bytes.
- Bundle payload contains NO HFS+ iPadOS root; the original iPad7,3 /product ADT was unavailable and is omitted.
- Original hardware DTB from a nabu boot.img v2 is still required before a fastboot test image can be assembled.
- The real tablet has NOT been booted or flashed in this milestone.

## Build outputs

GitHub Actions compiles the arm64 bare-metal shim, iPad7,3 ADT and patched XNU.
On success, the bundle job produces payload.bin and other parts. The CI does
NOT ship a complete iPadOS root, original Apple device-tree /product data,
a matching physical nabu DTB or any firmware partition dumps.

Compile success does **not** mean usable iPadOS or even successful physical boot.

## Corrections against upstream snapshot

- 0084: Implement missing IOSurface fallback/probe functions which
  caused undeclared identifier errors in NabuFramebuffer.cpp in CI run
  https://github.com/0xDive/ios-nabu/actions/runs/39673719559.
- 0085: Fix NabuCPU IONameMatch to qcom,kryo485 (the --ipad ADT contains this
  compatible, not the legacy qcom,kryo470); correct early screen framebuffer
  layout to 1600x2560, stride 6400.
- Upstream 0082 is rejected by git apply due to an existing
  config/MASTER.arm64.nabu and conflicting makedefs hunks. Do NOT silently
  assume that this entire upstream patch applied. Review all hardware-relevant
  differences before testing real hardware.

## Packaging when the required inputs are available

1. Extract Image from the ipados-nabu-shim-parts CI artifact and payload.bin
   from the ipados-nabu-payload-parts CI artifact.
2. Obtain the **same device's** boot.img v2 from a trusted local backup. Do not
   substitute an unrelated DTB or a random device-tree blob.
3. On Linux with mkbootimg installed, run:

```bash
bash ipados/assemble-boot.sh Image payload.bin original-nabu-boot.img shim-boot.img
```

The packer validates the boot header and FDT. It NEVER flashes partitions.

**Stop before booting if Android userdata is still present**. The payload
expects an HFS+ root and its UFS write settings are dangerous to Android
userdata. Preserve partition backups (especially userdata, modem, persist,
boot/recovery and GPT) before any destructive operations. Writing the iPadOS
root into userdata is destructive and should be a separately approved action.
Never use fastboot flash boot; testing is via temporary fastboot boot only
after the root, identity and board safety have been independently validated.

## iPadOS OS image is not in source control

The upstream tools/mkiosroot.sh requires OS.dmg, SystemOS.dmg and AppOS.dmg
from the user's legitimately obtained iPadOS 16.6.1 (20G81) iPad7,3 IPSW.
These Apple artifacts are not distributed by this repository. The root image
building step is independent of XNU + shim CI and needs Linux with apfs-fuse,
hfsprogs, rsync and sufficient free disk space.
