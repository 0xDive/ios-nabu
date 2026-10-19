"""Synthetic source-contract tests for the public nabu DTS staging process."""
import pathlib
import sys
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"tools"))
from inspect_nabu_source import inspect


def fixture():
    return """/* """ + "nabu source-only fixture " * 33 + """ */
#include "sm8150.dtsi"
#include "sm8150-wcd9340.dtsi"
/ {
    model = "Xiaomi Pad 5";
    compatible = "xiaomi,nabu", "qcom,sm8150";
};
&usb_1 {
    status = "okay";
};
&usb_1_dwc3 {
    dr_mode = "otg";
    maximum-speed = "high-speed";
    phys = <&usb_1_hsphy>;
    usb-role-switch;
};
&usb_2_dwc3 {
    dr_mode = "host";
};
"""


class SourceContractTests(unittest.TestCase):
    def test_expected_public_nabu_dts(self):
        s=inspect(fixture())
        self.assertEqual(s["target_board"],"xiaomi,nabu")
        self.assertEqual(s["usb1_role_from_linux_dts"],"otg")
        self.assertEqual(s["usb2_role_from_linux_dts"],"host")
        self.assertFalse(s["bootable_artifact_produced"])
        self.assertFalse(s["bootloader_time_usb_init_verified"])

    def test_other_board_rejected(self):
        bad=fixture().replace('"xiaomi,nabu"','"qcom,sm8150-mtp"')
        with self.assertRaisesRegex(ValueError,"Pad 5"):
            inspect(bad)

    def test_sm8150_mtp_peripheral_mode_rejected(self):
        with self.assertRaisesRegex(ValueError,"OTG"):
            inspect(fixture().replace('dr_mode = "otg";','dr_mode = "peripheral";'))

    def test_usb3_phy_is_not_nabu_usb2(self):
        with self.assertRaisesRegex(ValueError,"HS PHY"):
            inspect(fixture().replace('phys = <&usb_1_hsphy>;',
                                      'phys = <&usb_1_hsphy>, <&usb_1_qmpphy>;'))

    def test_second_usb_must_not_act_as_device(self):
        with self.assertRaisesRegex(ValueError,"host-only"):
            inspect(fixture().replace('dr_mode = "host";','dr_mode = "peripheral";'))

    def test_missing_linux_audio_include_catches_incomplete_staging(self):
        with self.assertRaisesRegex(ValueError,"audio"):
            inspect(fixture().replace('#include "sm8150-wcd9340.dtsi"',''))

    def test_truncated_dts_rejected(self):
        with self.assertRaisesRegex(ValueError,"size"):
            inspect("x")


if __name__=="__main__":
    unittest.main()
