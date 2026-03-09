"""FC detection and identification via MSP handshake."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from logfalcon.msp.client import MSPClient, MSPError
from logfalcon.msp.constants import (
    BLACKBOX_DEVICE_FLASH,
    BLACKBOX_DEVICE_NONE,
    BLACKBOX_DEVICE_SDCARD,
    BTFL_VARIANT,
    SUPPORTED_VARIANTS,
)

log = logging.getLogger(__name__)


@dataclass
class FCInfo:
    api_major: int
    api_minor: int
    variant: bytes  # e.g. b'BTFL' or b'INAV'
    uid: str  # hex string, e.g. "12ab34cdef..."
    blackbox_device: int


class FCDetectionError(Exception):
    pass


class FCNotSupported(FCDetectionError):
    """FC variant is not supported (not Betaflight or iNav)."""

    pass


# Keep old name as alias for backwards compatibility
FCNotBetaflight = FCNotSupported


class FCSDCardBlackbox(FCDetectionError):
    """FC uses SD card for blackbox — must be read directly."""

    pass


class FCBlackboxEmpty(FCDetectionError):
    """Flash is already empty — nothing to sync."""

    pass


def detect_fc(client: MSPClient) -> FCInfo:
    """Run MSP handshake, verify supported FC variant, return FC info.

    Raises:
        FCNotSupported: Variant not in SUPPORTED_VARIANTS
        FCSDCardBlackbox: Blackbox device is SD card
        FCDetectionError: Other identification failure
    """
    try:
        major, minor = client.get_api_version()
        log.info('MSP API version: %d.%d', major, minor)
    except MSPError as exc:
        raise FCDetectionError(f'MSP API_VERSION failed: {exc}') from exc

    try:
        variant = client.get_fc_variant()
        log.info('FC variant: %r', variant)
    except MSPError as exc:
        raise FCDetectionError(f'MSP FC_VARIANT failed: {exc}') from exc

    if variant[:4] not in SUPPORTED_VARIANTS:
        raise FCNotSupported(
            f'Unsupported FC variant {variant!r} — expected one of: '
            + ', '.join(v.decode() for v in sorted(SUPPORTED_VARIANTS))
        )

    uid = 'unknown'
    try:
        uid = client.get_uid()
        log.info('FC UID: %s', uid)
    except MSPError:
        log.warning("Could not read FC UID, using 'unknown'")

    # iNav deprecated MSP_BLACKBOX_CONFIG (80) — returns all zeros.
    # For iNav, skip the device-type check and infer flash support from
    # DATAFLASH_SUMMARY later in the orchestrator.
    blackbox_device = BLACKBOX_DEVICE_NONE
    if variant[:4] == BTFL_VARIANT:
        try:
            bb_cfg = client.get_blackbox_config()
            blackbox_device = bb_cfg.get('device', BLACKBOX_DEVICE_NONE)
            log.info('Blackbox device type: %d', blackbox_device)
        except MSPError as exc:
            log.warning('Could not read BLACKBOX_CONFIG: %s', exc)
    else:
        # For iNav, assume flash until DATAFLASH_SUMMARY proves otherwise
        blackbox_device = BLACKBOX_DEVICE_FLASH
        log.info('Non-Betaflight FC — skipping BLACKBOX_CONFIG, assuming flash')

    if blackbox_device == BLACKBOX_DEVICE_SDCARD:
        raise FCSDCardBlackbox(
            'FC uses SD card for blackbox — remove the FC SD card and read it directly'
        )

    return FCInfo(
        api_major=major,
        api_minor=minor,
        variant=variant,
        uid=uid,
        blackbox_device=blackbox_device,
    )
