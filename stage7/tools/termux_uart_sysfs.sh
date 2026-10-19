#!/system/bin/sh
# Xiaomi Pad 5 / nabu: read-only UART controller-to-tty mapping.
# Uses only id, test, readlink, tr, sed, printf, and shell builtins.
# Never mounts debugfs, reads bootargs/identifiers, writes GPIO/MMIO or runs
# fastboot. Output is a narrow sysfs topology summary, NOT early boot logging.
#
# Termux:
#   su -c 'sh -s' < termux_uart_sysfs.sh > "$HOME/nabu-uart-map.txt" 2>&1
#
# NABU_SYSROOT is for synthetic CI fixtures; unset on the real tablet.
ROOT="${NABU_SYSROOT:-}"

printf '%s\n' '=== STAGE 7.1 READ-ONLY UART SYSFS ==='
printf 'uid='
id -u

for ADDR in a90000 c8c000 a84000; do
    printf '\n=== UART MMIO 0x%s ===\n' "$ADDR"
    OF_FOUND=0
    for OF in \
        "$ROOT/sys/firmware/devicetree/base/soc/qcom,qup_uart@0x$ADDR" \
        "$ROOT/sys/firmware/devicetree/base/soc/qcom,qup_uart@$ADDR"
    do
        [ -d "$OF" ] || continue
        OF_FOUND=1
        printf 'of_node_present=yes\n'
        for PROP in status compatible clock-names pinctrl-names; do
            printf '%s: ' "$PROP"
            if [ -r "$OF/$PROP" ]; then
                # Only four explicit property names are allowlisted.
                tr '\000' '\n' < "$OF/$PROP" | sed -n '1,6p'
            else
                printf '%s\n' 'not-present-or-unreadable'
            fi
        done
        break
    done
    [ "$OF_FOUND" -eq 1 ] || printf '%s\n' 'of_node_present=no'

    PLAT_FOUND=0
    for DEV in "$ROOT/sys/bus/platform/devices/"*"$ADDR"*; do
        [ -e "$DEV" ] || continue
        DEV_NAME="${DEV##*/}"
        case "$DEV_NAME" in
            "$ADDR".qcom,qup_uart)
                # Only this platform type represents a UART. The QUP at
                # 0xA84000 may instead be bound as a84000.i2c (i2c_geni).
                ;;
            "$ADDR".i2c)
                printf 'other_protocol_device=%s (I2C, not UART)\n' "$DEV_NAME"
                continue
                ;;
            *)
                # Never treat all devices matching an MMIO base as UARTs.
                continue
                ;;
        esac
        PLAT_FOUND=1
        printf 'uart_platform_device=%s\n' "$DEV_NAME"
        if [ -L "$DEV/driver" ]; then
            printf 'driver_symlink_present=yes\n'
            if [ -e "$DEV/driver" ]; then
                printf 'driver_binding=confirmed\n'
                printf 'driver_link='
                readlink "$DEV/driver" 2>/dev/null || printf '%s\n' 'unreadable'
            else
                printf 'driver_binding=target-unavailable\n'
            fi
        else
            # readlink -f of a nonexistent final component can still print a
            # path on some Android builds. Never call that proof of binding.
            printf 'driver_symlink_present=no\n'
            printf 'driver_binding=not-confirmed\n'
        fi
        printf 'platform_of_node='
        if [ -L "$DEV/of_node" ]; then
            readlink -f "$DEV/of_node" 2>/dev/null || printf '%s\n' 'unknown'
        else
            printf '%s\n' 'missing'
        fi
    done
    [ "$PLAT_FOUND" -eq 1 ] || printf '%s\n' 'uart_platform_device=not-found'
done

printf '\n%s\n' '=== TTY-TO-PLATFORM CONNECTIONS ==='
TTY_FOUND=0
for TTY in \
    "$ROOT/sys/class/tty/"ttyHS[0-9]* \
    "$ROOT/sys/class/tty/"ttyMSM[0-9]* \
    "$ROOT/sys/class/tty/"ttyS[0-9]*
do
    [ -e "$TTY" ] || continue
    TTY_FOUND=1
    printf 'tty=%s\n' "${TTY##*/}"
    for LINK in device device/driver device/of_node; do
        printf '%s=' "$LINK"
        if [ -e "$TTY/$LINK" ] || [ -L "$TTY/$LINK" ]; then
            readlink -f "$TTY/$LINK" 2>/dev/null || printf '%s\n' 'unknown'
        else
            printf '%s\n' 'not-available'
        fi
    done
done
[ "$TTY_FOUND" -eq 1 ] || printf '%s\n' 'no-UART-like-tty-nodes'

printf '\n%s\n' '=== RESTRICTIONS ==='
printf '%s\n' 'read_only=yes'
printf '%s\n' 'debugfs_mounted_by_this_script=no'
printf '%s\n' 'uart_mmio_access_by_this_script=no'
printf '%s\n' 'abl_uart_state_proven=no'
printf '%s\n' '=== END ==='
