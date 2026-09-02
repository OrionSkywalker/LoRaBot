#!/usr/bin/env bash
# Discover and configure a USB Meshtastic serial device for the LoRaBot service.

set -euo pipefail

CONFIG_FILE="/etc/lorabot/config.ini"
SERVICE_NAME="lorabot"
SERVICE_USER="lorabot"
VENV_MESHTASTIC="/opt/lorabot/.venv/bin/meshtastic"
UDEV_RULE_FILE="/etc/udev/rules.d/99-lorabot-meshtastic.rules"

usage() {
  echo "Usage: sudo bash scripts/setup_serial.sh [--device /dev/serial/by-id/DEVICE]"
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

if [[ ${EUID} -ne 0 ]]; then
  die "Run this script with sudo."
fi

requested_device=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --device)
      [[ $# -ge 2 ]] || die "--device requires a path."
      requested_device="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      die "Unknown argument: $1"
      ;;
  esac
done

[[ -f "$CONFIG_FILE" ]] || die "Configuration not found: $CONFIG_FILE"
[[ -x "$VENV_MESHTASTIC" ]] || die "Meshtastic CLI not found: $VENV_MESHTASTIC"
id "$SERVICE_USER" >/dev/null 2>&1 || die "Service user '$SERVICE_USER' does not exist."
command -v udevadm >/dev/null 2>&1 || die "udevadm is required."

if [[ -n "$requested_device" ]]; then
  device="$requested_device"
else
  shopt -s nullglob
  devices=(/dev/serial/by-id/*)
  shopt -u nullglob
  if [[ ${#devices[@]} -eq 0 ]]; then
    die "No stable serial device was found in /dev/serial/by-id. Check the USB data cable."
  fi
  if [[ ${#devices[@]} -gt 1 ]]; then
    echo "More than one serial device was found:"
    printf '  %s\n' "${devices[@]}"
    die "Run again with --device followed by the intended Meshtastic path."
  fi
  device="${devices[0]}"
fi

[[ -e "$device" ]] || die "Device does not exist: $device"
real_device="$(readlink -f -- "$device")"
[[ -n "$real_device" && -c "$real_device" ]] || die "Not a character device: $device"
case "$real_device" in
  /dev/tty*) ;;
  *) die "Resolved device is not a tty: $real_device" ;;
esac

properties="$(udevadm info --query=property --name="$real_device")"
vendor_id="$(printf '%s\n' "$properties" | sed -n 's/^ID_VENDOR_ID=//p' | head -n 1)"
model_id="$(printf '%s\n' "$properties" | sed -n 's/^ID_MODEL_ID=//p' | head -n 1)"
serial_id="$(printf '%s\n' "$properties" | sed -n 's/^ID_SERIAL_SHORT=//p' | head -n 1)"
[[ "$vendor_id" =~ ^[[:xdigit:]]{4}$ ]] || die "Could not determine a safe USB vendor ID."
[[ "$model_id" =~ ^[[:xdigit:]]{4}$ ]] || die "Could not determine a safe USB model ID."
[[ "$serial_id" =~ ^[[:alnum:].:_-]+$ ]] || die "Could not determine a safe USB serial ID."

echo "Found Meshtastic serial device:"
echo "  stable path: $device"
echo "  tty target:  $real_device"
echo "  USB ID:      $vendor_id:$model_id"
echo "  serial:      $serial_id"

getent group dialout >/dev/null 2>&1 || die "The dialout group does not exist."
usermod -aG dialout "$SERVICE_USER"

temporary_rule="$(mktemp)"
cleanup() {
  rm -f -- "$temporary_rule"
}
trap cleanup EXIT
printf '%s\n' \
  "SUBSYSTEM==\"tty\", ENV{ID_VENDOR_ID}==\"$vendor_id\", ENV{ID_MODEL_ID}==\"$model_id\", ENV{ID_SERIAL_SHORT}==\"$serial_id\", GROUP=\"dialout\", MODE=\"0660\"" \
  >"$temporary_rule"
install -o root -g root -m 0644 "$temporary_rule" "$UDEV_RULE_FILE"
udevadm control --reload-rules

# Apply the same ownership immediately; the udev rule makes it persistent on reconnect/reboot.
chgrp dialout "$real_device"
chmod 0660 "$real_device"

escaped_device="$(printf '%s' "$device" | sed 's/[&|]/\\&/g')"
if grep -Eq '^[[:space:]]*serial_port[[:space:]]*=' "$CONFIG_FILE"; then
  sed -i "s|^[[:space:]]*serial_port[[:space:]]*=.*|serial_port = $escaped_device|" "$CONFIG_FILE"
else
  die "No serial_port setting was found in $CONFIG_FILE"
fi

was_active="false"
if systemctl is-active --quiet "$SERVICE_NAME"; then
  was_active="true"
  systemctl stop "$SERVICE_NAME"
fi

restore_service() {
  cleanup
  if [[ "$was_active" == "true" ]]; then
    systemctl start "$SERVICE_NAME" || true
  fi
}
trap restore_service EXIT

runuser -u "$SERVICE_USER" -- test -r "$device" || die "The service user still lacks read access."
runuser -u "$SERVICE_USER" -- test -w "$device" || die "The service user still lacks write access."

echo "Permissions are correct. Requesting node information..."
if ! timeout 90 runuser -u "$SERVICE_USER" -- "$VENV_MESHTASTIC" --port "$device" --info; then
  die "Meshtastic could not read the radio. Check the cable, firmware, and exact device selection."
fi

if [[ "$was_active" == "true" ]]; then
  systemctl start "$SERVICE_NAME"
  was_active="false"
fi

echo
echo "Serial setup succeeded. LoRaBot is configured to use:"
echo "  $device"
echo "Check the service with: sudo systemctl status lorabot --no-pager"
