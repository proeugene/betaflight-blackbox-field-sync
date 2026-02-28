"""Tests for the C native extension (_msp_fast).

Tests verify that the C implementation produces identical results
to the pure Python implementations for CRC, frame decoding, and
Huffman decompression.
"""

import pytest

from bbsyncer._native import _NATIVE_AVAILABLE

pytestmark = pytest.mark.skipif(not _NATIVE_AVAILABLE, reason='C extension not built')


class TestNativeCRC:
    def test_crc8_xor_matches_python(self):
        from bbsyncer._native._msp_fast import crc8_xor as c_xor

        from bbsyncer.msp.crc import _py_crc8_xor

        for data in [b'', b'\x00', b'\xff', b'\x03\x01\x05', bytes(range(256))]:
            assert c_xor(data) == _py_crc8_xor(data), f'Mismatch for {data!r}'

    def test_crc8_dvb_s2_matches_python(self):
        from bbsyncer._native._msp_fast import crc8_dvb_s2 as c_dvb

        from bbsyncer.msp.crc import _py_crc8_dvb_s2

        for data in [b'', b'\x00', b'\xff', bytes(range(256)), b'\xab\xcd' * 100]:
            assert c_dvb(data) == _py_crc8_dvb_s2(data), f'Mismatch for {data!r}'

    def test_crc8_dvb_s2_initial_param(self):
        from bbsyncer._native._msp_fast import crc8_dvb_s2 as c_dvb

        from bbsyncer.msp.crc import _py_crc8_dvb_s2

        header = bytes([0, 100, 0, 2, 0])
        payload = bytes([0xAB, 0xCD])
        full = _py_crc8_dvb_s2(header + payload)
        chained = c_dvb(payload, c_dvb(header))
        assert chained == full


class TestNativeDecoder:
    def _make_v1_response(self, code, payload):
        from bbsyncer.msp.crc import _py_crc8_xor

        size = len(payload)
        checksum = _py_crc8_xor(bytes([size, code]) + payload)
        return b'$M>' + bytes([size, code]) + payload + bytes([checksum])

    def _make_v2_response(self, code, payload):
        from bbsyncer.msp.crc import _py_crc8_dvb_s2

        size = len(payload)
        hdr = bytes([0, code & 0xFF, (code >> 8) & 0xFF, size & 0xFF, (size >> 8) & 0xFF])
        crc = _py_crc8_dvb_s2(hdr + payload)
        return b'$X>' + hdr + payload + bytes([crc])

    def test_v1_single_frame(self):
        from bbsyncer._native._msp_fast import decode, decoder_new

        ds = decoder_new()
        payload = b'\x03\x01\x05BTFL'
        raw = self._make_v1_response(2, payload)
        frames = decode(raw, ds)
        assert len(frames) == 1
        ver, dirn, code, p = frames[0]
        assert ver == 1 and dirn == ord('>') and code == 2 and p == payload

    def test_v2_single_frame(self):
        from bbsyncer._native._msp_fast import decode, decoder_new

        ds = decoder_new()
        payload = b'BTFL'
        raw = self._make_v2_response(2, payload)
        frames = decode(raw, ds)
        assert len(frames) == 1
        ver, dirn, code, p = frames[0]
        assert ver == 2 and code == 2 and p == payload

    def test_multiple_frames(self):
        from bbsyncer._native._msp_fast import decode, decoder_new

        ds = decoder_new()
        f1 = self._make_v1_response(1, b'\x01\x02')
        f2 = self._make_v1_response(2, b'BTFL')
        frames = decode(f1 + f2, ds)
        assert len(frames) == 2
        assert frames[0][2] == 1
        assert frames[1][2] == 2

    def test_bad_checksum_dropped(self):
        from bbsyncer._native._msp_fast import decode, decoder_new

        ds = decoder_new()
        raw = bytearray(self._make_v1_response(1, b''))
        raw[-1] ^= 0xFF
        frames = decode(bytes(raw), ds)
        assert len(frames) == 0

    def test_noise_before_frame(self):
        from bbsyncer._native._msp_fast import decode, decoder_new

        ds = decoder_new()
        noise = bytes([0x00, 0xFF, 0x12, 0x34])
        frame = self._make_v1_response(5, b'\xab')
        frames = decode(noise + frame, ds)
        assert len(frames) == 1 and frames[0][2] == 5

    def test_incremental_feed(self):
        from bbsyncer._native._msp_fast import decode, decoder_new

        ds = decoder_new()
        raw = self._make_v1_response(3, b'\x01\x02\x03')
        all_frames = []
        for byte in raw:
            all_frames.extend(decode(bytes([byte]), ds))
        assert len(all_frames) == 1

    def test_v2_large_payload(self):
        from bbsyncer._native._msp_fast import decode, decoder_new

        ds = decoder_new()
        payload = bytes(range(256)) * 64  # 16KB
        raw = self._make_v2_response(0x1234, payload)
        frames = decode(raw, ds)
        assert len(frames) == 1
        assert frames[0][2] == 0x1234
        assert frames[0][3] == payload


class TestNativeHuffman:
    def test_simple_decode(self):
        from bbsyncer._native._msp_fast import huffman_decode

        # 0x00=code(00,len2), 0x01=code(01,len2)
        huf_input = bytes([0b00011000])
        result = huffman_decode(huf_input, 2)
        assert result == bytes([0x00, 0x01])

    def test_matches_python(self):
        from bbsyncer._native._msp_fast import huffman_decode as c_huf

        from bbsyncer.msp.huffman import _py_huffman_decode

        # Encode a known sequence and verify both decoders agree
        # Bytes 0x00-0x05 have short codes (2-4 bits each)
        test_input = bytes([0b00010010, 0b00110100, 0b10101011])
        for count in range(1, 8):
            py_result = _py_huffman_decode(test_input, count)
            c_result = c_huf(test_input, count)
            assert c_result == py_result, f'Mismatch at count={count}'

    def test_empty_output(self):
        from bbsyncer._native._msp_fast import huffman_decode

        result = huffman_decode(b'\x00', 0)
        assert result == b''
