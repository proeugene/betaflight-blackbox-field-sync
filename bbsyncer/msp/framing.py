"""MSP frame encoder and state-machine decoder.

Ported from betaflight-configurator/src/js/msp.js.

Frame formats:
  v1: $M< + size(1B) + code(1B) + payload[size] + XOR-checksum(1B)
  v2: $X< + flag(1B,0) + code(2B LE) + size(2B LE) + payload[size] + CRC8-DVB-S2(1B)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, auto

from .crc import crc8_dvb_s2, crc8_xor


class _State(IntEnum):
    IDLE = auto()
    PROTO_V1_M = auto()
    PROTO_DIRECTION = auto()
    # V1 states
    V1_LEN = auto()
    V1_CODE = auto()
    V1_PAYLOAD = auto()
    V1_CHECKSUM = auto()
    # V2 states
    V2_FLAG = auto()
    V2_CODE_LO = auto()
    V2_CODE_HI = auto()
    V2_LEN_LO = auto()
    V2_LEN_HI = auto()
    V2_PAYLOAD = auto()
    V2_CHECKSUM = auto()


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
    appended to the `frames` list."""

    def __init__(self) -> None:
        self.frames: list[MSPFrame] = []
        self._reset()

    def _reset(self) -> None:
        self._state = _State.IDLE
        self._version = 0
        self._direction = 0
        self._code = 0
        self._size = 0
        self._payload = bytearray()
        self._checksum = 0  # running XOR for v1 or running CRC for v2
        self._v2_header = bytearray()  # accumulate V2 header bytes for batch CRC

    def feed(self, data: bytes) -> None:
        for byte in data:
            self._process(byte)

    def _process(self, b: int) -> None:  # noqa: C901
        s = self._state

        if s == _State.IDLE:
            if b == ord('$'):
                self._state = _State.PROTO_V1_M
        elif s == _State.PROTO_V1_M:
            if b == ord('M'):
                self._version = 1
                self._state = _State.PROTO_DIRECTION
            elif b == ord('X'):
                self._version = 2
                self._state = _State.PROTO_DIRECTION
            else:
                self._reset()
        elif s == _State.PROTO_DIRECTION:
            if b in (ord('<'), ord('>'), ord('!')):
                self._direction = b
                if self._version == 1:
                    self._state = _State.V1_LEN
                else:
                    self._state = _State.V2_FLAG
            else:
                self._reset()

        # --- V1 ---
        elif s == _State.V1_LEN:
            self._size = b
            self._checksum = b  # XOR starts with length byte
            self._state = _State.V1_CODE
        elif s == _State.V1_CODE:
            self._code = b
            self._checksum ^= b
            self._payload = bytearray()
            if self._size == 0:
                self._state = _State.V1_CHECKSUM
            else:
                self._state = _State.V1_PAYLOAD
        elif s == _State.V1_PAYLOAD:
            self._payload.append(b)
            self._checksum ^= b
            if len(self._payload) == self._size:
                self._state = _State.V1_CHECKSUM
        elif s == _State.V1_CHECKSUM:
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
        elif s == _State.V2_FLAG:
            self._v2_header = bytearray([b])
            self._state = _State.V2_CODE_LO
        elif s == _State.V2_CODE_LO:
            self._code = b
            self._v2_header.append(b)
            self._state = _State.V2_CODE_HI
        elif s == _State.V2_CODE_HI:
            self._code |= b << 8
            self._v2_header.append(b)
            self._state = _State.V2_LEN_LO
        elif s == _State.V2_LEN_LO:
            self._size = b
            self._v2_header.append(b)
            self._state = _State.V2_LEN_HI
        elif s == _State.V2_LEN_HI:
            self._size |= b << 8
            self._v2_header.append(b)
            self._payload = bytearray()
            if self._size == 0:
                self._state = _State.V2_CHECKSUM
            else:
                self._state = _State.V2_PAYLOAD
        elif s == _State.V2_PAYLOAD:
            self._payload.append(b)
            if len(self._payload) == self._size:
                self._state = _State.V2_CHECKSUM
        elif s == _State.V2_CHECKSUM:
            # Compute CRC over header + payload in one batch call
            expected = crc8_dvb_s2(bytes(self._v2_header) + bytes(self._payload))
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
