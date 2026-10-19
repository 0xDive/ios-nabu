#!/system/bin/sh
# Stage 9.1: read-only USB Device Controller / Type-C state on Xiaomi nabu.
# This is Android runtime, NOT the ABL or U-Boot state.
# No sysfs writes, mounts, configfs gadget changes, firmware, bootargs or
# raw logs. Do not print USB serial numbers or gadget identifiers.
#
# Termux: su -c 'sh -s' < termux_usb_status.sh > "$HOME/nabu-usb.txt" 2>&1
# NABU_SYSROOT is for synthetic CI fixtures only. Leave unset on tablet.
ROOT="${NABU_SYSROOT:-}"

safe_scalar() {
    FILE="$1"
    if [ ! -r "$FILE" ]; then
        printf '%s\n' unavailable
        return
    fi
    IFS= read -r VALUE < "$FILE" || :
    case "$VALUE" in
        ""|*[!A-Za-z0-9_\[\]\.\ \-/]*)
            printf '%s\n' unavailable
            ;;
        *)
            # Kernel names and role/status strings are bounded.
            if [ "${#VALUE}" -le 64 ]; then
                printf '%s\n' "$VALUE"
            else
                printf '%s\n' unavailable
            fi
            ;;
    esac
}

printf '%s\n' '=== NABU STAGE 9.1 USB STATUS (ANDROID ONLY) ==='
printf 'uid='
id -u

printf '\n%s\n' '=== SELECTED USB PLATFORM DEVICES ==='
COUNT=0
for DEV in "$ROOT/sys/bus/platform/devices/"*a600000* \
           "$ROOT/sys/bus/platform/devices/"*a6f8800* \
           "$ROOT/sys/bus/platform/devices/"*a800000* \
           "$ROOT/sys/bus/platform/devices/"*a8f8800*
do
    [ -e "$DEV" ] || continue
    BASE="${DEV##*/}"
    case "$BASE" in
        *a600000*|*a6f8800*|*a800000*|*a8f8800*) ;;
        *) continue ;;
    esac
    COUNT=$((COUNT+1))
    [ "$COUNT" -le 16 ] || break
    printf 'platform=%s\n' "$BASE"
    if [ -L "$DEV/driver" ]; then
        printf 'driver_link='
        readlink "$DEV/driver" 2>/dev/null || printf '%s\n' unavailable
    else
        printf '%s\n' 'driver_link=not-bound-or-unavailable'
    fi
    printf 'of_node='
    if [ -L "$DEV/of_node" ]; then
        readlink "$DEV/of_node" 2>/dev/null || printf '%s\n' unavailable
    else
        printf '%s\n' unavailable
    fi
done
[ "$COUNT" -gt 0 ] || printf '%s\n' 'usb_platform_devices=unavailable'

printf '\n%s\n' '=== USB DEVICE CONTROLLERS ==='
FOUND=0
for UDC in "$ROOT/sys/class/udc/"*; do
    [ -e "$UDC" ] || continue
    NAME="${UDC##*/}"
    case "$NAME" in
        *dwc3*|*a600000*|*a800000*|*qcom*)
            FOUND=$((FOUND+1))
            [ "$FOUND" -le 8 ] || break
            printf 'udc=%s\n' "$NAME"
            for PROP in state current_speed maximum_speed is_otg; do
                printf '%s=' "$PROP"
                safe_scalar "$UDC/$PROP"
            done
            ;;
    esac
done
[ "$FOUND" -gt 0 ] || printf '%s\n' 'udc=none-or-not-readable'

printf '\n%s\n' '=== TYPE-C ROLE OBSERVATIONS ==='
TYPEC=0
for PORT in "$ROOT/sys/class/typec/"port[0-9]*; do
    [ -e "$PORT" ] || continue
    BASE="${PORT##*/}"
    case "$BASE" in
        port[0-9]*)
            TYPEC=$((TYPEC+1))
            [ "$TYPEC" -le 8 ] || break
            printf 'typec_port=%s\n' "$BASE"
            for PROP in data_role power_role port_type; do
                printf '%s=' "$PROP"
                safe_scalar "$PORT/$PROP"
            done
            ;;
    esac
done
[ "$TYPEC" -gt 0 ] || printf '%s\n' 'typec=none-or-not-readable'

printf '\n%s\n' '=== SAFETY ==='
printf '%s\n' 'source=running-Android-not-ABL'
printf '%s\n' 'configured-U-Boot-USB-gadget-proven=no'
printf '%s\n' 'xnu-usb-logging-proven=no'
printf '%s\n' 'device-changes=no'
printf '%s\n' '=== END ==='
