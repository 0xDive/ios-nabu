"""Offline contract between initial NABU ADT generator and XNU CPU matching."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "stage4" / "tools"))
from adt_format import make_node, pack, unpack, u32, cstr
from mkadt_nabu import make_adt


class ADTContractTests(unittest.TestCase):
    def setUp(self):
        self.hardware = {
            "cpu_mpidr": list(range(8)),
            "timer_frequency_hz": 19_200_000,
            "vtimer_intid": 19,
            "gic": {
                "distributor_pa": 0x17A00000,
                "distributor_size": 0x10000,
                "redistributor_pa": 0x17A60000,
                "redistributor_size": 0x100000,
            },
            "ufs": {"controller_pa": 0x1D84000, "controller_size": 0x2500},
        }

    def test_root_model_for_platform_expert(self):
        tree = unpack(pack(make_adt(self.hardware)))
        compatible = tree.props["compatible"].split(bytes(1))
        self.assertIn(b"xiaomi,nabu", compatible)

    def test_cpu_compatible_service_name(self):
        tree = unpack(pack(make_adt(self.hardware)))
        cpus = tree.child("cpus")
        self.assertEqual(len(cpus.children), 8)
        for cpu in cpus.children:
            compatible = cpu.props["compatible"].split(bytes(1))
            self.assertIn(b"qcom,kryo485", compatible)

    def test_gic_and_arch_timer(self):
        tree = unpack(pack(make_adt(self.hardware)))
        gic = tree.child("arm-io").child("gic")
        self.assertEqual(gic.props["virtual-timer-intid"], u32(19))

    def test_not_an_os_adt(self):
        tree = unpack(pack(make_adt(self.hardware)))
        # A minimal compile contract is not a complete iOS ADT.
        self.assertIsNone(tree.child("display"))
        self.assertIsNone(tree.child("apple-aop"))


if __name__ == "__main__":
    unittest.main()
