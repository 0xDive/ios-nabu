import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "integrate_fv.py"
spec = importlib.util.spec_from_file_location("integrate_fv", SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class IntegrationTests(unittest.TestCase):
    def make_workspace(self, root):
        root = Path(root)
        dsc = root / "Platforms/Xiaomi/nabuPkg/nabu.dsc"
        fdf = root / "Platforms/Xiaomi/nabuPkg/nabu.fdf"
        dsc.parent.mkdir(parents=True, exist_ok=True)
        dsc.write_text(
            "[Defines]\n"
            "  SOC_TYPE                       = 2\n"
            "[LibraryClasses]\n"
            "  MemoryMapLib|nabuPkg/Library/MemoryMapLib/MemoryMapLib.inf\n"
            "[Components]\n  nabu/AcpiTables.inf\n"
        )
        fdf.write_text(
            "[FD.SILICIUM_UEFI]\n"
            "[FV.FvMain]\n  !include QcomPkg/Extra.fdf.inc\n"
            "[FV.FVMAIN_COMPACT]\n"
        )
        for file in [m.UNI_APP, m.DARWIN, "UniXNUPkg/UniXNUPkg.dec"]:
            file = root / file
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("dummy pinned source\n")
        return root, dsc, fdf

    def test_link_has_no_boot_order_or_variable_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, dsc, fdf = self.make_workspace(tmp)
            result = m.overlay(root)
            self.assertFalse(result["boots_unixnu_automatically"])
            self.assertFalse(result["writes_uefi_boot_order"])
            for content in (dsc.read_text(), fdf.read_text()):
                self.assertIn(m.UNI_APP, content)
                self.assertIn(m.DARWIN, content)
                self.assertNotIn(m.REGISTRAR, content)
            self.assertEqual(dsc.read_text().count(m.UNICORE), 1)
            self.assertEqual(dsc.read_text().count(m.FDTLIB), 1)

    def test_refuses_non_nabu_soc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, dsc, fdf = self.make_workspace(tmp)
            dsc.write_text(dsc.read_text().replace("SOC_TYPE                       = 2",
                                                     "SOC_TYPE                       = 0"))
            with self.assertRaises(ValueError):
                m.overlay(root)

    def test_refuses_duplicate_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, dsc, fdf = self.make_workspace(tmp)
            fdf.write_text(fdf.read_text() + "  INF " + m.UNI_APP)
            with self.assertRaises(ValueError):
                m.overlay(root)


if __name__ == "__main__":
    unittest.main()
