"""Synthetic, non-private Stage 7 Qualcomm GENI UART DTB topology tests."""
import json
from pathlib import Path
import struct
import sys
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "tools"))
from uart_dtb import inspect, cells
from dtb_inspect import Node


def be32(*parts):
    return struct.pack(">"+"I"*len(parts),*parts)


def N(name, props=None, children=None):
    # dtb_inspect.Node is dataclass(name, children, props); keywords avoid
    # positional field-order confusion.
    return Node(name, children=list(children or []), props=dict(props or {}))


def fake_tree():
    clock = N("clock-controller@100", {
        "phandle": be32(42),
        "#clock-cells": be32(1),
    })
    default = N("qupv3_se12_2uart_active", {
        "phandle": be32(100)
    }, [
        N("mux", {"pins":b"gpio85\0gpio86\0", "function":b"qup12\0"}),
        N("config", {"pins":b"gpio85\0gpio86\0", "drive-strength":be32(2)})
    ])
    sleep = N("qupv3_se12_2uart_sleep", {
        "phandle": be32(101)
    }, [
        N("mux", {"pins":b"gpio85\0gpio86\0", "function":b"gpio\0"})
    ])
    pinctrl = N("pinctrl@3000000", {}, [default,sleep])
    uart = N("qcom,qup_uart@0xa90000", {
        "compatible": b"qcom,msm-geni-console\0",
        "status":b"ok\0",
        "reg":be32(0xA90000,0x4000),
        "interrupts":be32(0,357,0),
        "clock-names":b"se-clk\0m-ahb\0s-ahb\0",
        "clocks":be32(42,0x69,42,0x7B,42,0x7C),
        "pinctrl-names":b"default\0sleep\0",
        "pinctrl-0":be32(100),
        "pinctrl-1":be32(101),
        "serial-number":b"PRIVATE_EXAMPLE_NEVER_EXPORTED",
    })
    soc = N("soc", {"#address-cells":be32(1),"#size-cells":be32(1)},
               [clock,pinctrl,uart])
    chosen = N("chosen", {
        "bootargs": b"PRIVATE_PASSWORD_EXAMPLE",
    })
    return N("", {
        "model":b"NABU\0",
        "compatible":b"qcom,sm8150-cdp\0qcom,sm8150\0",
        "#address-cells":be32(2),"#size-cells":be32(2),
        "serial-number":b"PRIVATE_ROOT_SERIAL"
    },[chosen,soc])


class UartDtbTests(unittest.TestCase):
    def test_real_nabu_console_topology(self):
        report = inspect(fake_tree())
        self.assertTrue(report["candidate_console_found"])
        self.assertFalse(report["stdout_path_declared"])
        self.assertEqual(len(report["controllers"]),1)
        uart = report["controllers"][0]
        self.assertEqual(uart["reg"],[{"base":"0xa90000","size":"0x4000"}])
        self.assertEqual(uart["interrupt"]["gic_intid"],389)
        self.assertEqual(uart["status_in_android_fdt"],"ok")
        self.assertEqual([c["specifier"][0] for c in uart["clocks"]],
                         ["0x69","0x7b","0x7c"])
        self.assertEqual(uart["pinctrl"][0]["targets"][0]["pins"],
                         ["gpio85","gpio86"])
        self.assertEqual(uart["pinctrl"][0]["targets"][0]["functions"],["qup12"])
        self.assertEqual(uart["pinctrl"][1]["targets"][0]["functions"],["gpio"])
        self.assertFalse(uart["driver_equivalence_proven"])
        self.assertIsNone(uart["pins_physically_accessible"])

    def test_no_private_fields_exported(self):
        report = json.dumps(inspect(fake_tree()))
        for secret in ("PRIVATE_EXAMPLE","PRIVATE_ROOT_SERIAL",
                       "PRIVATE_PASSWORD_EXAMPLE","bootargs","serial-number"):
            self.assertNotIn(secret,report)

    def test_missing_clock_provider_rejected(self):
        root = fake_tree()
        root.children[1].children[2].props["clocks"] = be32(999,0x69)
        with self.assertRaisesRegex(ValueError,"clock provider"):
            inspect(root)

    def test_missing_pinctrl_phandle_rejected(self):
        root = fake_tree()
        root.children[1].children[2].props["pinctrl-0"] = be32(999)
        with self.assertRaisesRegex(ValueError,"pinctrl"):
            inspect(root)

    def test_bad_reg_rejected(self):
        root = fake_tree()
        root.children[1].children[2].props["reg"] = be32(0xA90000)
        with self.assertRaisesRegex(ValueError,"reg"):
            inspect(root)

    def test_other_soc_rejected(self):
        root = fake_tree()
        root.props["compatible"] = b"qcom,sm7150\0"
        with self.assertRaisesRegex(ValueError,"SM8150"):
            inspect(root)

    def test_mainline_compatible_is_recognized_but_not_assumed_working(self):
        root = fake_tree()
        root.children[1].children[2].props["compatible"] = b"qcom,geni-debug-uart\0"
        record = inspect(root)["controllers"][0]
        self.assertIn("qcom,geni-debug-uart", record["compatible"])
        self.assertFalse(record["driver_equivalence_proven"])

    def test_invalid_cells_rejected(self):
        with self.assertRaisesRegex(ValueError,"cell"):
            cells(b"\x01\x02\x03")


if __name__ == "__main__":
    unittest.main()
