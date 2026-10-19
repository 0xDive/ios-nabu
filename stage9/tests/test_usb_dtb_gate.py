"""Host-only Qualcomm nabu USB DTB graph tests; no personal data or device I/O."""
from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "stage9" / "tools"))
from dtb_inspect import Node
from usb_dtb_gate import inspect, compare, USB1, USB2, USB1_WRAPPER


def words(*nums):
    return struct.pack(">" + "I" * len(nums), *nums)


def N(name, *, children=None, props=None):
    return Node(name, children=list(children or []), props=dict(props or {}))


def fixture():
    usb1 = N("usb@a600000", props={
        "compatible":b"snps,dwc3\0",
        "reg":words(0,USB1,0,0xcd00),
        "dr_mode":b"otg\0",
        "maximum-speed":b"high-speed\0",
        "phy-names":b"usb2-phy\0",
        "phys":words(0x123),
        "usb-role-switch":b"",
    })
    usb2 = N("usb@a800000", props={
        "compatible":b"snps,dwc3\0",
        "reg":words(0,USB2,0,0xcd00),
        "dr_mode":b"host\0",
        "maximum-speed":b"high-speed\0",
        "phy-names":b"usb2-phy\0",
    })
    phy_hs = N("phy@88e2000", props={
        "compatible":b"qcom,sm8150-usb-hs-phy\0",
        "reg":words(0,0x88e2000,0,0x400),
        "status":b"okay\0",
        "phandle":words(0x123),
        "#phy-cells":words(0),
    })
    phy_ss = N("phy@88e8000", props={
        "compatible":b"qcom,sm8150-qmp-usb3-dp-phy\0",
        "reg":words(0,0x88e8000,0,0x3000),
        "status":b"disabled\0",
    })
    w1 = N("usb@a6f8800", props={
        "compatible":b"qcom,sm8150-dwc3\0qcom,dwc3\0",
        "reg":words(0,USB1_WRAPPER,0,0x400),
        "#address-cells":words(2),"#size-cells":words(2),
        "status":b"okay\0",
    }, children=[usb1])
    w2 = N("usb@a8f8800", props={
        "compatible":b"qcom,sm8150-dwc3\0qcom,dwc3\0",
        "reg":words(0,0xa8f8800,0,0x400),
        "#address-cells":words(2),"#size-cells":words(2),
        "status":b"okay\0",
    }, children=[usb2])
    soc = N("soc@0", props={
        "#address-cells":words(2),"#size-cells":words(2),
        "compatible":b"simple-bus\0",
    }, children=[w1,w2,phy_hs,phy_ss])
    root = N("", props={
        "model":b"Xiaomi Pad 5\0",
        "compatible":b"xiaomi,nabu\0qcom,sm8150\0",
        "#address-cells":words(2),"#size-cells":words(2),
        "serial-number":b"PRIVATE_SERIAL_NEVER_EXPORTED\0",
    }, children=[soc])
    return root


def usb1_node(root):
    return root.children[0].children[0].children[0]


def usb2_node(root):
    return root.children[0].children[1].children[0]


