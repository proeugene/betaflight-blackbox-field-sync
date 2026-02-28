"""MSP frame encoder and state-machine decoder.

Ported from betaflight-configurator/src/js/msp.js.
Uses C extension when available for ~10-50x faster frame decoding.

Frame formats:
  v1: $M< + size(1B) + code(1B) + payload[size] + XOR-checksum(1B)
  v2: $X< + flag(1B,0) + code(2B LE) + size(2B LE) + payload[size] + CRC8-DVB-S2(1B)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .crc import crc8_dvb_s2, crc8_xor

try:
    from bbsyncer._native._msp_fast import decode as _native_decode
    from bbsyncer._native._msp_fast import decoder_new as _native_decoder_new

    _USE_NATIVE_DECODER = True
except ImportError:
    _USE_NATIVE_DECODER = False

_IDLE = 1
_PROTO_V1_M = 2
_PROTO_DIRECTION = 3
_V1_LEN = 4
_V1_CODE = 5
_V1_PAYLOAD = 6
_V1_CHECKSUM = 7
_V2_FLAG = 8
_V2_CODE_LO = 9
_V2_CODE_HI = 10
_V2_LEN_LO = 11
_V2_LEN_HI = 12
_V2_PAYLOAD = 13
_V2_CHECKSUM = 14


@dataclass
class MSPFrame:
    version: int  # 1 or 2
    direction: int  # ord('<') or ord('>')
    code: int
    payload: bytes = field(default=b'')


def encode_v1(code: int, payload: bytes = b'') -> bytes:
    """Encode an MSP v1 frame (to-FC direction)."""
    size = len(payload)
    # checksum covers: size + code + payload
    checksum = crc8_xor(bytes([size, code]) + payload)
    return b'$M<' + bytes([size, code]) + payload + bytes([checksum])


def encode_v2(code: int, payload: bytes = b'') -> bytes:
    """Encode an MSP v2 frame (to-FC direction)."""
    size = len(payload)
    # CRC covers: flag(0) + code_lo + code_hi + len_lo + len_hi + payload
    header_for_crc = bytes(
        [
            0,  # flag
            code & 0xFF,  # code lo
            (code >> 8) & 0xFF,  # code hi
            size & 0xFF,  # len lo
            (size >> 8) & 0xFF,  # len hi
        ]
    )
    crc = crc8_dvb_s2(header_for_crc + payload)
    return b'$X<' + header_for_crc + payload + bytes([crc])


class FrameDecoder:
    """Stateful MSP frame decoder. Feed bytes via feed(); complete frames are
    appended to the `frames` list.

    Uses C extension for ~10-50x faster decoding when available.
    """

    def __init__(self) -> None:
        self.frames: list[MSPFrame] = []
        self._native_state = _native_decoder_new() if _USE_NATIVE_DECODER else None
        self._reset()

    def _reset(self) -> None:
        self._state = _IDLE
        self._version = 0
        self._direction = 0
        self._code = 0
        self._size = 0
        self._payload = bytearray()
        self._payload_idx = 0
        self._checksum = 0  # running XOR for v1 or running CRC for v2
        self._v2_header = bytearray()  # accumulate V2 header bytes for batch CRC

    def feed(self, data: bytes) -> None:
        if self._native_state is not None:
            raw_frames = _native_decode(data, self._native_state)
            for ver, dirn, code, payload in raw_frames:
                self.frames.append(
                    MSPFrame(version=ver, direction=dirn, code=code, payload=payload)
                )
        else:
            for byte in data:
                self._process(byte)

    def _process(self, b: int) -> None:  # noqa: C901
        s = self._state

        if s == _IDLE:
            if b == ord('$'):
                self._state = _PROTO_V1_M
        elif s == _PROTO_V1_M:
            if b == ord('M'):
                self._version = 1
                self._state = _PROTO_DIRECTION
            elif b == ord('X'):
                self._version = 2
                self._state = _PROTO_DIRECTION
            else:
                self._reset()
        elif s == _PROTO_DIRECTION:
            if b in (ord('<'), ord('>'), ord('!')):
                self._direction = b
                if self._version == 1:
                    self._state = _V1_LEN
                else:
                    self._state = _V2_FLAG
            else:
                self._reset()

        # --- V1 ---
        elif s == _V1_LEN:
            self._size = b
            self._checksum = b  # XOR starts with length byte
            self._state = _V1_CODE
        elif s == _V1_CODE:
            self._code = b
            self._checksum ^= b
            if self._size == 0:
                self._payload = bytearray()
                self._state = _V1_CHECKSUM
            else:
                self._payload = bytearray(self._size)
                self._payload_idx = 0
                self._state = _V1_PAYLOAD
        elif s == _V1_PAYLOAD:
            self._payload[self._payload_idx] = b
            self._payload_idx += 1
            self._checksum ^= b
            if self._payload_idx == self._size:
                self._state = _V1_CHECKSUM
        elif s == _V1_CHECKSUM:
            if b == self._checksum:
                self.frames.append(
                    MSPFrame(
                        version=1,
                        direction=self._direction,
                        code=self._code,
                        payload=bytes(self._payload),
                    )
                )
            # always reset regardless of checksum validity
            self._reset()

        # --- V2 ---
        elif s == _V2_FLAG:
            self._v2_header = bytearray([b])
            self._state = _V2_CODE_LO
        elif s == _V2_CODE_LO:
            self._code = b
            self._v2_header.append(b)
            self._state = _V2_CODE_HI
        elif s == _V2_CODE_HI:
            self._code |= b << 8
            self._v2_header.append(b)
            self._state = _V2_LEN_LO
        elif s == _V2_LEN_LO:
            self._size = b
            self._v2_header.append(b)
            self._state = _V2_LEN_HI
        elif s == _V2_LEN_HI:
            self._size |= b << 8
            self._v2_header.append(b)
            if self._size == 0:
                self._payload = bytearray()
                self._state = _V2_CHECKSUM
            else:
                self._payload = bytearray(self._size)
                self._payload_idx = 0
                self._state = _V2_PAYLOAD
        elif s == _V2_PAYLOAD:
            self._payload[self._payload_idx] = b
            self._payload_idx += 1
            if self._payload_idx == self._size:
                self._state = _V2_CHECKSUM
        elif s == _V2_CHECKSUM:
            # Compute CRC over header + payload in one batch call
            expected = crc8_dvb_s2(self._payload, initial=crc8_dvb_s2(self._v2_header))
            if b == expected:
                self.frames.append(
                    MSPFrame(
                        version=2,
                        direction=self._direction,
                        code=self._code,
                        payload=bytes(self._payload),
                    )
                )
            self._reset()
