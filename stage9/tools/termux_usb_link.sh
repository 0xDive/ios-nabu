#!/system/bin/sh
# Stage 9.2: read-only USB link snapshot for Xiaomi Pad 5 / nabu.
# Run once disconnected and once with a known data-capable USB cable to PC.
# NEVER writes to sysfs/configfs, toggles roles, resets USB or reads USB IDs.
# The two snapshots reflect *running Android*, NOT ABL/U-Boot/XNU.
# NABU_SYSROOT is for synthetic CI testing only; unset on the real tablet.
ROOT="${NABU_SYSROOT:-}"
LABEL="${1:-unspecified}"
case "$LABEL" in
    disconnected|connected|unspecified) ;;
    *) printf '%s\n' 'ERROR: label must be disconnected or connected' >&2; exit 2 ;;
esac
UDC="$ROOT/sys/class/udc/a600000.dwc3"

# Strict allowlists prevent leaking arbitrary sysfs contents into reports.
read_state() {
    if [ ! -r "$1" ]; then printf '%s\n' unavailable; return; fi
    VALUE=
    IFS= read -r VALUE < "$1" || :
    case "$VALUE" in
        "not attached"|not-attached|attached|powered|reconnecting|unauthenticated|default|addressed|configured|suspended)
            printf '%s\n' "$VALUE" ;;
        *) printf '%s\n' unavailable ;;
    esac
}
read_speed() {
    if [ ! -r "$1" ]; then printf '%s\n' unavailable; return; fi
    VALUE=
    IFS= read -r VALUE < "$1" || :
    case "$VALUE" in
        UNKNOWN|unknown|low-speed|full-speed|high-speed|super-speed|super-speed-plus)
            printf '%s\n' "$VALUE" ;;
        *) printf '%s\n' unavailable ;;
    esac
}
read_bool() {
    if [ ! -r "$1" ]; then printf '%s\n' unavailable; return; fi
    VALUE=
    IFS= read -r VALUE < "$1" || :
    case "$VALUE" in
        0|1) printf '%s\n' "$VALUE" ;;
        *) printf '%s\n' unavailable ;;
    esac
}
read_role() {
    if [ ! -r "$1" ]; then printf '%s\n' unavailable; return; fi
    VALUE=
    IFS= read -r VALUE < "$1" || :
    case "$VALUE" in
        none|host|device|unknown|dual|source|sink) printf '%s\n' "$VALUE" ;;
        *) printf '%s\n' unavailable ;;
    esac
}
read_function_bound() {
    if [ ! -r "$1" ]; then printf '%s\n' unavailable; return; fi
    VALUE=
    IFS= read -r VALUE < "$1" || :
    # Never print the raw gadget driver name or serial information.
    if [ -z "$VALUE" ] || [ "$VALUE" = none ]; then
        printf '%s\n' no
    else
        printf '%s\n' yes
    fi
}
printf '%s\n' '=== NABU USB LINK SNAPSHOT / RUNNING ANDROID ==='
printf 'label=%s\n' "$LABEL"
if [ -d "$UDC" ] || [ -L "$UDC" ]; then
    printf '%s\n' 'udc=a600000.dwc3'
    printf 'udc_state='
    read_state "$UDC/state"
    printf 'current_speed='
    read_speed "$UDC/current_speed"
    printf 'maximum_speed='
    read_speed "$UDC/maximum_speed"
    printf 'otg_capable='
    read_bool "$UDC/is_otg"
    printf 'gadget_driver_assigned='
    read_function_bound "$UDC/function"
else
    printf '%s\n' 'udc=unavailable'
fi

# USB power online is independent of gadget enumeration and may be missing.
printf 'android_usb_power_online='
read_bool "$ROOT/sys/class/power_supply/usb/online"

# The upstream Type-C class may not exist in this downstream vendor kernel.
# Check USB role-switch sysfs as a separate, optional signal.
ROLES=0
for SYS_ROLE in "$ROOT/sys/class/usb_role/"*; do
    [ -d "$SYS_ROLE" ] || [ -L "$SYS_ROLE" ] || continue
    ROLES=$((ROLES+1))
    [ "$ROLES" -le 4 ] || break
    printf 'usb_role_%s=' "$ROLES"
    read_role "$SYS_ROLE/role"
done
[ "$ROLES" -gt 0 ] || printf '%s\n' 'usb_role_sysfs=unavailable'

printf '%s\n' 'source=running-Android-not-ABL'
printf '%s\n' 'bootloader_usb_gadget_tested=no'
printf '%s\n' 'xnu_usb_logging_tested=no'
printf '%s\n' 'device_settings_changed=no'
printf '%s\n' '=== END ==='