class USBDTBGateTests(unittest.TestCase):
    def test_valid_public_board(self):
        result = inspect(fixture(), require_public_contract=True)
        self.assertTrue(result["passes_compiled_dtb_contract"])
        self.assertEqual(result["usb1"]["controller_base"],hex(USB1))
        self.assertEqual(result["usb1"]["wrapper_base"],hex(USB1_WRAPPER))
        self.assertEqual(result["usb1"]["role"],"otg")
        self.assertEqual(result["usb1"]["maximum_speed"],"high-speed")
        self.assertEqual(result["usb1"]["phy_names"],["usb2-phy"])
        self.assertTrue(result["usb1"]["usb2_hsphy_active"])
        self.assertFalse(result["usb1"]["super_speed_phy_active"])
        self.assertEqual(result["usb2"]["role"],"host")
        self.assertFalse(result["safe_to_boot"])
        self.assertFalse(result["actual_usb_logging_proven"])

    def test_mtp_peripheral_mode_rejected(self):
        root=fixture()
        usb1_node(root).props["dr_mode"]=b"peripheral\0"
        with self.assertRaisesRegex(ValueError,"OTG"):
            inspect(root,require_public_contract=True)

    def test_usb1_wrong_speed_rejected(self):
        root=fixture()
        usb1_node(root).props["maximum-speed"]=b"super-speed\0"
        with self.assertRaisesRegex(ValueError,"USB2 high-speed"):
            inspect(root,require_public_contract=True)

    def test_usb1_qmp_phy_rejected(self):
        root=fixture()
        usb1_node(root).props["phy-names"]=b"usb2-phy\0usb3-phy\0"
        with self.assertRaisesRegex(ValueError,"SuperSpeed"):
            inspect(root,require_public_contract=True)

    def test_missing_role_switch_rejected(self):
        root=fixture()
        usb1_node(root).props.pop("usb-role-switch")
        with self.assertRaisesRegex(ValueError,"role switch"):
            inspect(root,require_public_contract=True)

    def test_wrong_phy_handle_rejected(self):
        root=fixture()
        usb1_node(root).props["phys"]=words(0x999)
        with self.assertRaisesRegex(ValueError,"primary HS PHY"):
            inspect(root,require_public_contract=True)

    def test_disabled_hsphy_rejected(self):
        root=fixture()
        root.children[0].children[2].props["status"]=b"disabled\0"
        with self.assertRaisesRegex(ValueError,"HS PHY missing or disabled"):
            inspect(root,require_public_contract=True)

    def test_enabled_ssphy_rejected(self):
        root=fixture()
        root.children[0].children[3].props["status"]=b"okay\0"
        with self.assertRaisesRegex(ValueError,"SuperSpeed PHY must not"):
            inspect(root,require_public_contract=True)

    def test_disabled_wrapper_rejected(self):
        root=fixture()
        root.children[0].children[0].props["status"]=b"disabled\0"
        with self.assertRaisesRegex(ValueError,"wrapper/child"):
            inspect(root,require_public_contract=True)

    def test_usb2_cannot_be_gadget(self):
        root=fixture()
        usb2_node(root).props["dr_mode"]=b"peripheral\0"
        with self.assertRaisesRegex(ValueError,"host-only"):
            inspect(root,require_public_contract=True)

    def test_truncated_registers_rejected(self):
        root=fixture()
        usb1_node(root).props["reg"]=words(0,USB1)
        with self.assertRaisesRegex(ValueError,"Truncated"):
            inspect(root,require_public_contract=True)

    def test_no_sensitive_vendor_properties_exported(self):
        report=inspect(fixture(),require_public_contract=True)
        self.assertNotIn("PRIVATE_SERIAL",str(report))
        self.assertNotIn("serial-number",str(report))

    def test_android_vendor_report_does_not_claim_boot_support(self):
        root=fixture()
        usb2_node(root).props["maximum-speed"]=b"super-speed-plus\0"
        usb1_node(root).props.pop("phys")
        usb1_node(root).props.pop("phy-names")
        usb1_node(root).props.pop("usb-role-switch")
        vendor=inspect(root,require_public_contract=False)
        compiled=inspect(fixture(),require_public_contract=True)
        diff=compare(compiled,vendor)
        self.assertFalse(vendor["passes_compiled_dtb_contract"])
        self.assertFalse(diff["safe_to_boot"])
        self.assertFalse(diff["source_fdt_same_as_abl"])
        self.assertIn("maximum_speed", [x["property"] for x in diff["differences"]])
        self.assertIn("role_switch_declared", [x["property"] for x in diff["differences"]])

    def test_wrong_board_rejected(self):
        root=fixture()
        root.props["compatible"]=b"qcom,sm8150-mtp\0qcom,sm8150\0"
        root.props["model"]=b"SM8150 MTP\0"
        with self.assertRaisesRegex(ValueError,"not a nabu"):
            inspect(root,require_public_contract=True)


if __name__=="__main__":
    unittest.main()
