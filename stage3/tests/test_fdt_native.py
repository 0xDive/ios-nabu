"""Host-side smoke tests for the same C FDT parser linked into Stage 3."""
import ctypes
import os
import pathlib
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def u32(n):
    return struct.pack(">I", n)


def pad4(data):
    return data + bytes(-len(data) % 4)


def make_fdt(model="NABU", compatible="qcom,sm8150-cdp",
             psci="arm,psci-1.0", method="smc",
             initrd_start=0x110000000, initrd_end=0x110000080):
    keys = ["model", "compatible", "method", "linux,initrd-start", "linux,initrd-end"]
    names = b"".join(s.encode()+bytes(1) for s in keys)
    offsets = {key: names.index(key.encode()+bytes(1)) for key in keys}
    def node(name):
        return u32(1)+pad4(name.encode()+bytes(1))
    def prop(name, value):
        return u32(3)+u32(len(value))+u32(offsets[name])+pad4(value)
    tree = node("")
    tree += prop("model", model.encode()+bytes(1))
    tree += prop("compatible", compatible.encode()+bytes(1))
    tree += node("psci")
    tree += prop("compatible", psci.encode()+bytes(1))
    tree += prop("method", method.encode()+bytes(1))
    tree += u32(2) + node("chosen")
    tree += prop("linux,initrd-start", struct.pack(">Q", initrd_start))
    tree += prop("linux,initrd-end", struct.pack(">Q", initrd_end))
    tree += u32(2)+u32(2)+u32(9)
    off_struct = 56
    off_strings = off_struct+len(tree)
    size = off_strings+len(names)
    header = struct.pack(">10I", 0xD00DFEED, size, off_struct, off_strings,
                         40, 17, 16, 0, len(names), len(tree))
    return header+bytes(16)+tree+names


class Result(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint8) for name in
                ("valid","nabu","psci_02_or_newer","method","has_initrd_start",
                 "has_initrd_end")] + [("initrd_start",ctypes.c_uint64),
                                      ("initrd_end",ctypes.c_uint64)]


class NativeParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("cc") or shutil.which("clang")
        if compiler is None:
            raise unittest.SkipTest("No C compiler installed")
        cls.tmp = tempfile.TemporaryDirectory()
        libpath = str(pathlib.Path(cls.tmp.name)/"probe.so")
        subprocess.run([compiler,"-O2","-fPIC","-shared",
                        str(ROOT/"src"/"fdt_probe.c"),"-o",libpath],check=True)
        cls.lib = ctypes.CDLL(libpath)
        cls.lib.nabu_inspect_fdt.argtypes = [ctypes.c_void_p]
        cls.lib.nabu_inspect_fdt.restype = Result

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def parse(self, data):
        buf = ctypes.create_string_buffer(bytes(data))
        return self.lib.nabu_inspect_fdt(buf)

    def test_nabu_smc(self):
        result = self.parse(make_fdt())
        self.assertEqual((result.valid,result.nabu,result.psci_02_or_newer,result.method),
                         (1,1,1,1))
        self.assertEqual((result.initrd_start,result.initrd_end),
                         (0x110000000,0x110000080))

    def test_uppercase_model(self):
        result = self.parse(make_fdt(model="NABU",compatible="qcom,sm8150-cdp"))
        self.assertEqual((result.valid,result.nabu),(1,1))

    def test_other_device_fails(self):
        result = self.parse(make_fdt(model="Other",compatible="qcom,sm8150"))
        self.assertEqual((result.valid,result.nabu),(1,0))

    def test_psci_hvc(self):
        result = self.parse(make_fdt(psci="arm,psci-0.2",method="hvc"))
        self.assertEqual((result.psci_02_or_newer,result.method),(1,2))

    def test_invalid_psci(self):
        result = self.parse(make_fdt(psci="arm,psci",method="smc"))
        self.assertEqual(result.psci_02_or_newer,0)

    def test_corruption(self):
        data = bytearray(make_fdt())
        data[0] = 0
        self.assertEqual(self.parse(data).valid,0)

    @unittest.skipUnless(os.getenv("NABU_DTB") and pathlib.Path(os.getenv("NABU_DTB","")).is_file(),
                         "Personal FDT stays local")
    def test_optional_real_fdt(self):
        result = self.parse(pathlib.Path(os.environ["NABU_DTB"]).read_bytes())
        self.assertEqual((result.valid,result.nabu,result.method),(1,1,1))


if __name__ == "__main__":
    unittest.main()
