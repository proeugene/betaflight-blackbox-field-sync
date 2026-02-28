"""Tests for FC detection logic."""

from unittest.mock import MagicMock

import pytest

from bbsyncer.fc.detector import (
    FCDetectionError,
    FCNotBetaflight,
    FCSDCardBlackbox,
    detect_fc,
)
from bbsyncer.msp.client import MSPClient, MSPError
from bbsyncer.msp.constants import (
    BLACKBOX_DEVICE_FLASH,
    BLACKBOX_DEVICE_NONE,
    BLACKBOX_DEVICE_SDCARD,
)


def make_client(**overrides):
    client = MagicMock(spec=MSPClient)
    client.get_api_version.return_value = overrides.get('api', (1, 45))
    client.get_fc_variant.return_value = overrides.get('variant', b'BTFL')
    client.get_uid.return_value = overrides.get('uid', 'deadbeef12345678')
    client.get_blackbox_config.return_value = overrides.get(
        'bb_config', {'device': BLACKBOX_DEVICE_FLASH}
    )
    return client


class TestDetectFC:
    def test_success(self):
        client = make_client()
        info = detect_fc(client)
        assert info.variant == b'BTFL'
        assert info.uid == 'deadbeef12345678'
        assert info.api_major == 1
        assert info.api_minor == 45
        assert info.blackbox_device == BLACKBOX_DEVICE_FLASH

    def test_not_betaflight(self):
        client = make_client(variant=b'INAV')
        with pytest.raises(FCNotBetaflight):
            detect_fc(client)

    def test_sd_card_blackbox(self):
        client = make_client(bb_config={'device': BLACKBOX_DEVICE_SDCARD})
        with pytest.raises(FCSDCardBlackbox):
            detect_fc(client)

    def test_api_version_failure(self):
        client = make_client()
        client.get_api_version.side_effect = MSPError('timeout')
        with pytest.raises(FCDetectionError):
            detect_fc(client)

    def test_variant_failure(self):
        client = make_client()
        client.get_fc_variant.side_effect = MSPError('timeout')
        with pytest.raises(FCDetectionError):
            detect_fc(client)

    def test_uid_failure_uses_unknown(self):
        client = make_client()
        client.get_uid.side_effect = MSPError('timeout')
        info = detect_fc(client)
        assert info.uid == 'unknown'

    def test_blackbox_config_failure_defaults_to_none(self):
        client = make_client()
        client.get_blackbox_config.side_effect = MSPError('timeout')
        info = detect_fc(client)
        assert info.blackbox_device == BLACKBOX_DEVICE_NONE

    def test_short_variant_not_btfl(self):
        client = make_client(variant=b'BT')
        with pytest.raises(FCNotBetaflight):
            detect_fc(client)
