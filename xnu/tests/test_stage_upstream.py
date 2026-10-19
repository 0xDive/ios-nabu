"""Exercise deterministic patch staging with synthetic files, never Apple inputs."""
from __future__ import annotations
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import stage_upstream


def fake_patch_source(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    expected = sorted(stage_upstream.REQUIRED_PATCHES)
    for filename in expected:
        (root / filename).write_text(
            "diff --git a/SweetCPU.cpp b/SweetCPU.cpp\n"
            "+#ifdef ARM64_BOARD_CONFIG_SWEET\n"
            "+#include <pexpert/arm64/SWEET.h>\n"
            "+/* device: sweet */\n",
            encoding="utf-8",
        )
    for i in range(40):
        (root / f"{i + 100:04d}-extra.patch").write_text(
            f"--- a/file{i}\n+++ b/file{i}\n+NABU no hardware changes\n",
            encoding="utf-8",
        )
    (root / "0019-stage-libpthread.sh").write_text(
        "#!/bin/sh\nprintf 'Sweet SWEET sweet'\n", encoding="utf-8"
    )


class StageTests(unittest.TestCase):
    def test_names_and_contents_are_transformed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "src"
            dest = root / "dst"
            report = root / "report.json"
            fake_patch_source(source)
            metadata = stage_upstream.stage(source, dest, report)
            self.assertEqual(len(metadata["files"]), 45)
            file = dest / "0016-nabu-device-tree-platform-expert.patch"
            text = file.read_text(encoding="utf-8")
            self.assertIn("NabuCPU.cpp", text)
            self.assertIn("ARM64_BOARD_CONFIG_NABU", text)
            self.assertIn("NABU.h", text)
            self.assertNotIn("SWEET", text)
            self.assertNotIn("Sweet", text)
            self.assertTrue((dest / "0019-stage-libpthread.sh").exists())
            saved = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(saved["reference_commit"], stage_upstream.SOURCE_COMMIT)
            self.assertEqual(saved["target_machine_config"], "NABU")
            self.assertEqual(len(saved["files"]), 45)
            self.assertEqual(
                metadata["files"][0]["upstream_sha256"],
                stage_upstream.digest((source / metadata["files"][0]["upstream_filename"]).read_bytes()),
            )

    def test_reject_empty_source(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source").mkdir()
            with self.assertRaises(ValueError):
                stage_upstream.stage(root / "source", root / "dst", root / "report.json")

    def test_reject_collision(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_patch_source(root / "source")
            (root / "dst").mkdir()
            (root / "dst" / "0004-nabu-machine-config.patch").write_text("already here")
            with self.assertRaises(ValueError):
                stage_upstream.stage(root / "source", root / "dst", root / "report.json")

    def test_reject_nested_target(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_patch_source(root / "source")
            with self.assertRaises(ValueError):
                stage_upstream.stage(root / "source", root / "source" / "dest", root / "report.json")

    def test_different_case_mapping(self):
        self.assertEqual(stage_upstream.convert_text("SWEET Sweet sweet"), "NABU Nabu nabu")


if __name__ == "__main__":
    unittest.main()
