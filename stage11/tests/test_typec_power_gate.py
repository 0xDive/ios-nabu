"""Host-only synthetic nabu PM8150B Type-C / USB2 PHY dependency checks."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "stage11" / "tools"))
sys.path.insert(0, str(ROOT / "stage9" / "tests"))
sys.path.insert(0, str(ROOT / "stage4" / "tools"))
from dtb_inspect import Node
from test_usb_dtb_gate import fixture as usb_fixture, words
from typec_power_gate import analyze, validate_board, SUPPLIES


def node(name, props=None, children=None):
    return Node(name, children=list(children or []), props=dict(props or {}))


def fake_board():
    root = usb_fixture()
    soc = root.children[0]
    w1, w2, hs, ss = soc.children[:4]
    w1.props["qcom,select-utmi-as-pipe-clk"] = b""
    providers = {}
    for idx, (key, uv) in enumerate(SUPPLIES.items()):
        phandle = 0x300 + idx
        supply = node(f"ldo{idx+1}", {
            "phandle": words(phandle),
            "regulator-min-microvolt": words(uv),
            "regulator-max-microvolt": words(uv),
        })
        providers[key] = phandle
        soc.children.append(supply)
        hs.props[key] = words(phandle)

    usb_ep = node("endpoint", {
        "phandle": words(0x451),
        "remote-endpoint": words(0x452),
    })
    dwc = w1.children[0]
    dwc.children.append(node("ports", children=[
        node("port@0", children=[usb_ep])
    ]))
    pm_ep = node("endpoint", {
        "phandle": words(0x452),
        "remote-endpoint": words(0x451),
    })
    connector = node("connector", {
        "compatible": b"usb-c-connector\0",
        "power-role": b"dual\0",
        "data-role": b"dual\0",
    }, [node("ports", children=[
        node("port@0", children=[pm_ep])
    ])])
    typec = node("typec@1500", {
        "compatible": b"qcom,pm8150b-typec\0",
        "status": b"okay\0",
        "vdd-pdphy-supply": words(providers["vdda33-supply"]),
    }, [connector])
    vbus = node("usb-vbus-regulator@1100", {
        "compatible": b"qcom,pm8150b-vbus-reg\0",
        "status": b"okay\0",
    })
    soc.children.append(node("pmic@2", {
        "compatible": b"qcom,pm8150b\0qcom,spmi-pmic\0",
        "status": b"okay\0",
    }, [vbus, typec]))
    # Public SM8150 Linux DTS supplies Qualcomm GCC and RPMh phandle
    # references. Validate topology, never assume their clocks are on.
    gcc_handle = 0x501
    rpmh_handle = 0x502
    gcc = node("clock-controller@100000", {
        "compatible": b"qcom,sm8150-gcc\0",
        "phandle": words(gcc_handle),
        "#clock-cells": words(1),
        "#reset-cells": words(1),
        "#power-domain-cells": words(1),
    })
    rpmh = node("clock-controller@rpmh", {
        "phandle": words(rpmh_handle),
        "#clock-cells": words(1),
    })
    soc.children.insert(-1, gcc)
    soc.children.insert(-1, rpmh)
    w1.props["clock-names"] = (
        b"cfg_noc\0core\0iface\0sleep\0mock_utmi\0xo\0"
    )
    w1.props["clocks"] = words(
        gcc_handle, 1, gcc_handle, 2, gcc_handle, 3,
        gcc_handle, 4, gcc_handle, 5, gcc_handle, 6,
    )
    w1.props["resets"] = words(gcc_handle, 100)
    w1.props["power-domains"] = words(gcc_handle, 200)
    w1.props["assigned-clocks"] = words(gcc_handle, 5, gcc_handle, 2)
    w1.props["assigned-clock-rates"] = words(19_200_000, 200_000_000)
    hs.props["clock-names"] = b"ref\0"
    hs.props["clocks"] = words(rpmh_handle, 1)
    hs.props["resets"] = words(gcc_handle, 300)
    return root


CONFIG = """CONFIG_DM_REGULATOR_QCOM_RPMH=y
# CONFIG_DM_REGULATOR_QCOM_USB_VBUS is not set
# CONFIG_TYPEC_TCPM is not set
# CONFIG_TYPEC_FUSB302 is not set
"""

MAKE = "obj-$(CONFIG_TYPEC_TCPM) += tcpm.o tcpm-uclass.o\nobj-$(CONFIG_TYPEC_FUSB302) += fusb302.o\n"
TYPEC_SRC = """
static const struct udevice_id fusb302_ids[] = {
    {.compatible = "fcs,fusb302" },
};
"""
VBUS_SRC = """
static const struct udevice_id qcom_usb_vbus_regulator_ids[] = {
    {.compatible = "qcom,pm8150b-vbus-reg" },
};
static int qcom_usb_vbus_regulator_probe() { pmic_clrsetbits(0); }
"""
HS_PHY_SRC = """
static int qcom_snps_hsphy_usb_init() { writel_relaxed(reg, base + offset); }
static int qcom_snps_hsphy_phy_probe() { reset_assert_bulk(&priv->resets); }
"""


class TypecPowerTests(unittest.TestCase):
    def scan(self, root=None, config=CONFIG, make=MAKE,
             tcpm=TYPEC_SRC, vbus=VBUS_SRC, phy=HS_PHY_SRC):
        return analyze(root or fake_board(), config, make, tcpm, vbus, phy)

    def test_public_pm8150b_graph_and_unresolved_uboot_driver(self):
        result = self.scan()
        self.assertEqual(result["device"], "xiaomi,nabu")
        self.assertTrue(result["dtb"]["usb1_hs_to_pm8150b_role_graph_reciprocal"])
        self.assertTrue(result["dtb"]["pm8150b_pdphy_shares_usb1_phy_3v072_supply"])
        self.assertEqual(len(result["dtb"]["usb1_phy_supply_constraints"]), 3)
        self.assertFalse(result["uboot"]["typec_pm8150b_driver_match_in_inspected_source"])
        self.assertTrue(result["uboot"]["pm8150b_vbus_regulator_driver_source_present"])
        self.assertFalse(result["uboot"]["hs_phy_driver_explicit_regulator_lookup"])
        self.assertFalse(result["safe_to_boot"])
        self.assertEqual(result["decision"], "blocked-until-runtime-evidence")

    def test_typec_parent_disabled_fails_closed(self):
        root = fake_board()
        root.children[0].children[-1].props["status"] = b"disabled\0"
        with self.assertRaisesRegex(ValueError, "node or ancestor is disabled"):
            self.scan(root)

    def test_vbus_regulator_disabled_fails_closed(self):
        root = fake_board()
        root.children[0].children[-1].children[0].props["status"] = b"disabled\0"
        with self.assertRaisesRegex(ValueError, "vbus-reg"):
            self.scan(root)

    def test_connector_must_support_dual_data_role(self):
        root = fake_board()
        connector = root.children[0].children[-1].children[1].children[0]
        connector.props["data-role"] = b"host\0"
        with self.assertRaisesRegex(ValueError, "dual data-role"):
            self.scan(root)

    def test_typec_rail_must_match_primary_phy_3v072(self):
        root = fake_board()
        typec = root.children[0].children[-1].children[1]
        typec.props["vdd-pdphy-supply"] = words(0x300)
        with self.assertRaisesRegex(ValueError, "expected L2 rail"):
            self.scan(root)

    def test_missing_hs_phy_regulator_fails(self):
        root = fake_board()
        root.children[0].children[2].props.pop("vdda18-supply")
        with self.assertRaisesRegex(ValueError, "vdda18-supply"):
            self.scan(root)

    def test_wrong_supply_voltage_fails(self):
        root = fake_board()
        root.children[0].children[4].props["regulator-max-microvolt"] = words(400_000)
        with self.assertRaisesRegex(ValueError, "expected voltage"):
            self.scan(root)

    def test_unknown_supply_phandle_fails(self):
        root = fake_board()
        root.children[0].children[2].props["vdda33-supply"] = words(0x999)
        with self.assertRaisesRegex(ValueError, "Unresolved supply"):
            self.scan(root)

    def test_reciprocal_typec_graph_required(self):
        root = fake_board()
        typec_ep = root.children[0].children[-1].children[1].children[0].children[0].children[0].children[0]
        typec_ep.props["remote-endpoint"] = words(0x999)
        with self.assertRaisesRegex(ValueError, "not bidirectional"):
            self.scan(root)

    def test_missing_usb_role_graph_rejected(self):
        root = fake_board()
        root.children[0].children[0].children[0].children.clear()
        with self.assertRaisesRegex(ValueError, "endpoint missing"):
            self.scan(root)

    def test_missing_vbus_source_driver_rejected(self):
        with self.assertRaisesRegex(ValueError, "PM8150B VBUS"):
            self.scan(vbus=VBUS_SRC.replace('"qcom,pm8150b-vbus-reg"',
                                            '"qcom,pm8550b-vbus-reg"'))

    def test_physical_writes_cannot_be_mistaken_for_safe_boot(self):
        result = self.scan()
        self.assertTrue(result["uboot"]["pm8150b_vbus_driver_writes_spmi"])
        self.assertTrue(result["uboot"]["hs_phy_reset_and_mmio_writes_require_review"])
        self.assertFalse(result["safe_to_boot"])
        self.assertFalse(result["abl_usb1_enumeration_proven"])

    def test_malformed_typec_endpoint_phandle_rejected(self):
        root = fake_board()
        ep = root.children[0].children[-1].children[1].children[0].children[0].children[0].children[0]
        ep.props["remote-endpoint"] = b"\x01"
        with self.assertRaisesRegex(ValueError, "single 32-bit"):
            self.scan(root)

    def test_duplicated_phandle_rejected(self):
        root = fake_board()
        root.children[0].children[4].props["phandle"] = words(0x301)
        with self.assertRaisesRegex(ValueError, "Duplicate FDT phandle"):
            self.scan(root)

    def test_detect_new_driver_without_claiming_boot_safety(self):
        change = TYPEC_SRC + '\n{.compatible = "qcom,pm8150b-typec" },\n'
        result = self.scan(tcpm=change)
        self.assertTrue(result["uboot"]["typec_pm8150b_driver_match_in_inspected_source"])
        self.assertFalse(result["safe_to_boot"])

    def test_qualcomm_clocks_and_reset_phandles_are_decoded(self):
        result = self.scan()
        status = result["dtb"]["clock_reset"]
        self.assertEqual(status["usb1_wrapper_clocks_declared"], 6)
        self.assertEqual(status["usb1_wrapper_resets_declared"], 1)
        self.assertEqual(status["usb1_wrapper_power_domains_declared"], 1)
        self.assertEqual(status["usb1_phy_reference_clocks_declared"], 1)
        self.assertEqual(status["usb1_phy_resets_declared"], 1)
        self.assertTrue(status["usb1_declared_19m2_and_200m_clock_rates"])
        self.assertFalse(status["actual_clock_reset_and_power_state_verified"])

    def test_usb1_missing_clock_dependency_rejected(self):
        root = fake_board()
        root.children[0].children[0].props["clocks"] = words(0x501, 1)
        with self.assertRaisesRegex(ValueError, "dependencies"):
            self.scan(root)

    def test_usb1_unresolved_reset_provider_rejected(self):
        root = fake_board()
        root.children[0].children[0].props["resets"] = words(0x999, 100)
        with self.assertRaisesRegex(ValueError, "Unresolved resets"):
            self.scan(root)

    def test_usb1_hsphy_ref_clock_missing_rejected(self):
        root = fake_board()
        root.children[0].children[2].props.pop("clocks")
        with self.assertRaisesRegex(ValueError, "ref clock|Absent/truncated"):
            self.scan(root)

    def test_bad_assigned_clock_rates_rejected(self):
        root = fake_board()
        root.children[0].children[0].props["assigned-clock-rates"] = words(0,0)
        with self.assertRaisesRegex(ValueError, "assigned-clock-rates"):
            self.scan(root)

    def test_disabled_usb1_clock_provider_rejected(self):
        root = fake_board()
        gcc = root.children[0].children[-3]
        gcc.props["status"] = b"disabled\0"
        with self.assertRaisesRegex(ValueError, "Disabled clocks"):
            self.scan(root)

        def test_does_not_publish_sensitive_dtb_properties(self):
        root = fake_board()
        root.props["serial-number"] = b"PRIVATE_SOC_SERIAL"
        result = self.scan(root)
        self.assertNotIn("PRIVATE_SOC_SERIAL",str(result))
        self.assertNotIn("serial-number",str(result))


if __name__ == "__main__":
    unittest.main()
