#!/usr/bin/env bash
# Build a read-only boot-time FDT survey. NOT XNU; NEVER flash partitions.
set -euo pipefail
cd "$(dirname "$0")"
for tool in clang ld.lld llvm-objcopy nm readelf python3 sha256sum; do
  command -v "$tool" >/dev/null || { echo "Missing $tool" >&2; exit 1; }
done
mkdir -p out
common=(--target=aarch64-none-elf -ffreestanding -nostdlib -fno-builtin
  -fno-pic -fno-pie -fno-stack-protector -fno-unwind-tables
  -fno-asynchronous-unwind-tables -fno-common -mstrict-align
  -mgeneral-regs-only -Wall -Wextra -Werror -O2)
clang "${common[@]}" -I../stage3/src -c ../stage3/src/entry.S -o out/entry.o
clang "${common[@]}" -I../stage3/src -c ../stage3/src/fdt_probe.c -o out/fdt_probe.o
clang "${common[@]}" -I../stage3/src -c src/survey.c -o out/survey.o
clang "${common[@]}" -I../stage3/src -c src/diag.c -o out/diag.o
ld.lld --no-undefined --build-id=none -T ../stage3/src/link.ld -o out/stage6.elf \
  out/entry.o out/fdt_probe.o out/survey.o out/diag.o
if readelf -r out/stage6.elf | grep -q 'R_AARCH64_'; then
  echo 'Unexpected unresolved ARM64 relocation' >&2; exit 1
fi
llvm-objcopy -O binary out/stage6.elf out/Image-stage6
end=$(nm out/stage6.elf | awk '$3 == "image_end" {print $1}')
test -n "$end"
python3 - out/Image-stage6 "$end" <<'PY'
import pathlib,sys
p=pathlib.Path(sys.argv[1]); size=int(sys.argv[2],16)
assert 64 < p.stat().st_size <= size <= 512 * 1024
with p.open("ab") as f:
    f.write(bytes(size-p.stat().st_size))
PY
python3 ../stage3/tools/bootimg.py pack out/Image-stage6 \
  out/nabu-stage6-fdt-survey.img
python3 ../stage3/tools/bootimg.py inspect out/nabu-stage6-fdt-survey.img
sha256sum out/nabu-stage6-fdt-survey.img > out/SHA256SUMS.txt
echo 'Stage 6: built diagnostic boot v3 (NO XNU / no partition operations)'
