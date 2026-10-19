"""Offline tests; personal nabu DTB is optional and never committed."""
import os
import pathlib
import struct
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from adt_format import Node, cstr, u32, u64, make_node, pack, unpack
from inspect_kernel import inspect
from mkadt_nabu import check_dtb, make_adt, BASE, SIZE
from dtb_inspect import parse_dtb


class ADTTests(unittest.TestCase):
    def test_roundtrip(self):
        root = make_node("device-tree", {"model":cstr("NABU")},
                         [make_node("chosen", {"dram-base":u64(BASE)})])
        restored = unpack(pack(root))
        self.assertEqual(restored.props["model"], b"NABU\0")
        self.assertEqual(restored.child("chosen").props["dram-base"], u64(BASE))

    def test_bad_name(self):
        with self.assertRaises(ValueError):
            pack(make_node("root", {"x"*40:b"X"}))

    def test_truncation(self):
        with self.assertRaises(ValueError):
            unpack(pack(make_node("root"))[:-1])

    def test_valid_root(self):
        self.assertEqual(unpack(pack(make_node("root"))).name, "root")


class MachOTests(unittest.TestCase):
    @staticmethod
    def fixture():
        segment = bytearray(72)
        struct.pack_into("<II", segment, 0, 0x19, 72)
        segment[8:14] = b"__TEXT"
        struct.pack_into("<QQQQ", segment, 24, 0x100000000, 0x4000, 392, 4)
        thread = bytearray(280)
        struct.pack_into("<II", thread, 0, 5, 280)
        struct.pack_into("<II", thread, 8, 6, 68)
        struct.pack_into("<Q", thread, 16+32*8, 0x100000020)
        header = struct.pack("<8I", 0xFEEDFACF, 0x0100000C, 0, 2, 2, 352, 0, 0)
        return header+segment+thread+bytes(8)+b"CODE"

    def test_inspection(self):
        got = inspect(self.fixture())
        self.assertTrue(got["entry_in_segment"])
        self.assertEqual(got["segments"][0]["name"], "__TEXT")

    def test_reject_magic(self):
        buf = bytearray(self.fixture())
        buf[0] = 0
        with self.assertRaises(ValueError):
            inspect(buf)

    def test_reject_invalid_segment_offset(self):
        buf = bytearray(self.fixture())
        struct.pack_into("<Q", buf, 32+24+16, 1_000_000)
        with self.assertRaises(ValueError):
            inspect(buf)

    def test_truncated_kernel(self):
        with self.assertRaises(ValueError):
            inspect(self.fixture()[:200])


class RealNabuDTB(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("NABU_DTB") and pathlib.Path(os.environ["NABU_DTB"]).is_file(),
                         "Local personal DTB required")
    def test_hardware(self):
        fdt = parse_dtb(pathlib.Path(os.environ["NABU_DTB"]).read_bytes())
        info = check_dtb(fdt)
        self.assertEqual(len(info["cpu_mpidr"]), 8)
        self.assertEqual(info["timer_frequency_hz"], 19200000)
        self.assertEqual(info["vtimer_intid"], 19)
        self.assertEqual(info["gic"]["distributor_pa"], 0x17A00000)
        self.assertEqual(info["ufs"]["controller_pa"], 0x1D84000)
        self.assertFalse(info["dram_candidate"]["runtime_proven_free"])
        adt = unpack(pack(make_adt(info)))
        self.assertEqual(len(adt.child("cpus").children), 8)
        self.assertEqual(adt.child("arm-io").child("gic").props["virtual-timer-intid"], u32(19))


if __name__ == "__main__":
    unittest.main()
