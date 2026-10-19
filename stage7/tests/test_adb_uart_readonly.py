"""ADB collector contract tests: fake device, no real ADB or privileged writes."""
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from adb_uart_readonly import collect


class FakeADB:
    def __init__(self, *, connected=True, product="nabu", debugfs=True):
        self.commands = []
        self.connected=connected
        self.product=product
        self.debugfs=debugfs

    def __call__(self, args):
        self.commands.append(args)
        command = " ".join(args[1:])
        if command == "devices":
            text = ("List of devices attached\nABCD123456\tdevice\n"
                    if self.connected else "List of devices attached\n")
        elif command == "shell getprop ro.product.device":
            text = self.product + "\n"
        elif command in ("shell cat /proc/consoles",
                         "shell su -c cat /proc/consoles"):
            text = "ttyMSM0                 -W- (EC  p  )    4:64\n"
        elif command == "shell ls /sys/class/tty":
            text = "tty0 ttyMSM0 ttyGS1 ttyS0 ttyUSB0 random_tty\n"
        elif command.endswith("cat /sys/kernel/debug/clk/clk_summary"):
            if not self.debugfs:
                return subprocess.CompletedProcess(args, 1, "", "Permission denied")
            text = ("clk                                    en prep prot rate\n"
                    "gcc_qupv3_wrap1_s4_clk                    1 1 0 19200000\n"
                    "private_network_key                        1 1 0 20\n"
                    "gcc_qupv3_wrap1_s5_clk                    0 0 0 19200000\n")
        elif command == "shell ls /sys/kernel/debug/pinctrl":
            text = "3000000.pinctrl\n" if self.debugfs else ""
        elif command.endswith("cat /sys/kernel/debug/pinctrl/3000000.pinctrl/pinmux-pins"):
            text = ("pin 85 (gpio85): device qup12 function qup12\n"
                    "pin 86 (gpio86): device qup12 function qup12\n"
                    "pin 105 (gpio105): PRIVATE_WIFI_KEY\n")
        else:
            return subprocess.CompletedProcess(args, 1, "", "not available")
        return subprocess.CompletedProcess(args, 0, text, "")


class RuntimeTests(unittest.TestCase):
    def test_report_filters_device_identifiers_and_private_rows(self):
        fake = FakeADB()
        report = collect(invoke=fake)
        self.assertTrue(report["read_only"])
        self.assertFalse(report["root_used"])
        self.assertEqual(report["consoles_with_uart_like_names"],["ttyMSM0"])
        self.assertEqual(report["uart_like_tty_devices"],["ttyGS1","ttyMSM0","ttyS0"])
        self.assertEqual(len(report["filtered_qup_clock_rows"]),2)
        self.assertTrue(report["clock_debugfs_readable"])
        self.assertEqual(len(report["filtered_gpio85_86_pinctrl_lines"]),2)
        self.assertFalse(report["early_uart_output_confirmed"])
        self.assertNotIn("ABCD123456",str(report))
        self.assertNotIn("PRIVATE",str(report))
        for cmd in fake.commands:
            joined=" ".join(cmd)
            for forbidden in ("mount ", "setprop ", "dmesg", "/proc/cmdline",
                              "devmem", "write", "fastboot", "/proc/kallsyms"):
                self.assertNotIn(forbidden,joined)

    def test_root_mode_still_read_only(self):
        fake=FakeADB()
        report=collect(root=True,invoke=fake)
        self.assertTrue(report["root_used"])
        self.assertTrue(any("su" in call for call in fake.commands))
        self.assertFalse(report["early_uart_output_confirmed"])

    def test_debugfs_unavailable_is_unknown(self):
        fake=FakeADB(debugfs=False)
        report=collect(invoke=fake)
        self.assertFalse(report["clock_debugfs_readable"])
        self.assertEqual(report["filtered_qup_clock_rows"],[])
        self.assertFalse(report["early_uart_output_confirmed"])

    def test_no_authorized_device_fails(self):
        with self.assertRaisesRegex(ValueError,"Exactly one"):
            collect(invoke=FakeADB(connected=False))

    def test_wrong_product_fails(self):
        with self.assertRaisesRegex(ValueError,"not nabu"):
            collect(invoke=FakeADB(product="sweet"))

    def test_denies_multiple_devices(self):
        fake=FakeADB()
        original=fake.__call__
        def run(args):
            result=original(args)
            if args[-1]=="devices":
                result.stdout += "ANOTHER\tdevice\n"
            return result
        with self.assertRaisesRegex(ValueError,"Exactly one"):
            collect(invoke=run)


if __name__ == "__main__":
    unittest.main()
