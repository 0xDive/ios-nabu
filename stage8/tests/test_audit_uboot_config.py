"""Safe, synthetic Stage 8 U-Boot Kconfig validation."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/"tools"))
from audit_uboot_config import audit, decode, REQUIRED, FORBIDDEN, UBOOT_COMMIT


def valid_config():
    lines = [f"{key}=y" for key in sorted(REQUIRED)]
    lines += [f"# {key} is not set" for key in sorted(FORBIDDEN)]
    lines += [
        'CONFIG_DEFAULT_DEVICE_TREE="qcom/sdm845-db845c"',
        'CONFIG_SYS_LOAD_ADDR=0xa0000000',
        '# This is a host-only reference build',
    ]
    return "\n".join(lines) + "\n"


class AuditTests(unittest.TestCase):
    def test_valid_host_only_config(self):
        report = audit(valid_config())
        self.assertTrue(report["usb_console_gadget_compiled"])
        self.assertTrue(report["u_boot_recorded_console_fastboot_supported"])
        self.assertEqual(report["pinned_commit"], UBOOT_COMMIT)
        self.assertFalse(report["nabu_board_support_verified"])
        self.assertFalse(report["xnu_logging_supported"])
        self.assertFalse(report["device_hardware_tested"])

    def test_reject_missing_usb_serial(self):
        source = valid_config().replace("CONFIG_USB_FUNCTION_ACM=y",
                                         "# CONFIG_USB_FUNCTION_ACM is not set")
        with self.assertRaisesRegex(ValueError, "CONFIG_USB_FUNCTION_ACM"):
            audit(source)

    def test_reject_fastboot_flash(self):
        source = valid_config().replace("# CONFIG_FASTBOOT_FLASH is not set",
                                         "CONFIG_FASTBOOT_FLASH=y")
        with self.assertRaisesRegex(ValueError, "CONFIG_FASTBOOT_FLASH"):
            audit(source)

    def test_reject_arbitrary_oem_run(self):
        source = valid_config().replace("# CONFIG_FASTBOOT_OEM_RUN is not set",
                                         "CONFIG_FASTBOOT_OEM_RUN=y")
        with self.assertRaisesRegex(ValueError, "CONFIG_FASTBOOT_OEM_RUN"):
            audit(source)

    def test_reject_capsule_disk_update(self):
        source = valid_config().replace("# CONFIG_EFI_CAPSULE_ON_DISK is not set",
                                         "CONFIG_EFI_CAPSULE_ON_DISK=y")
        with self.assertRaisesRegex(ValueError, "CONFIG_EFI_CAPSULE_ON_DISK"):
            audit(source)

    def test_reject_missing_log_collection(self):
        source = valid_config().replace("CONFIG_FASTBOOT_CMD_OEM_CONSOLE=y", "")
        with self.assertRaisesRegex(ValueError, "CONFIG_FASTBOOT_CMD_OEM_CONSOLE"):
            audit(source)

    def test_reject_claim_of_device_dt(self):
        source = valid_config().replace('"qcom/sdm845-db845c"',
                                         '"qcom/sm8150-xiaomi-nabu"')
        with self.assertRaisesRegex(ValueError, "not claim"):
            audit(source)

    def test_duplicate_symbol_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            decode("CONFIG_ARM=y\nCONFIG_ARM=y\n")

    def test_malformed_kconfig_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Malformed"):
            decode("CONFIG_ARM=<bad>\n")

    def test_firmware_update_opcodes_not_in_report(self):
        report = audit(valid_config())
        self.assertNotIn("firmware_blob",report)
        self.assertEqual(report["artifact_policy"],
                         "config and compile logs only; no executable U-Boot or boot.img")


if __name__ == "__main__":
    unittest.main()
