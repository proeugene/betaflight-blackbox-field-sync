"""Tests for MSP frame encoder and decoder."""
import pytest
from bbsyncer.msp.framing import FrameDecoder, MSPFrame, encode_v1, encode_v2
from bbsyncer.msp.crc import crc8_xor, crc8_dvb_s2


class TestEncodeV1:
    def test_empty_payload(self):
        frame = encode_v1(1)
        assert frame[:3] == b'$M<'
        size = frame[3]
        code = frame[4]
        checksum = frame[5]
        assert size == 0
        assert code == 1
        assert checksum == crc8_xor(bytes([0, 1]))

    def test_with_payload(self):
        payload = bytes([0x04, 0x00, 0x00, 0x00, 0x10, 0x00, 0x00])
        frame = encode_v1(71, payload)
        assert frame[:3] == b'$M<'
        assert frame[3] == len(payload)
        assert frame[4] == 71
        assert frame[-1] == crc8_xor(bytes([len(payload), 71]) + payload)

    def test_total_length(self):
        payload = b'\x01\x02\x03'
        frame = encode_v1(5, payload)
        assert len(frame) == 3 + 1 + 1 + len(payload) + 1  # preamble + len + code + payload + checksum


class TestEncodeV2:
    def test_empty_payload(self):
        frame = encode_v2(1)
        assert frame[:3] == b'$X<'
        flag = frame[3]
        code = frame[4] | (frame[5] << 8)
        size = frame[6] | (frame[7] << 8)
        assert flag == 0
        assert code == 1
        assert size == 0

    def test_crc_coverage(self):
        payload = bytes([0xAB, 0xCD])
        frame = encode_v2(100, payload)
        # CRC covers: flag + code_lo + code_hi + len_lo + len_hi + payload
        expected_crc = crc8_dvb_s2(bytes([0, 100, 0, 2, 0]) + payload)
        assert frame[-1] == expected_crc


class TestFrameDecoder:
    def _make_response_v1(self, code: int, payload: bytes) -> bytes:
        """Build a v1 FROM-FC response frame."""
        size = len(payload)
        checksum = crc8_xor(bytes([size, code]) + payload)
        return b'$M>' + bytes([size, code]) + payload + bytes([checksum])

    def test_decode_v1_empty_payload(self):
        dec = FrameDecoder()
        raw = self._make_response_v1(1, b'')
        dec.feed(raw)
        assert len(dec.frames) == 1
        f = dec.frames[0]
        assert f.version == 1
        assert f.code == 1
        assert f.payload == b''
        assert f.direction == ord('>')

    def test_decode_v1_with_payload(self):
        dec = FrameDecoder()
        payload = bytes([0x03, 0x01, 0x05, 0x42, 0x54, 0x46, 0x4C])
        raw = self._make_response_v1(2, payload)
        dec.feed(raw)
        assert len(dec.frames) == 1
        assert dec.frames[0].payload == payload

    def test_roundtrip_v1(self):
        """Encode a request, decode as if FC echo'd it back as a response."""
        # Encode a request, then manually flip direction for decode test
        request = encode_v1(70, b'')
        # Manually build a matching response (simulate FC reply)
        payload = bytes([0x03, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00])
        response = self._make_response_v1(70, payload)
        dec = FrameDecoder()
        dec.feed(response)
        assert len(dec.frames) == 1
        assert dec.frames[0].code == 70

    def test_bad_checksum_dropped(self):
        dec = FrameDecoder()
        raw = bytearray(self._make_response_v1(1, b''))
        raw[-1] ^= 0xFF  # corrupt checksum
        dec.feed(bytes(raw))
        assert len(dec.frames) == 0

    def test_multiple_frames(self):
        dec = FrameDecoder()
        f1 = self._make_response_v1(1, b'\x01\x02')
        f2 = self._make_response_v1(2, b'BTFL')
        dec.feed(f1 + f2)
        assert len(dec.frames) == 2
        assert dec.frames[0].code == 1
        assert dec.frames[1].code == 2

    def test_noise_before_frame(self):
        dec = FrameDecoder()
        noise = bytes([0x00, 0xFF, 0x12, 0x34])
        frame = self._make_response_v1(5, b'\xAB')
        dec.feed(noise + frame)
        assert len(dec.frames) == 1
        assert dec.frames[0].code == 5

    def test_incremental_feed(self):
        dec = FrameDecoder()
        raw = self._make_response_v1(3, b'\x01\x02\x03')
        for byte in raw:
            dec.feed(bytes([byte]))
        assert len(dec.frames) == 1

    def _make_response_v2(self, code: int, payload: bytes) -> bytes:
        """Build a v2 FROM-FC response frame."""
        size = len(payload)
        header_for_crc = bytes([0, code & 0xFF, (code >> 8) & 0xFF, size & 0xFF, (size >> 8) & 0xFF])
        crc = crc8_dvb_s2(header_for_crc + payload)
        return b'$X>' + header_for_crc + payload + bytes([crc])

    def test_decode_v2(self):
        dec = FrameDecoder()
        payload = b'BTFL'
        raw = self._make_response_v2(2, payload)
        dec.feed(raw)
        assert len(dec.frames) == 1
        f = dec.frames[0]
        assert f.version == 2
        assert f.code == 2
        assert f.payload == payload

    def test_decode_v2_bad_crc(self):
        dec = FrameDecoder()
        raw = bytearray(self._make_response_v2(1, b'\x01'))
        raw[-1] ^= 0xAA
        dec.feed(bytes(raw))
        assert len(dec.frames) == 0
