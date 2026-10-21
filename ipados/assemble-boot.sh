#!/usr/bin/env bash
# Assemble a temporary fastboot boot image from tested XNU payload parts.
# Requires a SAME-DEVICE Android boot.img v2 to supply the original nabu DTB.
# Does not write partitions or flash a device.
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "Usage: $0 SHIM_IMAGE PAYLOAD_BIN ORIGINAL_NABU_BOOT_IMG OUT_BOOT_IMG" >&2
  echo "Requires: python3, mkbootimg (Android platform tools)." >&2
  exit 2
fi

shim=$(realpath "$1")
payload=$(realpath "$2")
stock=$(realpath "$3")
output=$4
for file in "$shim" "$payload" "$stock"; do
  [[ -s "$file" ]] || { echo "Missing/empty input: $file" >&2; exit 2; }
done
[[ ! -e "$output" ]] || { echo "Refusing to overwrite: $output" >&2; exit 2; }
command -v mkbootimg >/dev/null || { echo 'Please install mkbootimg.' >&2; exit 2; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
python3 - "$stock" "$tmp/nabu.dtb" <<'PY'
import sys, struct
from pathlib import Path

blob = Path(sys.argv[1]).read_bytes()
if blob[:8] != b"ANDROID!":
    sys.exit("Source is not an Android boot.img")
if len(blob) < 1660:
    sys.exit("Truncated boot image")
kernel, _, ramdisk, _, second, _, _, page, version, _ = struct.unpack_from("<10I", blob, 8)
if version != 2 or page != 4096:
    sys.exit(f"Expected nabu boot header v2 / page size 4096, got v{version}/{page}. Stop; do not guess.")
rdtbo, _, hdrsize = struct.unpack_from("<IQI", blob, 1632)
dtbsize, _ = struct.unpack_from("<IQ", blob, 1648)
if not dtbsize or not (1660 <= hdrsize <= page):
    sys.exit(f"Invalid v2 DTB/header: dtb size={dtbsize}, header size={hdrsize}")
align = lambda x: (x + page - 1) // page * page
offset = page + sum(map(align, (kernel, ramdisk, second, rdtbo)))
dtb = blob[offset:offset + dtbsize]
if len(dtb) != dtbsize or dtb[:4] != b"\xd0\x0d\xfe\xed":
    sys.exit("Could not find a valid flattened DTB in the source boot image")
Path(sys.argv[2]).write_bytes(dtb)
print(f"Extracted nabu DTB: {len(dtb):,} bytes")
PY

if [[ $(head -c 7 "$payload") != NABUXNU ]]; then
  echo "Payload does not begin with NABUXNU magic; refusing to pack" >&2
  exit 2
fi

mkbootimg --header_version 2 \
  --kernel "$shim" --ramdisk "$payload" --dtb "$tmp/nabu.dtb" \
  --base 0 --kernel_offset 0x8000 --ramdisk_offset 0x1000000 \
  --tags_offset 0x100 --dtb_offset 0x1f00000 --pagesize 4096 \
  --os_version 17.0.0 --os_patch_level 2035-06 \
  --cmdline "console=null" -o "$output"

sha256sum "$output"
echo 'Generated temporary boot image. No partitions have been changed.'
echo 'WARNING: payload may access userdata. Do NOT fastboot boot before backing up partitions and preparing the correct HFS+ root.'
echo 'Only temporary boot is supported; NEVER run fastboot flash boot with this image.'
