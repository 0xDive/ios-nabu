#!/usr/bin/env python3
"""Minimal strict Apple Device Tree serializer and reader.

Wire format matches dipa-studio/ios-sweet/tools/adt.py:
node: LE32 prop_count, LE32 child_count, properties, children.
property: ASCII name[32], LE32 size, padded binary value.
No Apple copyrighted data included.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import struct

MAX_BYTES = 8 * 1024 * 1024


@dataclass
class Node:
    name: str
    props: dict[str, bytes] = field(default_factory=dict)
    children: list["Node"] = field(default_factory=list)

    def child(self, name: str):
        return next((n for n in self.children if n.name == name), None)


def u32(*v: int) -> bytes:
    return struct.pack('<' + 'I' * len(v), *v)


def u64(*v: int) -> bytes:
    return struct.pack('<' + 'Q' * len(v), *v)


def cstr(s: str) -> bytes:
    return s.encode('utf-8') + b'\0'


def make_node(name: str, props=None, children=None) -> Node:
    p = {'name': cstr(name)}
    p.update(dict(props or {}))
    return Node(name, p, list(children or []))


def pack(root: Node) -> bytes:
    out = bytearray()
    def emit(n: Node, depth: int):
        if depth > 64 or len(n.props) > 512 or len(n.children) > 512:
            raise ValueError('ADT tree too deep or wide')
        out.extend(struct.pack('<II', len(n.props), len(n.children)))
        for key, raw in n.props.items():
            if not key.isascii() or not key or len(key.encode()) > 31 or not isinstance(raw, bytes):
                raise ValueError(f'Unsupported ADT property {key!r}')
            if len(raw) > 0x7FFFFFFF:
                raise ValueError('Property too large')
            out.extend(key.encode('ascii').ljust(32, b'\0'))
            out.extend(u32(len(raw)))
            out.extend(raw)
            out.extend(bytes(-len(raw) & 3))
        for child in n.children:
            emit(child, depth+1)
    emit(root, 0)
    if len(out) > MAX_BYTES:
        raise ValueError('ADT too large')
    return bytes(out)


def unpack(data: bytes) -> Node:
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Invalid ADT size')
    def decode(off, depth):
        if depth > 64 or off + 8 > len(data):
            raise ValueError('Invalid ADT node boundary')
        nprops, nchildren = struct.unpack_from('<II', data, off)
        if nprops > 512 or nchildren > 512:
            raise ValueError('Invalid ADT counts')
        off += 8
        props = {}
        for _ in range(nprops):
            if off + 36 > len(data):
                raise ValueError('Truncated ADT property')
            name = data[off:off+32].split(b'\0',1)[0].decode('ascii')
            size, = struct.unpack_from('<I', data, off+32)
            if size & 0x80000000:
                raise ValueError('Unresolved placeholder property')
            off += 36
            if off + size > len(data):
                raise ValueError('Truncated ADT value')
            props[name] = data[off:off+size]
            off += (size+3) & ~3
            if off > len(data):
                raise ValueError('Out-of-bounds ADT padding')
        children = []
        for _ in range(nchildren):
            child, off = decode(off, depth+1)
            children.append(child)
        name = props.get('name',b'?').split(b'\0')[0].decode('utf-8','replace')
        return Node(name, props, children),off
    n,end = decode(0,0)
    if end != len(data):
        raise ValueError('Trailing ADT bytes')
    return n
