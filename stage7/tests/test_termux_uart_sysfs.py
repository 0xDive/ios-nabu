"""Host-only regression tests for Stage 7.1 rooted-Termux sysfs reader."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "termux_uart_sysfs.sh"


class TermuxSysfsTests(unittest.TestCase):
    def run_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            soc = root / "sys/firmware/devicetree/base/soc"
            drivers = root / "sys/bus/platform/drivers"
            platforms = root / "sys/bus/platform/devices"
            ttys = root / "sys/class/tty"
            drivers.mkdir(parents=True)
            platforms.mkdir(parents=True)
            ttys.mkdir(parents=True)
            (drivers / "msm_geni_serial").mkdir()
            (drivers / "i2c_geni").mkdir()
            for address, compatible in (
                ("a90000", "qcom,msm-geni-console"),
                ("c8c000", "qcom,msm-geni-serial-hs"),
                ("a84000", "qcom,msm-geni-serial-hs"),
            ):
                node = soc / f"qcom,qup_uart@0x{address}"
                node.mkdir(parents=True)
                (node / "compatible").write_bytes(compatible.encode() + bytes(1))
                status = b"disabled" if address == "a84000" else b"ok"
                (node / "status").write_bytes(status + bytes(1))
                (node / "clock-names").write_bytes(b"se-clk" + bytes(1))
                (node / "private-key").write_text("DO_NOT_READ_THIS", encoding="utf-8")
                device = platforms / f"{address}.qcom,qup_uart"
                device.mkdir()
                (device / "of_node").symlink_to(node)
                if address == "c8c000":
                    (device / "driver").symlink_to(drivers / "msm_geni_serial")
                    tty = ttys / "ttyHS0"
                    tty.mkdir()
                    (tty / "device").symlink_to(device)
            # The same QUP SE at 0xA84000 is bound as i2c_geni, not
            # a second UART: this occurred on the real Xiaomi Pad 5.
            i2c_node = soc / "i2c@a84000"
            i2c_node.mkdir()
            i2c_device = platforms / "a84000.i2c"
            i2c_device.mkdir()
            (i2c_device / "of_node").symlink_to(i2c_node)
            (i2c_device / "driver").symlink_to(drivers / "i2c_geni")
            result = subprocess.run(
                ["sh", str(SCRIPT)],
                capture_output=True, text=True, errors="replace", check=False,
                env={**os.environ, "NABU_SYSROOT":str(root)},
            )
            return result

    def test_maps_only_real_uart_tty(self):
        result = self.run_fixture()
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("=== UART MMIO 0xa90000 ===",result.stdout)
        self.assertIn("=== UART MMIO 0xc8c000 ===",result.stdout)
        self.assertIn("uart_platform_device=a90000.qcom,qup_uart",result.stdout)
        self.assertIn("driver_symlink_present=no",result.stdout)
        self.assertIn("driver_binding=not-confirmed",result.stdout)
        self.assertIn("driver_binding=confirmed",result.stdout)
        self.assertIn("msm_geni_serial",result.stdout)
        self.assertIn("tty=ttyHS0",result.stdout)
        self.assertIn("c8c000.qcom,qup_uart",result.stdout)
        self.assertIn("other_protocol_device=a84000.i2c (I2C, not UART)",result.stdout)
        self.assertIn("uart_platform_device=a84000.qcom,qup_uart",result.stdout)
        self.assertNotIn("uart_platform_device=a84000.i2c",result.stdout)
        self.assertIn("read_only=yes",result.stdout)
        self.assertIn("abl_uart_state_proven=no",result.stdout)

    def test_never_outputs_private_properties(self):
        result = self.run_fixture()
        self.assertNotIn("DO_NOT_READ_THIS",result.stdout)
        self.assertNotIn("private-key",result.stdout)

    def test_shell_syntax(self):
        result=subprocess.run(["sh","-n",str(SCRIPT)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_static_read_only_contract(self):
        data=SCRIPT.read_text(encoding="utf-8")
        # Comments may discuss prohibited operations. Inspect executable lines.
        executable="\n".join(
            line for line in data.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        for token in ("> /sys",">/sys","mount -t","devmem","setprop ",
                      "fastboot ","insmod ","modprobe ",
                      "/proc/kallsyms","/proc/cmdline","dmesg "):
            self.assertNotIn(token,executable)


if __name__ == "__main__":
    unittest.main()
