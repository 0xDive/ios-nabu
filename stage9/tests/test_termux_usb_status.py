"""Synthetic read-only USB observation tests; no device or vendor dump accessed."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "termux_usb_status.sh"


class USBStatusTests(unittest.TestCase):
    def fake(self, *, udc=True, typec=True, unsafe_scalar=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            devdir = root / "sys/bus/platform/devices"
            devdir.mkdir(parents=True)
            usbdev=devdir / "a600000.dwc3"
            usbdev.mkdir()
            drivers = root / "sys/bus/platform/drivers/dwc3"
            drivers.mkdir(parents=True)
            (usbdev/"driver").symlink_to(drivers)
            soc_node = root / "sys/firmware/devicetree/base/soc/ssusb@a600000"
            soc_node.mkdir(parents=True)
            (usbdev/"of_node").symlink_to(soc_node)
            # This is intentionally irrelevant and MUST NOT be exported.
            (soc_node/"serial-number").write_text("SECRET-PRIVATE-GADGET-SERIAL")
            if udc:
                n=root/"sys/class/udc/a600000.dwc3"
                n.mkdir(parents=True)
                for key,val in {
                    "state":"configured",
                    "current_speed":"high-speed",
                    "maximum_speed":"high-speed",
                    "is_otg":"1",
                    "secret":"SHOULD_NOT_LEAK",
                }.items():
                    (n/key).write_text(val+"\n")
            if typec:
                n=root/"sys/class/typec/port0"
                n.mkdir(parents=True)
                for key,val in {
                    "data_role":"device",
                    "power_role":"sink",
                    "port_type":"dual",
                    "serial_number":"PRIVATE_NUMBER",
                }.items():
                    (n/key).write_text(val+"\n")
                if unsafe_scalar:
                    (n/"data_role").write_text("PRIVATE_SERIAL=SECRET&DEVICE\n")
            return subprocess.run(["sh",str(SCRIPT)],env={**os.environ,
                     "NABU_SYSROOT":str(root)},text=True,
                     capture_output=True,check=False,timeout=12)

    def test_reads_android_udc_and_typec_only(self):
        r=self.fake()
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn("platform=a600000.dwc3",r.stdout)
        self.assertIn("udc=a600000.dwc3",r.stdout)
        self.assertIn("state=configured",r.stdout)
        self.assertIn("current_speed=high-speed",r.stdout)
        self.assertIn("maximum_speed=high-speed",r.stdout)
        self.assertIn("typec_port=port0",r.stdout)
        self.assertIn("data_role=device",r.stdout)
        self.assertIn("power_role=sink",r.stdout)
        self.assertIn("source=running-Android-not-ABL",r.stdout)
        self.assertIn("configured-U-Boot-USB-gadget-proven=no",r.stdout)
        self.assertIn("device-changes=no",r.stdout)

    def test_missing_udc_is_not_claimed_broken(self):
        r=self.fake(udc=False,typec=False)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn("udc=none-or-not-readable",r.stdout)
        self.assertIn("typec=none-or-not-readable",r.stdout)

    def test_does_not_print_sensitive_properties(self):
        r=self.fake(unsafe_scalar=True)
        self.assertNotIn("SECRET",r.stdout)
        self.assertNotIn("PRIVATE",r.stdout)
        self.assertNotIn("serial-number",r.stdout)
        self.assertIn("data_role=unavailable",r.stdout)

    def test_shell_validity(self):
        result=subprocess.run(["sh","-n",str(SCRIPT)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_no_write_or_gadget_reconfiguration(self):
        code="\n".join(line for line in SCRIPT.read_text(encoding="utf-8").splitlines()
                       if line.strip() and not line.lstrip().startswith("#"))
        for forbidden in ("echo gadget >","mount -t", "devmem",
                          "setprop ", "fastboot ", "insmod ", "modprobe ",
                          "/proc/cmdline", "dmesg ", "driver_override",
                          "> /sys", ">/sys","configfs/usb_gadget"):
            self.assertNotIn(forbidden,code)


if __name__=="__main__":
    unittest.main()
