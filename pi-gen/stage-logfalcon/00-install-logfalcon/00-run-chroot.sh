#!/bin/bash -e
# Install logfalcon into the image

INSTALL_DIR="/opt/logfalcon"
CONFIG_DIR="/etc/logfalcon"
LOG_DIR="/mnt/logfalcon-logs"
REPO_DIR="/tmp/logfalcon-src"

# Create bbsyncer system user (legacy name kept for compatibility)
if ! id bbsyncer &>/dev/null; then
    useradd --system --no-create-home --shell /sbin/nologin \
        --groups dialout bbsyncer 2>/dev/null || \
    useradd --system --no-create-home --shell /sbin/nologin bbsyncer
fi

# Add to gpio group if it exists
usermod -a -G gpio bbsyncer 2>/dev/null || true

# Install Go binary
mkdir -p "$INSTALL_DIR"

# Detect architecture and copy appropriate binary
ARCH=$(uname -m)
case "$ARCH" in
    armv6l|armv7l) BINARY_NAME="logfalcon-arm6" ;;
    aarch64)       BINARY_NAME="logfalcon-arm64" ;;
    *)             BINARY_NAME="logfalcon" ;;
esac

if [ -f "$REPO_DIR/bin/$BINARY_NAME" ]; then
    install -m 755 "$REPO_DIR/bin/$BINARY_NAME" "$INSTALL_DIR/logfalcon"
elif [ -f "$REPO_DIR/logfalcon" ]; then
    install -m 755 "$REPO_DIR/logfalcon" "$INSTALL_DIR/logfalcon"
else
    echo "ERROR: No logfalcon binary found in $REPO_DIR"
    exit 1
fi

# Config
mkdir -p "$CONFIG_DIR"
cp "$REPO_DIR/config/logfalcon.toml" "$CONFIG_DIR/logfalcon.toml"

# Log storage
mkdir -p "$LOG_DIR"
chown bbsyncer:bbsyncer "$LOG_DIR"
chmod 755 "$LOG_DIR"

# Firstboot script
cp "$REPO_DIR/system/firstboot.sh" "$INSTALL_DIR/firstboot.sh"
chmod +x "$INSTALL_DIR/firstboot.sh"

# Ownership
chown -R bbsyncer:bbsyncer "$INSTALL_DIR" "$CONFIG_DIR"

# ── Disable conflicting services ────────────────────────────────────────────
# This is an AP-only appliance. Several services fight hostapd for wlan0.
# Strategy: mask everything that manages Wi-Fi in client mode.
# Masking (symlink → /dev/null) beats any later `systemctl enable` call
# and survives pi-gen's export-image stage which can reinstall packages.

# wpa_supplicant — Wi-Fi client supplicant, fights hostapd for wlan0
rm -f /etc/systemd/system/multi-user.target.wants/wpa_supplicant.service
rm -f /etc/systemd/system/multi-user.target.wants/wpa_supplicant@wlan0.service
rm -f /etc/systemd/system/dbus-fi.w1.wpa_supplicant1.service
ln -sf /dev/null /etc/systemd/system/wpa_supplicant.service
ln -sf /dev/null /etc/systemd/system/wpa_supplicant@wlan0.service

# NetworkManager — Raspberry Pi OS Bookworm installs NM enabled by default.
# NM takes over wlan0 in managed/client mode, completely preventing hostapd
# from starting an AP. Must be masked, not just disabled.
rm -f /etc/systemd/system/multi-user.target.wants/NetworkManager.service
rm -f /etc/systemd/system/network-online.target.wants/NetworkManager-wait-online.service
rm -f /etc/systemd/system/multi-user.target.wants/ModemManager.service
rm -f /etc/systemd/system/dbus-org.freedesktop.ModemManager1.service
ln -sf /dev/null /etc/systemd/system/NetworkManager.service
ln -sf /dev/null /etc/systemd/system/NetworkManager-wait-online.service
ln -sf /dev/null /etc/systemd/system/ModemManager.service

# userconfig.service — Bookworm first-boot wizard (shows "enter username" prompt).
# pi-gen's export-image stage installs userconf-pi AFTER our custom stage runs,
# which re-creates the multi-user.target.wants symlink. Masking with /dev/null
# prevents any re-enable: masked units cannot be started or re-enabled.
rm -f /etc/systemd/system/multi-user.target.wants/userconfig.service
ln -sf /dev/null /etc/systemd/system/userconfig.service

# Cleanup
rm -rf "$REPO_DIR"
