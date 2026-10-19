#!/usr/bin/env python3
"""Stage 3 raw initrd test payload. NOT an iOS/XNU loader."""
from __future__ import annotations
import argparse
import pathlib
import struct
import zlib

MAGIC = b'NABU3PAY'
TOKEN = 0x4e414255334f4b21
OFFSET = 64
HEADER = struct.Struct('<8sIIIIIQ')


def pack(code: bytes) -> bytes:
    if not 4 <= len(code) <= 256 or len(code) % 4:
        raise ValueError('Payload must be 4..256 bytes aligned to 4')
    hdr = HEADER.pack(MAGIC, 1, OFFSET, len(code), zlib.crc32(code), 0, TOKEN)
    return hdr.ljust(OFFSET, b'\0') + code


def inspect(data: bytes) -> dict:
    if len(data) < OFFSET:
        raise ValueError('Payload truncated')
    magic, version, offset, length, crc, flags, token = HEADER.unpack_from(data)
    if (magic != MAGIC or version != 1 or offset != OFFSET or flags != 0 or
        token != TOKEN or length < 4 or length > 256 or length % 4 or
        offset + length > len(data)):
        raise ValueError('Invalid payload header')
    if zlib.crc32(data[offset:offset+length]) != crc:
        raise ValueError('Payload CRC mismatch')
    return {'version': version, 'length': length, 'crc32': hex(crc),
            'token': hex(token)}


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('code', type=pathlib.Path)
    cli.add_argument('output', type=pathlib.Path)
    args = cli.parse_args()
    data = pack(args.code.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    print(args.output, inspect(data))

if __name__ == '__main__':
    main()
