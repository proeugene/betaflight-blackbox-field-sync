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


def crc8_dvb_s2(data: bytes, initial: int = 0) -> int:
    """CRC8-DVB-S2 checksum used in MSP v2 frames.

    Polynomial: 0xD5 (x^8 + x^7 + x^6 + x^4 + x^2 + 1)
    """
    crc = initial
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0xD5) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc
