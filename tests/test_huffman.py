"""Tests for Huffman decoder."""

from bbsyncer.msp.huffman import DEFAULT_HUFFMAN_TREE, HUFFMAN_EOF, huffman_decode


class TestHuffmanDecode:
    def test_empty_input(self):
        result = huffman_decode(b'', 0)
        assert result == b''

    def test_decode_zero_char_count(self):
        result = huffman_decode(b'\xff\xff\xff', 0)
        assert result == b''

    def test_single_byte_decode(self):
        # Value 0x00 has code_len=2, code=0x00 → bits: 00
        # Value 0x01 has code_len=2, code=0x01 → bits: 01
        # To encode 0x00: bits = 00, padded to a byte: 00000000 = 0x00
        result = huffman_decode(bytes([0x00]), 1)
        assert result == bytes([0x00])

    def test_two_bytes_decode(self):
        # 0x00 → 00, 0x01 → 01 → combined bits: 0001xxxx = 0x10
        result = huffman_decode(bytes([0x10]), 2)
        assert result == bytes([0x00, 0x01])

    def test_tree_completeness(self):
        # All byte values 0x00-0xFF should be in the tree plus EOF
        values = {e.value for e in DEFAULT_HUFFMAN_TREE}
        for i in range(256):
            assert i in values
        assert HUFFMAN_EOF in values

    def test_memoryview_input(self):
        data = bytearray([0x00])
        result = huffman_decode(memoryview(data), 1)
        assert result == bytes([0x00])
