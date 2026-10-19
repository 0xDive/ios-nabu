#!/usr/bin/env python3
"""Offline FDT parser. Do not commit personal input DTBs or raw property dumps."""
from __future__ import annotations
import argparse
import json
import pathlib
import struct
from dataclasses import dataclass, field

FDT_MAGIC = 0xD00DFEED
MAX_FDT = 16 * 1024 * 1024
MAX_NODES = 30000
MAX_DEPTH = 96


@dataclass
class Node:
    name: str
    children: list["Node"] = field(default_factory=list)
    props: dict[str, bytes] = field(default_factory=dict)

    def get(self, path: str) -> "Node | None":
        node = self
        for component in path.strip("/").split("/"):
            if component:
                node = next((child for child in node.children if child.name == component), None)
                if node is None:
                    return None
        return node


def strings(value: bytes | None) -> list[str]:
    if not value:
        return []
    return [part.decode("utf-8", "replace") for part in value.split(b"\0") if part]


def one_u32(value: bytes | None, default: int) -> int:
    if value is None:
        return default
    if len(value) != 4:
        raise ValueError("Invalid address/size cell property length")
    count = int.from_bytes(value, "big")
    if count not in (1, 2):
        raise ValueError("Unsupported cell count")
    return count


def parse_ranges(blob: bytes | None, na: int, ns: int) -> list[dict]:
    if not blob:
        return []
    count = 4 * (na + ns)
    if len(blob) % count:
        raise ValueError("Invalid reg property length")
    result = []
    for offset in range(0, len(blob), count):
        addr = int.from_bytes(blob[offset:offset+4*na], "big")
        size = int.from_bytes(blob[offset+4*na:offset+count], "big")
        result.append({"address": f"0x{addr:016X}",
                       "end_exclusive": f"0x{addr+size:016X}",
                       "size_mib": round(size / 1048576, 3),
                       "size_bytes": size})
    return result


def parse_dtb(raw: bytes) -> Node:
    if len(raw) < 40 or len(raw) > MAX_FDT:
        raise ValueError("DTB too small/large")
    (magic, total, off_struct, off_strings, off_reserve,
     version, last_comp, _, szstr, szstruct) = struct.unpack_from(">10I", raw)
    if magic != FDT_MAGIC or version < 17 or last_comp > 17 or not 40 <= total <= len(raw):
        raise ValueError("Invalid DTB header")
    if off_struct < 40 or off_strings < 40 or off_struct+szstruct > total or off_strings+szstr > total:
        raise ValueError("FDT segment out of bounds")
    if off_reserve < 40 or off_reserve >= total:
        raise ValueError("Invalid FDT reservation table")
    st = raw[off_struct:off_struct+szstruct]
    names = raw[off_strings:off_strings+szstr]
    at = 0
    stack = []
    root = None
    nodes = 0
    ended = False
    while at + 4 <= len(st):
        token = struct.unpack_from(">I", st, at)[0]
        at += 4
        if token == 1:
            end = st.find(b"\0", at)
            if end < 0:
                raise ValueError("Unterminated node")
            node = Node(st[at:end].decode("utf-8", "replace"))
            at = (end + 4) & ~3
            if stack:
                stack[-1].children.append(node)
            elif root is None:
                root = node
            else:
                raise ValueError("Multiple roots")
            stack.append(node)
            nodes += 1
            if nodes > MAX_NODES or len(stack) > MAX_DEPTH:
                raise ValueError("FDT depth/size limit")
        elif token == 2:
            if not stack:
                raise ValueError("Excess END_NODE")
            stack.pop()
        elif token == 3:
            if not stack or at + 8 > len(st):
                raise ValueError("Bad FDT property header")
            size, name_offset = struct.unpack_from(">II", st, at)
            at += 8
            if size > len(st)-at or name_offset >= len(names):
                raise ValueError("Invalid FDT property bounds")
            end = names.find(b"\0", name_offset)
            if end < 0:
                raise ValueError("Unterminated FDT property name")
            key = names[name_offset:end].decode("utf-8", "replace")
            stack[-1].props[key] = st[at:at+size]
            at = (at + size + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            if stack:
                raise ValueError("Open FDT node on END")
            ended = True
            break
        else:
            raise ValueError(f"Unknown FDT token {token}")
    if not ended or root is None:
        raise ValueError("FDT lacks root/END")
    return root


def summarize(root: Node) -> dict:
    model = strings(root.props.get("model"))
    compatible = strings(root.props.get("compatible"))
    psci = root.get("/psci")
    reserved = root.get("/reserved-memory")
    address_cells = one_u32(root.props.get("#address-cells"), 2)
    size_cells = one_u32(root.props.get("#size-cells"), 2)
    memory = {}
    for n in root.children:
        if n.name == "memory" or n.name.startswith("memory@"):
            memory[n.name] = parse_ranges(n.props.get("reg"), address_cells, size_cells)
    reserved_regions = {}
    if reserved:
        na = one_u32(reserved.props.get("#address-cells"), address_cells)
        ns = one_u32(reserved.props.get("#size-cells"), size_cells)
        for child in reserved.children:
            reserved_regions[child.name] = parse_ranges(child.props.get("reg"), na, ns)
    return {"model": model, "compatible": compatible,
            "psci": {"compatible": strings(psci.props.get("compatible")) if psci else [],
                     "method": strings(psci.props.get("method")) if psci else []},
            "memory_banks": memory, "reserved_memory": reserved_regions,
            "warning": "Offline hardware inventory; excludes bootargs, serials, and vendor properties. ABL may pass a different DTB."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("dtb", type=pathlib.Path)
    p.add_argument("-o", "--output", type=pathlib.Path)
    args = p.parse_args()
    summary = summarize(parse_dtb(args.dtb.read_bytes()))
    encoded = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded)

if __name__ == "__main__":
    main()
