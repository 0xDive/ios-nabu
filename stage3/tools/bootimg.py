#!/usr/bin/env python3
"""Dependency-free diagnostic Android boot v3 packer and offline inspector.

The packer is not a replacement for all features of AOSP mkbootimg.
See https://source.android.com/docs/core/architecture/bootloader/boot-image-header
"""
from __future__ import annotations
import argparse
import gzip
import pathlib
import struct
import sys

PAGE = 4096
HEAD_SIZE_V3 = 1580
CMDLINE_SIZE = 1536
MAX_PAYLOAD = 34 * 1024 * 1024


def align(n: int, page: int = PAGE) -> int:
    return (n + page - 1) // page * page


def newc_empty_ramdisk() -> bytes:
    name = b'TRAILER!!!\0'
    fields = [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, len(name), 0]
    record = b'070701' + b''.join(f'{f:08x}'.encode('ascii') for f in fields)
    record += name
    record += b'\0' * ((-len(record)) % 4)
    return gzip.compress(record, compresslevel=9, mtime=0)


def assert_arm64_image(raw: bytes) -> None:
    if len(raw) < 64 or raw[56:60] != b'ARM\x64':
        raise ValueError('Kernel is not an uncompressed ARM64 Linux Image (missing ARM\\x64).')
    image_size = struct.unpack_from('<Q', raw, 16)[0]
    if image_size != len(raw):
        raise ValueError(f'ARM64 Image header image_size={image_size}, actual={len(raw)}.')
    if image_size <= 64 or image_size > MAX_PAYLOAD:
        raise ValueError('Suspicious ARM64 Image size.')


def pack_v3(kernel: bytes, ramdisk: bytes, cmdline: str = '') -> bytes:
    assert_arm64_image(kernel)
    if not ramdisk:
        raise ValueError('Ramdisk must be non-empty')
    if len(kernel) + len(ramdisk) > MAX_PAYLOAD:
        raise ValueError('Kernel + ramdisk exceed conservative ~34 MiB nabu ABL limit')
    cmd = cmdline.encode('ascii')
    if len(cmd) >= CMDLINE_SIZE:
        raise ValueError('Command line too long')
    head = (b'ANDROID!' + struct.pack('<IIII', len(kernel), len(ramdisk), 0, HEAD_SIZE_V3)
            + struct.pack('<4I', 0, 0, 0, 0) + struct.pack('<I', 3)
            + cmd.ljust(CMDLINE_SIZE, b'\0'))
    assert len(head) == HEAD_SIZE_V3
    return (head.ljust(PAGE, b'\0')
            + kernel.ljust(align(len(kernel)), b'\0')
            + ramdisk.ljust(align(len(ramdisk)), b'\0'))


def read_header(data: bytes) -> dict:
    if data[:8] == b'ANDROID!':
        if len(data) < 44:
            raise ValueError('Boot image too small')
        kernel, ramdisk, osver = struct.unpack_from('<III', data, 8)
        candidate = struct.unpack_from('<I', data, 40)[0]
        version = candidate if candidate in (3, 4) else None
        result = {'kind': 'boot', 'header_version': version, 'kernel_size': kernel,
                  'ramdisk_size': ramdisk, 'os_version': osver, 'file_size': len(data)}
        if version in (3, 4):
            result['header_size'] = struct.unpack_from('<I', data, 20)[0]
            result['kernel_offset'] = PAGE
            result['ramdisk_offset'] = PAGE + align(kernel)
            if result['ramdisk_offset'] + ramdisk > len(data):
                raise ValueError('Truncated boot image')
        else:
            result['warning'] = 'Only v3/v4 parsing supported; boot header may be v0/v1/v2.'
        return result
    if data[:8] == b'VNDRBOOT':
        if len(data) < 2112:
            raise ValueError('Vendor boot image too small')
        version, pagesize, kernel_addr, ramdisk_addr, vrdsize = struct.unpack_from('<5I', data, 8)
        dtbsize = struct.unpack_from('<I', data, 2100)[0]
        return {'kind': 'vendor_boot', 'header_version': version,
                'page_size': pagesize, 'kernel_addr': hex(kernel_addr),
                'ramdisk_addr': hex(ramdisk_addr), 'vendor_ramdisk_size': vrdsize,
                'dtb_size': dtbsize, 'file_size': len(data)}
    raise ValueError('Unknown image magic (expected ANDROID! or VNDRBOOT)')


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='command', required=True)
    p = sub.add_parser('pack', help='Pack diagnostic ARM64 Linux Image into v3 boot.img')
    p.add_argument('kernel', type=pathlib.Path)
    p.add_argument('output', type=pathlib.Path)
    p.add_argument('--ramdisk', type=pathlib.Path, help='Optional gzip cpio ramdisk')
    p.add_argument('--cmdline', default='', help='Must be small, no secrets')
    q = sub.add_parser('inspect', help='Offline information: boot.img / vendor_boot.img')
    q.add_argument('images', nargs='+', type=pathlib.Path)
    ex = sub.add_parser('extract-dtb', help='Extract the DTB segment from a local vendor_boot v3/v4 image')
    ex.add_argument('vendor_boot', type=pathlib.Path)
    ex.add_argument('output', type=pathlib.Path)
    args = ap.parse_args(argv)
    try:
        if args.command == 'pack':
            kernel = args.kernel.read_bytes()
            ramdisk = args.ramdisk.read_bytes() if args.ramdisk else newc_empty_ramdisk()
            data = pack_v3(kernel, ramdisk, args.cmdline)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(data)
            print(f'Created {args.output} ({len(data)} bytes)')
        elif args.command == 'extract-dtb':
            data = args.vendor_boot.read_bytes()
            h = read_header(data)
            if h['kind'] != 'vendor_boot' or h['header_version'] not in (3, 4):
                raise ValueError('Needs vendor_boot v3/v4')
            page = h['page_size']
            if page < 2048 or page > 65536 or page & (page - 1):
                raise ValueError('Invalid vendor boot page size')
            header_bytes = 2112 if h['header_version'] == 3 else 2128
            offset = align(header_bytes, page) + align(h['vendor_ramdisk_size'], page)
            end = offset + h['dtb_size']
            if h['dtb_size'] == 0 or end > len(data):
                raise ValueError('DTB segment size/offset is invalid')
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(data[offset:end])
            print(f'Extracted DTB segment: {args.output} ({h["dtb_size"]} bytes)')
            print('Note: Qualcomm DTB segment may contain several concatenated device trees.')
        else:
            for path in args.images:
                print(f'{path}:')
                info = read_header(path.read_bytes())
                for key, value in info.items():
                    print(f'  {key}: {value}')
    except (ValueError, OSError, UnicodeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
