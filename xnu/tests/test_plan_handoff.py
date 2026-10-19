"""Synthetic end-to-end Stage 5 checks; no real kernel or private DTB used."""
from __future__ import annotations
import copy
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "xnu" / "tools"))
sys.path.insert(0, str(ROOT / "stage4" / "tools"))
sys.path.insert(0, str(ROOT / "tools"))
from adt_format import make_node, pack, cstr, u64
from boot_args import make as make_boot_args
from plan_handoff import plan
from validate_layout import assess

PHYS = 0x100000000
TEXT = 0xFFFFFE0007004000


def metadata():
    return {
        "format": "Mach-O 64-bit ARM64",
        "filetype": "0x00000002",
        "file_bytes": 0xA000,
        "entry_in_segment": True,
        "entry_va": hex(TEXT + 0x5000),
        "chained_fixups": None,
        "segments": [
            {"name":"__TEXT", "vmaddr":hex(TEXT),
             "vmsize":0x4000, "fileoff":0, "filesize":0x4000},
            {"name":"__TEXT_EXEC", "vmaddr":hex(TEXT+0x4000),
             "vmsize":0x4000, "fileoff":0x4000, "filesize":0x4000},
            {"name":"__DATA", "vmaddr":hex(TEXT+0x8000),
             "vmsize":0x8000, "fileoff":0x8000, "filesize":0x1000},
            {"name":"__CTF", "vmaddr":hex(TEXT+0x10000),
             "vmsize":0, "fileoff":0x9000, "filesize":0x1000}
        ]
    }


def adt():
    return pack(make_node("device-tree", {
        "compatible": cstr("xiaomi,nabu") + cstr("qcom,sm8150")
    }, [make_node("chosen", {
        "dram-base": u64(PHYS),
        "dram-size": u64(0x40000000)
    })]))


def fdt():
    return {
        "memory_banks": {"memory":[
            {"address":hex(PHYS), "end_exclusive":hex(PHYS+0x40000000)}]},
        "reserved_memory": {"linux,cma":{
            "ranges":[], "dynamic_size_bytes":0x1000000
        }}
    }


def specimen():
    m = metadata()
    blob = adt()
    layout = assess(m, fdt(), PHYS, len(blob))
    args = make_boot_args(layout, blob, 0x40000000)
    return m, layout, blob, args


class HandoffTests(unittest.TestCase):
    def test_complete_nonexecutable_plan(self):
        m, layout, blob, args = specimen()
        report = plan(m, layout, blob, args)
        self.assertEqual(report["schema"], "ios-nabu-stage5-offline-handoff-v1")
        self.assertEqual(report["mapped_segment_count"], 3)
        self.assertEqual(report["virtual_base"], "0xfffffe0006000000")
        self.assertEqual(report["entry_physical"], hex(PHYS + TEXT + 0x5000 - int(report["virtual_base"],16)))
        self.assertFalse(report["safe_to_boot"])
        self.assertFalse(report["runtime_memory_verified"])
        self.assertIn("linux,cma", report["unresolved_dynamic_reservations"])
        copies = [x for x in report["operations"] if x["operation"] == "copy_from_macho"]
        zeros = [x for x in report["operations"] if x["operation"] == "zero_bss"]
        self.assertEqual(len(copies), 3)
        self.assertEqual(len(zeros), 1)
        self.assertEqual(zeros[0]["bytes"], 0x7000)
        self.assertNotIn("__CTF", [x["segment"] for x in report["operations"]])

    def test_rejects_chained_fixups(self):
        m, layout, blob, args = specimen()
        m["chained_fixups"] = {"dataoff":0x10,"datasize":0x20}
        with self.assertRaisesRegex(ValueError, "fixups"):
            plan(m, layout, blob, args)

    def test_rejects_different_entry(self):
        m, layout, blob, args = specimen()
        m["entry_va"] = hex(TEXT+0x8000)
        with self.assertRaisesRegex(ValueError, "entry physical"):
            plan(m, layout, blob, args)

    def test_rejects_entry_not_in_executable_segment(self):
        m, layout, blob, args = specimen()
        m["entry_va"] = hex(TEXT+0x8000)
        layout["entry_physical"] = hex(PHYS + (TEXT+0x8000)-int(layout["virtual_base"],16))
        with self.assertRaisesRegex(ValueError, "__TEXT_EXEC"):
            plan(m, layout, blob, args)

    def test_rejects_boot_args_adt_pointer_disagreement(self):
        m, layout, blob, args = specimen()
        data = bytearray(args)
        struct.pack_into("<Q", data, 96, 0xFFFFFE0010000000)
        with self.assertRaisesRegex(ValueError, "ADT virtual pointer"):
            plan(m, layout, blob, bytes(data))

    def test_rejects_segment_load_outside_file(self):
        m, layout, blob, args = specimen()
        m["segments"][2]["fileoff"] = 0xFFFFFF
        with self.assertRaisesRegex(ValueError, "outside Mach-O"):
            plan(m, layout, blob, args)

    def test_rejects_different_layout_mapping(self):
        m, layout, blob, args = specimen()
        layout["mapped_segments"][1]["start"] = hex(PHYS)
        with self.assertRaisesRegex(ValueError, "mapping disagree"):
            plan(m, layout, blob, args)

    def test_rejects_unverified_run_time_layout(self):
        m, layout, blob, args = specimen()
        layout["safe_to_boot"] = True
        with self.assertRaisesRegex(ValueError, "offline-only"):
            plan(m, layout, blob, args)

    def test_rejects_adt_of_other_device(self):
        m, layout, _, args = specimen()
        bad = pack(make_node("device-tree", {
            "compatible": cstr("xiaomi,sweet") + cstr("qcom,sm7150")
        }, [make_node("chosen",{
            "dram-base":u64(PHYS),"dram-size":u64(0x40000000)
        })]))
        with self.assertRaisesRegex(ValueError, "nabu"):
            plan(m,layout,bad,args)

    def test_rejects_unrecognized_file_only_segment(self):
        m, layout, blob, args = specimen()
        m["segments"][-1]["name"] = "__UNTRUSTED"
        with self.assertRaisesRegex(ValueError,"file-only"):
            plan(m,layout,blob,args)


if __name__ == "__main__":
    unittest.main()
