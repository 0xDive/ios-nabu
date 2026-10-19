"""Portable synthetic-FDT tests for the read-only bare-metal survey."""
import ctypes
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LOW, HIGH = 0x100000000, 0x1024d0000

def be32(n): return struct.pack('>I', n)
def be64(n): return struct.pack('>Q', n)
def pad4(data): return data + bytes((-len(data)) & 3)

def synthetic_fdt(*, dynamic=True, fixed=(0x9c000000, 0x100000),
                  initrd=(0x88000000, 0x89000000), memreserve=None,
                  memory=(0xc0000000, 0x140000000)):
    names = ['model', 'compatible', '#address-cells', '#size-cells',
             'method', 'reg', 'size', 'linux,initrd-start', 'linux,initrd-end']
    strings = b''
    off = {}
    for key in names:
        off[key] = len(strings)
        strings += key.encode('ascii') + b'\0'
    def node(name): return be32(1) + pad4(name.encode() + b'\0')
    def prop(name, value): return be32(3) + be32(len(value)) + be32(off[name]) + pad4(value)
    def close(): return be32(2)
    tree = node('')
    tree += prop('model', b'NABU\0') + prop('compatible', b'qcom,sm8150\0')
    tree += prop('#address-cells', be32(2)) + prop('#size-cells', be32(2))
    tree += node('psci') + prop('compatible', b'arm,psci-1.0\0') + prop('method', b'smc\0') + close()
    tree += node('memory') + prop('reg', be64(memory[0]) + be64(memory[1])) + close()
    tree += node('reserved-memory')
    tree += prop('#address-cells', be32(2)) + prop('#size-cells', be32(2))
    tree += node('fixed') + prop('reg', be64(fixed[0]) + be64(fixed[1])) + close()
    if dynamic: tree += node('dynamic') + prop('size', be64(8*1024*1024)) + close()
    tree += close()
    tree += node('chosen')
    if initrd:
        tree += prop('linux,initrd-start', be64(initrd[0]))
        tree += prop('linux,initrd-end', be64(initrd[1]))
    tree += close() + close() + be32(9)
    reservations = b''.join(be64(start) + be64(size) for start,size in (memreserve or []))
    reservations += bytes(16)
    off_struct = 40 + len(reservations)
    off_strings = off_struct + len(tree)
    total = off_strings + len(strings)
    header = struct.pack('>10I', 0xd00dfeed, total, off_struct, off_strings, 40,
                         17, 16, 0, len(strings), len(tree))
    return header + reservations + tree + strings

class Result(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint8) for name in (
        'fdt_valid', 'root_cells_2_2', 'reserved_cells_2_2',
        'candidate_inside_dram', 'fixed_overlap', 'dynamic_unresolved',
        'ramdisk_present', 'ramdisk_overlap', 'fdt_self_overlap',
        'reserve_table_valid', 'reserve_table_overlap')] + [
            ('reserve_entries', ctypes.c_uint32), ('dynamic_nodes', ctypes.c_uint32)]

class SurveyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = shutil.which('cc') or shutil.which('clang')
        if not cc: raise unittest.SkipTest('C compiler unavailable')
        cls.temp = tempfile.TemporaryDirectory()
        target = Path(cls.temp.name) / 'survey.so'
        subprocess.run([cc,'-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',
                        str(ROOT/'src/survey.c'),'-o',str(target)],check=True)
        cls.dll = ctypes.CDLL(str(target))
        cls.dll.survey_fdt.argtypes = [ctypes.c_void_p,ctypes.c_uint64,ctypes.c_uint64]
        cls.dll.survey_fdt.restype = Result
    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()
    def check(self, content, lo=LOW, hi=HIGH):
        payload = ctypes.create_string_buffer(bytes(content))
        return self.dll.survey_fdt(payload, lo, hi)
    def test_expected_dynamic_unknown(self):
        v = self.check(synthetic_fdt())
        self.assertTrue(v.fdt_valid and v.candidate_inside_dram and v.ramdisk_present)
        self.assertEqual(v.dynamic_nodes, 1)
        self.assertEqual((v.fixed_overlap,v.ramdisk_overlap,v.reserve_table_overlap),(0,0,0))
    def test_fixed_reservation_overlap(self):
        v = self.check(synthetic_fdt(fixed=(0x101000000, 0x100000)))
        self.assertEqual(v.fixed_overlap,1)
    def test_ramdisk_collision(self):
        v = self.check(synthetic_fdt(initrd=(LOW+0x1000, LOW+0x100000)))
        self.assertEqual(v.ramdisk_overlap,1)
    def test_memreserve_collision(self):
        v = self.check(synthetic_fdt(memreserve=[(LOW+0x100000, 0x1000)]))
        self.assertEqual((v.reserve_entries,v.reserve_table_overlap),(1,1))
    def test_candidate_not_inside_dram(self):
        v = self.check(synthetic_fdt(memory=(0xc0000000,0x10000000)))
        self.assertEqual(v.candidate_inside_dram,0)
    def test_dynamic_absent(self):
        v = self.check(synthetic_fdt(dynamic=False))
        self.assertEqual(v.dynamic_nodes,0)
        self.assertEqual(v.dynamic_unresolved,0)
    def test_missing_initrd(self):
        v = self.check(synthetic_fdt(initrd=None))
        self.assertEqual(v.ramdisk_present,0)
    def test_invalid_fdt(self):
        data = bytearray(synthetic_fdt())
        data[0] = 0
        self.assertEqual(self.check(data).fdt_valid,0)
    def test_bad_reserve_entry(self):
        data = bytearray(synthetic_fdt())
        data[40:48] = bytes([0xff])*8
        data[48:56] = bytes([0xff])*8
        self.assertEqual(self.check(data).fdt_valid,0)

if __name__=='__main__': unittest.main()
