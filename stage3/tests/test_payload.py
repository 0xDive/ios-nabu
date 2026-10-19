from __future__ import annotations
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import payload
import bootimg


class PayloadTests(unittest.TestCase):
    def test_roundtrip(self):
        code = b'\x01\x02\x03\x04'*5
        blob = payload.pack(code)
        self.assertEqual(payload.inspect(blob)['length'], 20)
        self.assertEqual(blob[64:], code)

    def test_reject_corruption(self):
        data = bytearray(payload.pack(b'abcd'))
        data[-1] ^= 1
        with self.assertRaises(ValueError):
            payload.inspect(data)

    def test_reject_wrong_token(self):
        data = bytearray(payload.pack(b'abcd'))
        data[28] ^= 0x01
        with self.assertRaises(ValueError):
            payload.inspect(data)

    def test_actual_stage3_boot_payload(self):
        p = ROOT / 'out' / 'nabu-stage3-handoff.img'
        if not p.exists():
            self.skipTest('Build image first')
        data = p.read_bytes()
        info = bootimg.read_header(data)
        ofs = info['ramdisk_offset']
        buf = data[ofs:ofs+info['ramdisk_size']]
        self.assertEqual(payload.inspect(buf)['token'], hex(payload.TOKEN))
        self.assertEqual(buf[:8], payload.MAGIC)


if __name__ == '__main__':
    unittest.main()
