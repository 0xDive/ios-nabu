"""Host-test the exact C parser compiled into Stage 6; only synthetic FDT in CI."""
from __future__ import annotations
import ctypes
import os
import pathlib
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CANDIDATE_LO = 0x100000000
CANDIDATE_HI = 0x1F0000000
IMAGE_LO = 0x85000000
IMAGE_HI = 0x85010000
DTB_PA = 0x88000000
INITRD_LO = 0x90000000
INITRD_HI = 0x90100000


def be32(value):
    return struct.pack(">I", value)


def pad4(data):
    return data + bytes((-len(data)) % 4)


def dtb(*, ram_end=0x200000000, fixed=None, dynamic=7, memreserve=None,
        malformed_reg=False):
    """Synthetic FDT following the actual nabu's 2/2 cell convention."""
    keys = ("#address-cells", "#size-cells", "model", "compatible", "reg",
            "size", "method", "linux,initrd-start", "linux,initrd-end")
    strings = b"".join(key.encode() + b"\0" for key in keys)
    offsets = {name: strings.index(name.encode() + b"\0") for name in keys}

    def node(name):
        return be32(1) + pad4(name.encode() + b"\0")

    def prop(key, value):
        return be32(3) + be32(len(value)) + be32(offsets[key]) + pad4(value)

    end = be32(2)
    tree = node("")
    tree += prop("#address-cells", be32(2))
    tree += prop("#size-cells", be32(2))
    tree += prop("model", b"NABU\0")
    tree += prop("compatible", b"qcom,sm8150\0xiaomi,nabu\0")
    tree += node("psci")
    tree += prop("compatible", b"arm,psci-1.0\0")
    tree += prop("method", b"smc\0")
    tree += end
    tree += node("chosen")
    tree += prop("linux,initrd-start", struct.pack(">Q", INITRD_LO))
    tree += prop("linux,initrd-end", struct.pack(">Q", INITRD_HI))
    tree += end
    tree += node("memory")
    regs = struct.pack(">QQQQ", 0x80000000, 0x3CC00000,
                       0xC0000000, ram_end - 0xC0000000)
    if malformed_reg:
        regs = regs[:-1]
    tree += prop("reg", regs)
    tree += end
    tree += node("reserved-memory")
    tree += prop("#address-cells", be32(2))
    tree += prop("#size-cells", be32(2))
    if fixed:
        for i, (start, size) in enumerate(fixed):
            tree += node(f"carveout@{i:x}")
            tree += prop("reg", struct.pack(">QQ", start, size))
            tree += end
    for index in range(dynamic):
        tree += node(f"dynamic@{index}")
        tree += prop("size", struct.pack(">Q", 0x100000))
        tree += end
    tree += end + end + be32(9)
    reserve = b"".join(struct.pack(">QQ", a, sz) for a, sz in (memreserve or []))
    reserve += bytes(16)   # mandatory 0/0 terminator
    off_reserve = 40
    off_struct = off_reserve + len(reserve)
    off_strings = off_struct + len(tree)
    total = off_strings + len(strings)
    header = struct.pack(">10I", 0xD00DFEED, total, off_struct, off_strings,
                         off_reserve, 17, 16, 0, len(strings), len(tree))
    return header + reserve + tree + strings


class MemoryReport(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in (
        "valid", "candidate_in_ram", "fixed_conflict", "loaded_conflict",
        "dynamic_unknown", "initrd_valid", "ram_bank_count",
        "fixed_count", "memreserve_count"
    )]


class NativeAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("cc") or shutil.which("clang")
        if not compiler:
            raise unittest.SkipTest("C compiler not installed")
        cls.temp = tempfile.TemporaryDirectory()
        shared = pathlib.Path(cls.temp.name) / "nabu_probe.so"
        subprocess.run([compiler, "-std=c11", "-O2", "-fPIC", "-shared",
                        "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "src" / "memory_probe.c"),
                        "-o", str(shared)], check=True)
        cls.lib = ctypes.CDLL(str(shared))
        cls.lib.nabu_memory_probe.argtypes = [ctypes.c_void_p] + [ctypes.c_uint64] * 7
        cls.lib.nabu_memory_probe.restype = MemoryReport

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_probe(self, tree, *, image=(IMAGE_LO, IMAGE_HI),
                  dtb_pa=DTB_PA, initrd=(INITRD_LO, INITRD_HI)):
        buf = ctypes.create_string_buffer(tree)
        return self.lib.nabu_memory_probe(
            buf, dtb_pa, image[0], image[1],
            CANDIDATE_LO, CANDIDATE_HI, initrd[0], initrd[1]
        )

    def test_dynamic_reservations_are_unresolved(self):
        r = self.run_probe(dtb())
        self.assertEqual((r.valid, r.candidate_in_ram, r.fixed_conflict), (1, 1, 0))
        self.assertEqual((r.loaded_conflict, r.dynamic_unknown), (0, 7))
        self.assertEqual(r.ram_bank_count, 2)

    def test_no_dynamic_reservations_does_not_prove_ram_free(self):
        r = self.run_probe(dtb(dynamic=0))
        self.assertEqual((r.valid, r.candidate_in_ram, r.dynamic_unknown), (1, 1, 0))

    def test_fixed_reservation_overlap(self):
        r = self.run_probe(dtb(fixed=[(CANDIDATE_LO + 0x10000, 0x100000)]))
        self.assertEqual((r.valid, r.fixed_conflict), (1, 1))

    def test_fdt_memreserve_overlap(self):
        r = self.run_probe(dtb(memreserve=[(CANDIDATE_LO + 0x10000, 0x20000)]))
        self.assertEqual((r.valid, r.memreserve_count, r.fixed_conflict), (1, 1, 1))

    def test_fdt_in_candidate(self):
        r = self.run_probe(dtb(), dtb_pa=CANDIDATE_LO + 0x20000)
        self.assertEqual((r.valid, r.loaded_conflict), (1, 1))

    def test_image_in_candidate(self):
        r = self.run_probe(dtb(), image=(CANDIDATE_LO+0x4000,CANDIDATE_LO+0x8000))
        self.assertEqual((r.valid, r.loaded_conflict), (1, 1))

    def test_ramdisk_in_candidate(self):
        r = self.run_probe(dtb(), initrd=(CANDIDATE_LO+0x4000,CANDIDATE_LO+0x8000))
        self.assertEqual((r.valid, r.loaded_conflict), (1, 1))

    def test_candidate_outside_ram(self):
        r = self.run_probe(dtb(ram_end=0x180000000))
        self.assertEqual((r.valid, r.candidate_in_ram), (1, 0))

    def test_invalid_reg_fails_closed(self):
        r = self.run_probe(dtb(malformed_reg=True))
        self.assertEqual(r.valid, 0)

    def test_header_corruption_fails_closed(self):
        damaged = bytearray(dtb())
        damaged[0] ^= 1
        self.assertEqual(self.run_probe(damaged).valid, 0)

    def test_memreserve_requires_terminator(self):
        bad = bytearray(dtb(memreserve=[(0x88000000, 0x1000)]))
        bad[56:72] = struct.pack(">QQ", 0x88100000, 0x1000)
        self.assertEqual(self.run_probe(bad).valid, 0)

    def test_missing_initrd_fails_closed(self):
        r = self.run_probe(dtb(), initrd=(0, 0))
        self.assertEqual(r.valid, 0)

    @unittest.skipUnless(os.environ.get("NABU_DTB") and
                         pathlib.Path(os.environ["NABU_DTB"]).is_file(),
                         "Keep personal DTB outside repository and CI")
    def test_optional_personal_dtb(self):
        tree = pathlib.Path(os.environ["NABU_DTB"]).read_bytes()
        r = self.run_probe(tree)
        self.assertEqual((r.valid, r.candidate_in_ram), (1, 1))
        self.assertGreaterEqual(r.dynamic_unknown, 1)


if __name__ == "__main__":
    unittest.main()
