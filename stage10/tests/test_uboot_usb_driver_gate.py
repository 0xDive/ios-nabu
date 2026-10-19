"""Pure-host, synthetic Stage 10 U-Boot USB source/Kconfig/DTB regression tests."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "stage10" / "tools"))
sys.path.insert(0, str(ROOT / "stage9" / "tests"))
sys.path.insert(0, str(ROOT / "stage4" / "tools"))
from test_usb_dtb_gate import fixture
from uboot_usb_driver_gate import analyze, config_values, REQUIRED_KCONFIG, DANGEROUS_KCONFIG


def dtb_fixture():
    root = fixture()
    root.children[0].children[0].props["qcom,select-utmi-as-pipe-clk"] = b""
    return root


def kconfig():
    return ("\n".join(
        [key + "=y" for key in REQUIRED_KCONFIG] +
        ["# " + key + " is not set" for key in DANGEROUS_KCONFIG]
    ) + "\n")


GENERIC = """
static int dwc3_glue_bind_common(int dr_mode) {
    if (CONFIG_IS_ENABLED(DM_USB_GADGET) &&
        (dr_mode == USB_DR_MODE_PERIPHERAL || dr_mode == USB_DR_MODE_OTG)) {
       driver = "dwc3-generic-peripheral";
    }
}
static const struct udevice_id dwc3_glue_ids[] = {
    { .compatible = "qcom,dwc3", .data = (ulong)&qcom_ops },
};
static void dwc3_qcom_glue_configure(void *qscratch_base) {
    if (dev_read_bool(dev, "qcom,select-utmi-as-pipe-clk"))
        dwc3_qcom_select_utmi_clk(qscratch_base);
    dwc3_qcom_vbus_override_enable(qscratch_base, true);
    setbits_le32(qscratch_base, 1);
    writel(42, qscratch_base);
}
"""

PHY = """
static const struct udevice_id qcom_snps_hsphy_phy_ids[] = {
    { .compatible = "qcom,sm8150-usb-hs-phy" },
};
static void qcom_snps_hsphy_usb_init() {
    writel_relaxed(reg, base + offset);
}
static void qcom_snps_hsphy_phy_probe() {
    reset_assert_bulk(&priv->resets);
}
"""


class UBootUsbDriverTests(unittest.TestCase):
    def test_compiled_source_contract_succeeds_but_never_authorizes_boot(self):
        report=analyze(dtb_fixture(), kconfig(), GENERIC, PHY)
        self.assertTrue(report["board_dtb_graph_passed"])
        self.assertTrue(report["usb_1_gadget_driver_compilation_plausible"])
        self.assertFalse(report["safe_to_boot"])
        self.assertIsNone(report["boot_time_typec_controller_supported"])
        self.assertFalse(report["real_usb_enumeration_in_uboot"])
        self.assertFalse(report["xnu_debug_messages_over_usb"])

    def test_missing_driver_model_gadget_rejected(self):
        bad=kconfig().replace("CONFIG_DM_USB_GADGET=y",
                              "# CONFIG_DM_USB_GADGET is not set")
        with self.assertRaisesRegex(ValueError,"CONFIG_DM_USB_GADGET"):
            analyze(dtb_fixture(),bad,GENERIC,PHY)

    def test_missing_hsphy_driver_rejected(self):
        bad=kconfig().replace("CONFIG_PHY_QCOM_USB_SNPS_FEMTO_V2=y",
                              "# CONFIG_PHY_QCOM_USB_SNPS_FEMTO_V2 is not set")
        with self.assertRaisesRegex(ValueError,"CONFIG_PHY_QCOM_USB_SNPS_FEMTO_V2"):
            analyze(dtb_fixture(),bad,GENERIC,PHY)

    def test_missing_dwc3_gadget_rejected(self):
        bad=kconfig().replace("CONFIG_USB_DWC3_GADGET=y",
                              "# CONFIG_USB_DWC3_GADGET is not set")
        with self.assertRaisesRegex(ValueError,"CONFIG_USB_DWC3_GADGET"):
            analyze(dtb_fixture(),bad,GENERIC,PHY)

    def test_flashing_rejected(self):
        bad=kconfig().replace("# CONFIG_FASTBOOT_FLASH is not set",
                              "CONFIG_FASTBOOT_FLASH=y")
        with self.assertRaisesRegex(ValueError,"CONFIG_FASTBOOT_FLASH"):
            analyze(dtb_fixture(),bad,GENERIC,PHY)

    def test_missing_qcom_wrapper_fallback_rejected(self):
        root=dtb_fixture()
        root.children[0].children[0].props["compatible"]=b"qcom,sm8150-dwc3\0"
        with self.assertRaisesRegex(ValueError,"qcom,dwc3 fallback"):
            analyze(root,kconfig(),GENERIC,PHY)

    def test_missing_utmi_select_rejected(self):
        root=dtb_fixture()
        root.children[0].children[0].props.pop("qcom,select-utmi-as-pipe-clk")
        with self.assertRaisesRegex(ValueError,"UTMI-as-PIPE"):
            analyze(root,kconfig(),GENERIC,PHY)

    def test_missing_phy_source_match_rejected(self):
        with self.assertRaisesRegex(ValueError,"sm8150_hsphy_binding"):
            analyze(dtb_fixture(),kconfig(),GENERIC,PHY.replace(
                '"qcom,sm8150-usb-hs-phy"', '"qcom,sdm845-usb-hs-phy"'
            ))

    def test_missing_otg_driver_select_rejected(self):
        with self.assertRaisesRegex(ValueError,"otg_binds_generic_peripheral"):
            analyze(dtb_fixture(),kconfig(),
                    GENERIC.replace('driver = "dwc3-generic-peripheral";',
                                    'driver = "dwc3-generic-host";'),PHY)

    def test_missing_critical_reset_write_review_is_not_accepted(self):
        with self.assertRaisesRegex(ValueError,"hs_phy_init_performs_mmio"):
            analyze(dtb_fixture(),kconfig(),GENERIC,
                    PHY.replace("reset_assert_bulk(&priv->resets);",""))

    def test_duplicate_config_flag_rejected(self):
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            config_values("CONFIG_USB_DWC3=y\nCONFIG_USB_DWC3=y\n")

    def test_sensitive_dtb_serial_is_not_exported(self):
        report=analyze(dtb_fixture(),kconfig(),GENERIC,PHY)
        self.assertNotIn("PRIVATE_SERIAL",str(report))
        self.assertNotIn("serial-number",str(report))


if __name__=="__main__":
    unittest.main()
