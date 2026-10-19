"""Offline-only USB link snapshots; no Android, root or hardware is accessed."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "termux_usb_link.sh"


class USBLinkSnapshotTests(unittest.TestCase):
    def run_fixture(self, *, label="disconnected", connected=False,
                    present=True, raw_function="android_usb",
                    power=True, role=True, sensitive=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            if present:
                udc = root / "sys/class/udc/a600000.dwc3"
                udc.mkdir(parents=True)
                values = {
                    "state": "configured" if connected else "not attached",
                    "current_speed": "high-speed" if connected else "UNKNOWN",
                    "maximum_speed": "high-speed",
                    "is_otg": "1",
                    "function": raw_function,
                    "serial_number": "PRIVATE_DEVICE_SERIAL_SHOULD_NOT_LEAK",
                }
                for k, value in values.items():
                    (udc / k).write_text(value + "\n")
                if sensitive:
                    (udc / "state").write_text("SECRET SERIAL=abcdef123\n")
                    (udc / "current_speed").write_text("SERIAL_NUMBER_ABC\n")
            if power:
                p = root / "sys/class/power_supply/usb"
                p.mkdir(parents=True)
                (p / "online").write_text("1\n" if connected else "0\n")
                (p / "serial_number").write_text("PRIVATE_CHARGING_SERIAL")
            if role:
                p = root / "sys/class/usb_role/a600000.dwc3"
                p.mkdir(parents=True)
                (p / "role").write_text("device\n" if connected else "none\n")
                (p / "secret_id").write_text("PRIVATE_ROLE_SERIAL")
            args = ["sh", str(SCRIPT), label]
            return subprocess.run(args, capture_output=True, text=True,
                                  check=False, timeout=10,
                                  env={**os.environ,"NABU_SYSROOT":str(root)})

    def test_disconnected_snapshot(self):
        r=self.run_fixture()
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn("label=disconnected",r.stdout)
        self.assertIn("udc_state=not attached",r.stdout)
        self.assertIn("current_speed=UNKNOWN",r.stdout)
        self.assertIn("maximum_speed=high-speed",r.stdout)
        self.assertIn("otg_capable=1",r.stdout)
        self.assertIn("gadget_driver_assigned=yes",r.stdout)
        self.assertIn("android_usb_power_online=0",r.stdout)
        self.assertIn("usb_role_1=none",r.stdout)
        self.assertIn("bootloader_usb_gadget_tested=no",r.stdout)
        self.assertIn("device_settings_changed=no",r.stdout)

    def test_connected_snapshot(self):
        r=self.run_fixture(label="connected",connected=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn("udc_state=configured",r.stdout)
        self.assertIn("current_speed=high-speed",r.stdout)
        self.assertIn("android_usb_power_online=1",r.stdout)
        self.assertIn("usb_role_1=device",r.stdout)

    def test_no_udc_is_unavailable_not_broken(self):
        r=self.run_fixture(present=False,power=False,role=False)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn("udc=unavailable",r.stdout)
        self.assertIn("android_usb_power_online=unavailable",r.stdout)
        self.assertIn("usb_role_sysfs=unavailable",r.stdout)

    def test_never_prints_sensitive_scalar_or_function(self):
        r=self.run_fixture(sensitive=True, raw_function="SECRET_KEY_MAC_123")
        self.assertEqual(r.returncode,0,r.stderr)
        for secret in ("PRIVATE", "SECRET", "abcdef123", "SERIAL_NUMBER_ABC"):
            self.assertNotIn(secret,r.stdout)
        self.assertIn("udc_state=unavailable",r.stdout)
        self.assertIn("current_speed=unavailable",r.stdout)
        self.assertIn("gadget_driver_assigned=yes",r.stdout)

    def test_unknown_gadget_driver_does_not_claim_attached(self):
        r=self.run_fixture(raw_function="")
        self.assertIn("gadget_driver_assigned=no",r.stdout)
        self.assertIn("udc_state=not attached",r.stdout)

    def test_disallow_unknown_label(self):
        r=self.run_fixture(label="bootloader")
        self.assertEqual(r.returncode,2)
        self.assertNotIn("PRIVATE",r.stdout)

    def test_posix_shell_syntax(self):
        result=subprocess.run(["sh","-n",str(SCRIPT)],
                              capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_read_only_shell_contract(self):
        code="\n".join(line for line in SCRIPT.read_text(encoding="utf-8").splitlines()
                       if line.strip() and not line.lstrip().startswith("#"))
        for forbidden in (
            "mount ", "insmod ", "modprobe ", "devmem ", "setprop ",
            "fastboot ", "adb ", "dmesg ", "/proc/cmdline",
            "/config/usb_gadget", "echo configured >", "echo device >",
            "> /sys", ">/sys", "/sys/kernel/debug",
        ):
            self.assertNotIn(forbidden,code)


if __name__ == "__main__":
    unittest.main()
