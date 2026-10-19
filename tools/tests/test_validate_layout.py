"""Synthetic layout tests. No user/device dumps are checked in."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from validate_layout import assess, XNU_L2_BLOCK

BASE = 0x100000000
VIRT = 0xFFFFFFF007004000


def sample_kernel():
    return {
        "entry_in_segment": True,
        "entry_va": hex(VIRT + 128),
        "segments": [
            {"name": "__TEXT", "vmaddr": hex(VIRT), "vmsize": 0x8000, "filesize": 0x4000},
            {"name": "__DATA", "vmaddr": hex(VIRT+0x8000), "vmsize": 0xC000, "filesize": 0x2000},
        ],
    }


def sample_fdt():
    return {
        "memory_banks": {"memory": [
            {"address": hex(BASE), "end_exclusive": hex(BASE + 0x40000000)}
        ]},
        "reserved_memory": {"firmware": [
            {"address": hex(BASE+0x08000000),
             "end_exclusive": hex(BASE+0x09000000)}
        ]},
    }


class LayoutTests(unittest.TestCase):
    def test_valid_is_never_runtime_approval(self):
        report = assess(sample_kernel(), sample_fdt(), BASE, 10000,
                        (BASE+0x20000000, BASE+0x20100000))
        block = VIRT & ~(XNU_L2_BLOCK - 1)
        self.assertEqual(report["virtual_base"], hex(block))
        self.assertEqual(report["entry_physical"], hex(BASE + VIRT - block + 128))
        self.assertEqual(report["first_segment_physical"], hex(BASE + VIRT - block))
        self.assertEqual(report["mapping_prefix_bytes"], VIRT - block)
        self.assertEqual(report["virtual_mapping_block_bytes"], XNU_L2_BLOCK)
        self.assertFalse(report["safe_to_boot"])
        self.assertFalse(report["runtime_free_verified"])
        self.assertEqual(int(report["boot_args_physical"], 16) % 16384, 0)

    def test_collision_with_reserved_fdt_memory(self):
        with self.assertRaisesRegex(ValueError, "Reserved-memory"):
            assess(sample_kernel(), sample_fdt(), BASE+0x08000000, 16384)

    def test_collision_with_initrd(self):
        with self.assertRaisesRegex(ValueError, "initrd"):
            assess(sample_kernel(), sample_fdt(), BASE, 16384,
                   (BASE+0x1000, BASE+0x3000))

    def test_unaligned_kernel_base(self):
        with self.assertRaisesRegex(ValueError, "aligned"):
            assess(sample_kernel(), sample_fdt(), BASE+1, 16384)

    def test_outside_ram(self):
        with self.assertRaisesRegex(ValueError, "RAM bank"):
            assess(sample_kernel(), sample_fdt(), BASE+0x3fff0000, 16384)

    def test_excessive_kernel(self):
        kernel = sample_kernel()
        kernel["segments"][-1]["vmsize"] = 300 * 1024 * 1024
        with self.assertRaisesRegex(ValueError, "256 MiB"):
            assess(kernel, sample_fdt(), BASE, 16384)

    def test_invalid_kernel_entry(self):
        kernel = sample_kernel()
        kernel["entry_in_segment"] = False
        with self.assertRaisesRegex(ValueError, "entry"):
            assess(kernel, sample_fdt(), BASE, 16384)

    def test_overlapping_segments(self):
        kernel = sample_kernel()
        kernel["segments"][-1]["vmaddr"] = hex(VIRT+0x4000)
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            assess(kernel, sample_fdt(), BASE, 16384)

    def test_actual_nabu_xnu_8796_macho_metadata(self):
        # Selected segment layout and entry address from successful host-side
        # run 39295105141; no XNU binary or user device dumps are included.
        text = 0xFFFFFE0007004000
        macho = {
            "entry_in_segment": True,
            "entry_va": "0xFFFFFE000748B488",
            "segments": [
                {"name":"__TEXT","vmaddr":hex(text),
                 "vmsize":0x160000,"filesize":0x160000},
                {"name":"__TEXT_EXEC","vmaddr":"0xfffffe00072e4000",
                 "vmsize":8732672,"filesize":8732672},
                {"name":"__CTF","vmaddr":"0xfffffe0008110000",
                 "vmsize":0,"filesize":606208},
                {"name":"__LINKEDIT","vmaddr":"0xfffffe0008110000",
                 "vmsize":3885456,"filesize":3885456}
            ]
        }
        hardware = {
            "memory_banks":{"memory":[{"address":"0x100000000",
                    "end_exclusive":"0x200000000"}]},
            "reserved_memory":{
                "camera_region":{"ranges":[{"address":"0x8b700000",
                        "end_exclusive":"0x8bc00000"}],"no_map":True},
                "linux,cma":{"ranges":[],"dynamic_size_bytes":134217728}
            }
        }
        report = assess(macho,hardware,BASE,4096)
        self.assertEqual(report["virtual_base"],"0xfffffe0006000000")
        self.assertEqual(report["first_segment_physical"],"0x101004000")
        self.assertEqual(report["entry_physical"],"0x10148b488")
        self.assertEqual(report["mapping_prefix_bytes"],0x1004000)
        self.assertIn("linux,cma",report["dynamic_reservations_unresolved"])
        self.assertFalse(report["runtime_free_verified"])
        self.assertFalse(report["safe_to_boot"])

    def test_fdt_nested_reserved_memory_collision(self):
        fdt = sample_fdt()
        fdt["reserved_memory"] = {"firmware":{"ranges":[
            {"address":hex(BASE+0x1001000),
             "end_exclusive":hex(BASE+0x1006000)}]}}
        with self.assertRaisesRegex(ValueError,"Reserved-memory"):
            assess(sample_kernel(), fdt, BASE,4096)

    def test_unknown_file_only_segment_rejected(self):
        kernel = sample_kernel()
        kernel["segments"].append({"name":"__UNKNOWN", "vmaddr":hex(VIRT+0x30000),
                                   "vmsize":0,"filesize":64})
        with self.assertRaisesRegex(ValueError,"file-only"):
            assess(kernel,sample_fdt(),BASE,4096)

    def test_address_overflow(self):
        with self.assertRaisesRegex(ValueError, "64-bit"):
            assess(sample_kernel(), sample_fdt(), 0xffffffffffff0000, 16384)


if __name__ == "__main__":
    unittest.main()
