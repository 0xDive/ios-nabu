"""Synthetic layout tests. No user/device dumps are checked in."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from validate_layout import assess

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
        self.assertEqual(report["entry_physical"], hex(BASE+128))
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

    def test_address_overflow(self):
        with self.assertRaisesRegex(ValueError, "64-bit"):
            assess(sample_kernel(), sample_fdt(), 0xffffffffffff0000, 16384)


if __name__ == "__main__":
    unittest.main()
