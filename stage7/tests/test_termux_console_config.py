"""Synthetic, read-only coverage of the rooted Termux console Kconfig check."""
from __future__ import annotations

import gzip
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "termux_console_config.sh"


class ConsoleConfigTests(unittest.TestCase):
    def fixture(self, *, installed=True, bound=False, config=True,
                console="n", poll="n"):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            platform = root / "sys/bus/platform/devices/a90000.qcom,qup_uart"
            driver = root / "sys/bus/platform/drivers/msm_geni_serial"
            driver.mkdir(parents=True)
            if installed:
                platform.mkdir(parents=True)
                (platform / "uevent").write_text(
                    "OF_COMPATIBLE_0=qcom,msm-geni-console\n"
                    "PRIVATE_SERIAL=DO_NOT_PRINT\n",
                    encoding="utf-8",
                )
                if bound:
                    (platform / "driver").symlink_to(driver)
            if config:
                out = root / "proc/config.gz"
                out.parent.mkdir(parents=True)
                lines = [
                    ("CONFIG_SERIAL_CORE_CONSOLE=y" if console=="y"
                     else "# CONFIG_SERIAL_CORE_CONSOLE is not set"),
                    ("CONFIG_CONSOLE_POLL=y" if poll=="y"
                     else "# CONFIG_CONSOLE_POLL is not set"),
                    "CONFIG_SERIAL_MSM_GENI=y",
                    "CONFIG_PRIVATE_KEY=DO_NOT_PRINT",
                ]
                out.write_bytes(gzip.compress(("\n".join(lines)+"\n").encode()))
            result = subprocess.run(
                ["sh",str(SCRIPT)],
                env={**os.environ, "NABU_SYSROOT":str(root)},
                text=True, capture_output=True, check=False, timeout=10,
            )
            return result

    def test_missing_console_flags_visible_with_no_driver_binding(self):
        result = self.fixture()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("console_driver_binding=none", result.stdout)
        self.assertIn("# CONFIG_SERIAL_CORE_CONSOLE is not set",result.stdout)
        self.assertIn("# CONFIG_CONSOLE_POLL is not set",result.stdout)
        self.assertIn("CONFIG_SERIAL_MSM_GENI=y",result.stdout)
        self.assertIn("hs_uart_driver_directory=present",result.stdout)
        self.assertNotIn("DO_NOT_PRINT",result.stdout)

    def test_enabled_console_still_does_not_establish_driver_binding(self):
        result=self.fixture(console="y")
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("CONFIG_SERIAL_CORE_CONSOLE=y",result.stdout)
        self.assertIn("console_driver_binding=none",result.stdout)
        self.assertIn("console-driver-condition=hypothesis-not-proven",result.stdout)

    def test_driver_bound(self):
        result=self.fixture(bound=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("console_driver_binding=confirmed",result.stdout)

    def test_missing_proc_config_does_not_infer_disabled(self):
        result=self.fixture(config=False)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("kernel_config=/proc/config.gz-not-available",result.stdout)
        self.assertNotIn("CONFIG_SERIAL_CORE_CONSOLE=y",result.stdout)

    def test_missing_platform_device(self):
        result=self.fixture(installed=False)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("console_platform_device=absent",result.stdout)

    def test_script_syntax_and_no_write_operations(self):
        check=subprocess.run(["sh","-n",str(SCRIPT)],capture_output=True,text=True)
        self.assertEqual(check.returncode,0,check.stderr)
        code="\n".join(l for l in SCRIPT.read_text(encoding="utf-8").splitlines()
                       if l.strip() and not l.lstrip().startswith("#"))
        for pattern in ("> /sys",">/sys","mount -t","insmod ",
                        "modprobe ","devmem ","setprop ","fastboot ",
                        "dmesg ","/proc/cmdline","echo msm_geni_serial >"):
            self.assertNotIn(pattern,code)


if __name__=="__main__":
    unittest.main()
