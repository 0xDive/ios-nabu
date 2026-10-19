#!/system/bin/sh
# Stage 7.3: Xiaomi Pad 5 root-Termux read-only console-driver hypothesis check.
# No mount, modprobe, insmod, driver bind/override, GPIO or MMIO operations.
# No raw /proc/cmdline, dmesg, device IDs, system properties or file exports.
# A disabled CONFIG_SERIAL_CORE_CONSOLE/CONFIG_CONSOLE_POLL could explain
# why qcom,msm-geni-console at 0xA90000 is not driver-bound in Android.
#
# To test with host-only sysfs fixtures:
#     NABU_SYSROOT=/path/to/fixture sh termux_console_config.sh
ROOT="$NABU_SYSROOT"
DEVICE="$ROOT/sys/bus/platform/devices/a90000.qcom,qup_uart"
DRIVER="$ROOT/sys/bus/platform/drivers/msm_geni_serial"
CONFIG="$ROOT/proc/config.gz"

printf '%s\n' '=== NABU SERIAL CONSOLE CONFIG (READ-ONLY) ==='
printf 'uid='
id -u
printf 'kernel_release='
uname -r

if [ -d "$DEVICE" ]; then
    printf '%s\n' 'console_platform_device=present'
    if [ -L "$DEVICE/driver" ] && [ -e "$DEVICE/driver" ]; then
        printf '%s\n' 'console_driver_binding=confirmed'
    elif [ -L "$DEVICE/driver" ]; then
        printf '%s\n' 'console_driver_binding=broken-symlink'
    else
        printf '%s\n' 'console_driver_binding=none'
    fi
    if [ -r "$DEVICE/uevent" ]; then
        grep -E '^(DRIVER|OF_COMPATIBLE_0)=' "$DEVICE/uevent" 2>/dev/null | head -n 4
    fi
else
    printf '%s\n' 'console_platform_device=absent'
fi

if [ -d "$DRIVER" ]; then
    printf '%s\n' 'hs_uart_driver_directory=present'
else
    printf '%s\n' 'hs_uart_driver_directory=absent'
fi

printf '%s\n' '=== BUILD FLAGS ==='
# Print ONLY these exact feature flags. Full .config contains unrelated
# machine settings and must never be included in a user diagnostic report.
filter_config() {
    grep -E '^(CONFIG_(SERIAL_CORE_CONSOLE|CONSOLE_POLL|SERIAL_MSM_GENI|SERIAL_MSM_GENI_CONSOLE|SERIAL_QCOM_GENI_CONSOLE)=|# CONFIG_(SERIAL_CORE_CONSOLE|CONSOLE_POLL|SERIAL_MSM_GENI|SERIAL_MSM_GENI_CONSOLE|SERIAL_QCOM_GENI_CONSOLE) is not set)'
}

if [ -r "$CONFIG" ]; then
    GOT_FLAGS=0
    # Android's /system/bin/toybox is independent of Termux's possibly broken
    # curl/OpenSSL/gzip shared libraries.
    if [ -z "$ROOT" ] && [ -x /system/bin/toybox ]; then
        FOUND=$(/system/bin/toybox zcat "$CONFIG" 2>/dev/null | filter_config)
        if [ -n "$FOUND" ]; then
            printf '%s\n' "$FOUND"
            GOT_FLAGS=1
        fi
    fi
    if [ "$GOT_FLAGS" -eq 0 ]; then
        FOUND=$(gzip -dc "$CONFIG" 2>/dev/null | filter_config)
        if [ -n "$FOUND" ]; then
            printf '%s\n' "$FOUND"
            GOT_FLAGS=1
        fi
    fi
    [ "$GOT_FLAGS" -eq 1 ] || printf '%s\n' 'kernel_config=unavailable-or-no-matching-flags'
else
    printf '%s\n' 'kernel_config=/proc/config.gz-not-available'
fi

printf '%s\n' '=== NOTES ==='
printf '%s\n' 'console-driver-condition=hypothesis-not-proven'
printf '%s\n' 'kernel-drivers-at-ABL-entry=unknown'
printf '%s\n' 'physical-TX-access=unknown'
printf '%s\n' 'no-hardware-or-system-changes=yes'
printf '%s\n' '=== END ==='
