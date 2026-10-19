"""Regression tests for legitimate, file-only XNU Mach-O metadata."""
import pathlib
import struct
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from inspect_kernel import inspect


def mach_o_with_metadata(metadata_name="__CTF", fileoff=460):
    header = struct.pack("<8I",
        0xFEEDFACF, 0x0100000C, 0, 2, 3, 424, 0, 0)
    text = bytearray(72)
    struct.pack_into("<II", text, 0, 0x19, 72)
    text[8:14] = b"__TEXT"
    struct.pack_into("<QQQQ", text, 24, 0x100000000, 0x4000, 456, 4)
    meta = bytearray(72)
    struct.pack_into("<II", meta, 0, 0x19, 72)
    label = metadata_name.encode("ascii")
    meta[8:8+len(label)] = label
    struct.pack_into("<QQQQ", meta, 24, 0, 0, fileoff, 4)
    thread = bytearray(280)
    struct.pack_into("<II", thread, 0, 0x5, 280)
    struct.pack_into("<II", thread, 8, 6, 68)
    struct.pack_into("<Q", thread, 16 + 32*8, 0x100000010)
    return header + text + meta + thread + b"TEXT" + b"DATA"


class CTFMetadataTests(unittest.TestCase):
    def test_file_only_ctf_is_not_mapped_into_ram(self):
        info = inspect(mach_o_with_metadata())
        self.assertTrue(info["entry_in_segment"])
        self.assertEqual(info["segments"][1]["name"], "__CTF")
        self.assertEqual(info["segments"][1]["vmsize"], 0)
        self.assertEqual(info["segments"][1]["filesize"], 4)

    def test_unrecognized_file_only_segment_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "file size larger"):
            inspect(mach_o_with_metadata("__DANGEROUS"))

    def test_ctf_still_has_file_bounds_checks(self):
        with self.assertRaisesRegex(ValueError, "outside Mach-O"):
            inspect(mach_o_with_metadata("__CTF", fileoff=1_000_000))


if __name__ == "__main__":
    unittest.main()
