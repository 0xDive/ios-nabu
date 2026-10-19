#!/usr/bin/env bash
# Reproducible host-side diagnostic build. Creates a boot v3 image, never flashes it.
set -euo pipefail
cd "$(dirname "$0")"
for cmd in clang ld.lld llvm-objcopy nm python3 readelf sha256sum; do
    command -v "$cmd" >/dev/null || { echo "Missing $cmd" >&2; exit 1; }
done
mkdir -p out
common=(--target=aarch64-none-elf -ffreestanding -nostdlib -fno-builtin
    -fno-pic -fno-pie -fno-stack-protector -fno-unwind-tables
    -fno-asynchronous-unwind-tables -fno-common -mstrict-align
    -mgeneral-regs-only -Wall -Wextra -Werror -O2)
clang "${common[@]}" -c src/entry.S -o out/entry.o
clang "${common[@]}" -c src/handoff.c -o out/handoff.o
clang "${common[@]}" -c src/fdt_probe.c -o out/fdt_probe.o
ld.lld --no-undefined -T src/link.ld --build-id=none -o out/stage3.elf \
  out/entry.o out/handoff.o out/fdt_probe.o
if readelf -r out/stage3.elf | grep -q R_AARCH64_; then
    echo 'Unexpected ARM64 relocations in linked image' >&2
    exit 1
fi
llvm-objcopy -O binary out/stage3.elf out/Image-stage3
end_addr=$(nm out/stage3.elf | awk '$3 == "image_end" { print $1 }')
test -n "$end_addr"
python3 - out/Image-stage3 "$end_addr" <<'PY'
import pathlib,sys
p=pathlib.Path(sys.argv[1])
size=int(sys.argv[2],16)
assert p.stat().st_size <= size <= 512*1024
with p.open('ab') as file:
    file.write(bytes(size-p.stat().st_size))
PY
clang "${common[@]}" -c src/payload_entry.S -o out/payload_entry.o
ld.lld --no-undefined --build-id=none -Ttext=0 -e payload_entry \
    -o out/payload_entry.elf out/payload_entry.o
if readelf -r out/payload_entry.elf | grep -q R_AARCH64_; then
    echo 'Unexpected payload relocation' >&2
    exit 1
fi
llvm-objcopy -O binary -j .text out/payload_entry.elf out/payload_code.bin
python3 tools/payload.py out/payload_code.bin out/ramdisk-payload.bin
python3 tools/bootimg.py pack out/Image-stage3 out/nabu-stage3-handoff.img \
    --ramdisk out/ramdisk-payload.bin
python3 tools/bootimg.py inspect out/nabu-stage3-handoff.img
sha256sum out/nabu-stage3-handoff.img > out/SHA256SUMS.txt
echo 'Stage3 built (offline only; NOT an XNU/iOS image).'
