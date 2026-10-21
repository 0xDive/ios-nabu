import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "check_sources.py"
spec = importlib.util.spec_from_file_location("check_sources", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

MANIFEST = Path(__file__).resolve().parents[1] / "nabu-reference.toml"


class NabuReferenceContract(unittest.TestCase):
    def load_plan(self):
        import tomllib
        with MANIFEST.open("rb") as f:
            return tomllib.load(f)

    def test_target_is_nonbootable(self):
        data = self.load_plan()
        module.validate_plan(data)
        self.assertFalse(data["target"]["safe_to_boot"])
        self.assertFalse(data["xnu"]["abi_compatible"])
        self.assertFalse(any(data["handoff"].values()))

    def test_handoff_must_not_claim_success(self):
        data = self.load_plan()
        data["handoff"]["verified_early_ram_map"] = True
        with self.assertRaises(ValueError):
            module.validate_plan(data)

    def test_unixnu_generation_mismatch_must_be_explicit(self):
        data = self.load_plan()
        data["xnu"]["abi_compatible"] = True
        with self.assertRaises(ValueError):
            module.validate_plan(data)

    def test_sources_are_checked_by_immutable_paths(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            u = root / "unixnu"
            d = root / "darwinboot"
            for f in module.REQUIRED_UNIXNU:
                path = u / f
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# reference fixture\n")
            (u / "feeds.toml").write_text(
                '[[source]]\nname="xnu"\ncommit="d8b80295118ef25ac3a784134bcf95cd8e88109f"\n'
            )
            for f in module.REQUIRED_DARWIN:
                path = d / f
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# reference fixture\n")
            (d / "DarwinBootPkg/Driver/DarwinBoot.inf").write_text(
                "MODULE_TYPE = UEFI_DRIVER\n"
                "  UniXNUPkg/UniXNUPkg.dec\n"
                "  gUniXNULoaderProtocolGuid\n"
            )
            report = module.inspect(MANIFEST, u, d)
            self.assertFalse(report["safe_to_boot"])
            self.assertEqual(len(report["inspected_files"]), 11)
            self.assertEqual(report["existing_nabu_xnu_generation"], 8796)


if __name__ == "__main__":
    unittest.main()
