"""Offline ABI packing tests for experimental XNU boot_args v2."""
import pathlib
import struct
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
from boot_args import make, inspect, STRUCT_SIZE
from adt_format import make_node, pack, cstr, u64


def adt(extra_padding=0, dram_size=0x40000000):
    chosen = make_node("chosen", {
        "dram-base": u64(0x100000000),
        "dram-size": u64(dram_size),
    })
    root = make_node("device-tree", {
        "compatible": cstr("xiaomi,nabu") + cstr("qcom,sm8150"),
        "pad": b"Z" * extra_padding,
    }, [chosen])
    return pack(root)


def layout():
    base = 0x100000000
    return {
        "status": "STATIC_ONLY",
        "static_no_known_collision": True,
        "safe_to_boot": False,
        "runtime_free_verified": False,
        "physical_base": hex(base),
        "virtual_base": hex(0xfffffe0004000000),
        "adt_physical": hex(base + 0x200000),
        "boot_args_physical": hex(base + 0x204000),
        "allocation_end_exclusive": hex(base + 0x208000),
    }


class BootArgsTests(unittest.TestCase):
    def test_roundtrip(self):
        data = make(layout(), adt(), 0x40000000, "cpus=1 -v")
        self.assertEqual(len(data), STRUCT_SIZE)
        self.assertEqual(struct.unpack_from("<HH", data, 0), (2, 2))
        self.assertEqual(struct.unpack_from("<QQQQ", data, 8),
                         (0xfffffe0004000000, 0x100000000, 0x40000000,
                          0x100208000))
        info = inspect(data)
        self.assertEqual(info["command_line"], "cpus=1 -v")
        self.assertEqual(info["device_tree_va"], hex(0xfffffe0004200000))
        self.assertEqual(info["device_tree_length"], len(adt()))
        self.assertEqual(info["video"], [0] * 6)
        self.assertFalse(info["safe_to_boot"])

    def test_reject_unverified_layout(self):
        src = layout()
        src["status"] = "READY"
        with self.assertRaises(ValueError):
            make(src, adt(), 0x40000000)

    def test_reject_conflicting_boot_ready_flag(self):
        src = layout()
        src["safe_to_boot"] = True
        with self.assertRaises(ValueError):
            make(src, adt(), 0x40000000)

    def test_reject_unaligned_virtual_block(self):
        src = layout()
        src["virtual_base"] = hex(int(src["virtual_base"], 16) + 0x4000)
        with self.assertRaisesRegex(ValueError, "32 MiB aligned"):
            make(src, adt(), 0x40000000)

    def test_reject_inconsistent_first_segment_physical(self):
        src = layout()
        virt = int(src["virtual_base"], 16)
        src["first_segment_va"] = hex(virt + 0x1004000)
        src["first_segment_physical"] = hex(0x100000000)
        with self.assertRaisesRegex(ValueError, "contradicts"):
            make(src, adt(), 0x40000000)

    def test_accept_consistent_block_prefix(self):
        src = layout()
        virt = int(src["virtual_base"], 16)
        src["first_segment_va"] = hex(virt + 0x1004000)
        src["first_segment_physical"] = hex(0x100000000 + 0x1004000)
        self.assertEqual(len(make(src, adt(), 0x40000000)), STRUCT_SIZE)

    def test_reject_misaligned_ram(self):
        src = layout()
        src["adt_physical"] = hex(0x100200001)
        with self.assertRaisesRegex(ValueError, "aligned"):
            make(src, adt(), 0x40000000)

    def test_reject_adt_overlap(self):
        src = layout()
        with self.assertRaisesRegex(ValueError, "overlaps"):
            make(src, adt(extra_padding=0x8000), 0x40000000)

    def test_reject_invalid_command_line(self):
        with self.assertRaises(ValueError):
            make(layout(), adt(), 0x40000000, "too\0bad")
        with self.assertRaises(UnicodeError):
            make(layout(), adt(), 0x40000000, "привет")

    def test_reject_mismatched_adt_dram(self):
        with self.assertRaisesRegex(ValueError, "must match"):
            make(layout(), adt(dram_size=0x20000000), 0x40000000)

    def test_reject_invalid_adt(self):
        with self.assertRaises(ValueError):
            make(layout(), b"not an ADT", 0x40000000)

    def test_reject_unchecked_collision(self):
        src = layout()
        src["static_no_known_collision"] = False
        with self.assertRaisesRegex(ValueError, "collision"):
            make(src, adt(), 0x40000000)

    def test_reject_bad_header(self):
        with self.assertRaisesRegex(ValueError, "736"):
            inspect(bytes(100))


if __name__ == "__main__":
    unittest.main()
