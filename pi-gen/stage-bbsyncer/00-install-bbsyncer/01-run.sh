#!/bin/bash -e
# Copy source code into chroot for installation
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"

mkdir -p "${ROOTFS_DIR}/tmp/bbsyncer-src"
# Copy source (exclude .git, .venv, etc.)
rsync -a --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
    --exclude='*.egg-info' --exclude='.pytest_cache' --exclude='pi-gen' \
    "${REPO_ROOT}/" "${ROOTFS_DIR}/tmp/bbsyncer-src/"

# Copy systemd units
install -m 644 "${REPO_ROOT}/system/bbsyncer@.service" "${ROOTFS_DIR}/etc/systemd/system/"
install -m 644 "${REPO_ROOT}/system/bbsyncer-web.service" "${ROOTFS_DIR}/etc/systemd/system/"
install -m 644 "${REPO_ROOT}/system/bbsyncer-firstboot.service" "${ROOTFS_DIR}/etc/systemd/system/"

# Copy udev rule
install -m 644 "${REPO_ROOT}/system/99-betaflight-fc.rules" "${ROOTFS_DIR}/etc/udev/rules.d/"

# Copy boot config
install -m 644 "${REPO_ROOT}/boot/bbsyncer-config.txt" "${ROOTFS_DIR}/boot/firmware/" 2>/dev/null || \
install -m 644 "${REPO_ROOT}/boot/bbsyncer-config.txt" "${ROOTFS_DIR}/boot/"

# Enable services in chroot
on_chroot << CHEOF
systemctl enable bbsyncer-web.service
systemctl enable bbsyncer-firstboot.service
systemctl enable hostapd
systemctl enable dnsmasq
systemctl enable avahi-daemon
CHEOF
