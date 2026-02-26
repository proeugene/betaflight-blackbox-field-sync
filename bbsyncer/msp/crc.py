"""CRC implementations for MSP protocol.

MSP v1: XOR checksum over length + code + payload
MSP v2: CRC8-DVB-S2 over flag + code_low + code_high + len_low + len_high + payload
"""


def crc8_xor(data: bytes) -> int:
    """XOR checksum used in MSP v1 frames."""
    result = 0
    for b in data:
        result ^= b
    return result


def _build_crc8_dvb_s2_table() -> bytes:
    table = bytearray(256)
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0xD5) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
        table[i] = crc
    return bytes(table)


_CRC8_TABLE = _build_crc8_dvb_s2_table()


def crc8_dvb_s2(data: bytes, initial: int = 0) -> int:
    """CRC8-DVB-S2 checksum used in MSP v2 frames.

    Polynomial: 0xD5 (x^8 + x^7 + x^6 + x^4 + x^2 + 1)
    Uses a precomputed 256-entry lookup table for ~7x speedup.
    """
    crc = initial
    for b in data:
        crc = _CRC8_TABLE[crc ^ b]
    return crc
