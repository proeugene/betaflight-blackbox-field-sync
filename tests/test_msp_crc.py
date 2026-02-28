"""Tests for MSP CRC implementations."""

from bbsyncer.msp.crc import crc8_dvb_s2, crc8_xor


class TestCRC8XOR:
    def test_empty(self):
        assert crc8_xor(b'') == 0

    def test_single_byte(self):
        assert crc8_xor(b'\x05') == 0x05

    def test_known_value(self):
        # length=1, code=1, payload=[]  → 1 XOR 1 = 0
        assert crc8_xor(bytes([1, 1])) == 0

    def test_v1_frame_checksum(self):
        # MSP_API_VERSION request: len=0, code=1
        assert crc8_xor(bytes([0, 1])) == 1

    def test_roundtrip(self):
        data = bytes(range(256))
        result = crc8_xor(data)
        assert isinstance(result, int)
        assert 0 <= result <= 255


class TestCRC8DVBS2:
    def test_empty(self):
        assert crc8_dvb_s2(b'') == 0

    def test_known_vector(self):
        # Verify against known test vector for DVB-S2 polynomial 0xD5
        # Input: 0x00 → CRC should be 0x00 (XOR with 0, shift 8 times, no poly since bit7 never set)
        assert crc8_dvb_s2(bytes([0x00])) == 0x00

    def test_single_0xff(self):
        # 0xFF: crc starts 0xFF, bit7 always set → polynomial applied 8 times
        result = crc8_dvb_s2(bytes([0xFF]))
        assert isinstance(result, int)
        assert 0 <= result <= 255

    def test_incremental_matches_bulk(self):
        data = bytes([0x01, 0x02, 0x03, 0x40, 0x00])
        bulk = crc8_dvb_s2(data)
        incremental = 0
        for b in data:
            incremental = crc8_dvb_s2(bytes([b]), incremental)
        assert bulk == incremental

    def test_v2_frame_example(self):
        # v2 header: flag=0, code_lo=1, code_hi=0, len_lo=0, len_hi=0  (MSP_API_VERSION)
        header = bytes([0, 1, 0, 0, 0])
        crc = crc8_dvb_s2(header)
        assert isinstance(crc, int)
        assert 0 <= crc <= 255
