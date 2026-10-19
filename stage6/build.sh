#!/usr/bin/env bash
# Read-only nabu Stage 6 FDT RAM-layout diagnostic.
# Produces Android boot v3 image for optional *temporary* fastboot boot.
# Never flashes partitions and never writes to an arbitrary memory address.
set -euo pipefail
cd "$(dirname "$0")"
for cmd in clang ld.lld llvm-objcopy nm readelf python3 sha256sum; do
    command -v "$cmd" >/dev/null || { echo "Missing executable: $cmd" >&2; exit 1; }
done
mkdir -p out
common=(--target=aarch64-none-elf -ffreestanding -nostdlib -fno-builtin
    -fno-pic -fno-pie -fno-stack-protector -fno-unwind-tables
    -fno-asynchronous-unwind-tables -fno-common -mstrict-align
    -mgeneral-regs-only -Wall -Wextra -Werror -O2
    -I ../stage3/src -I src)
clang "${common[@]}" -c ../stage3/src/entry.S -o out/entry.o
clang "${common[@]}" -c ../stage3/src/fdt_probe.c -o out/fdt_probe.o
clang "${common[@]}" -c src/memory_probe.c -o out/memory_probe.o
clang "${common[@]}" -c src/runtime.c -o out/runtime.o
clang "${common[@]}" -c src/diag.c -o out/diag.o
ld.lld --no-undefined --build-id=none -T ../stage3/src/link.ld \
    -o out/nabu-audit.elf \
    out/entry.o out/fdt_probe.o out/memory_probe.o out/runtime.o out/diag.o
if readelf -r out/nabu-audit.elf | grep -q R_AARCH64_; then
    echo 'ERROR: unresolved ARM64 relocations found' >&2
    exit 1
fi
llvm-objcopy -O binary out/nabu-audit.elf out/Image-stage6
size_hex=$(nm out/nabu-audit.elf | awk '$3 == "image_end" {print $1}')
test -n "$size_hex"
python3 - out/Image-stage6 "$size_hex" <<'PY'
import pathlib, sys
path=pathlib.Path(sys.argv[1])
image_end=int(sys.argv[2],16)
raw=path.read_bytes()
assert 64 < len(raw) <= image_end <= 512*1024, "Invalid image size"
assert raw[56:60] == b"ARM\x64", "Expected Linux-compatible ARM64 Image header"
path.write_bytes(raw + bytes(image_end-len(raw)))
PY
python3 ../stage3/tools/bootimg.py pack out/Image-stage6 out/nabu-stage6-audit.img
python3 ../stage3/tools/bootimg.py inspect out/nabu-stage6-audit.img
sha256sum out/nabu-stage6-audit.img > out/SHA256SUMS.txt
echo 'Stage 6 compiled. No device accessed. NOT an XNU/iOS image.'
