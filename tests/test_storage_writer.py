"""Tests for StreamWriter — file writing, SHA-256 verification, abort cleanup."""

import hashlib
import tempfile
from pathlib import Path

import pytest

from bbsyncer.storage.writer import StreamWriter


@pytest.fixture
def tmp_path():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


class TestStreamWriter:
    def test_write_and_close(self, tmp_path):
        path = tmp_path / 'test.bbl'
        w = StreamWriter(path)
        w.open()
        w.write(b'hello')
        w.write(b'world')
        w.close()
        assert path.read_bytes() == b'helloworld'
        assert w.bytes_written == 10

    def test_sha256_matches(self, tmp_path):
        path = tmp_path / 'test.bbl'
        data = b'betaflight blackbox data' * 100
        w = StreamWriter(path)
        w.open()
        w.write(data)
        w.close()
        expected = hashlib.sha256(data).hexdigest()
        assert w.sha256_hex() == expected

    def test_verify_against_file_success(self, tmp_path):
        path = tmp_path / 'test.bbl'
        data = b'\xde\xad\xbe\xef' * 256
        w = StreamWriter(path)
        w.open()
        w.write(data)
        w.close()
        match, sha = w.verify_against_file()
        assert match is True
        assert sha == hashlib.sha256(data).hexdigest()

    def test_verify_against_file_detects_corruption(self, tmp_path):
        path = tmp_path / 'test.bbl'
        data = b'\x01\x02\x03\x04'
        w = StreamWriter(path)
        w.open()
        w.write(data)
        w.close()
        # Corrupt the file on disk
        with open(path, 'r+b') as f:
            f.write(b'\xff')
        match, sha = w.verify_against_file()
        assert match is False

    def test_abort_deletes_file(self, tmp_path):
        path = tmp_path / 'test.bbl'
        w = StreamWriter(path)
        w.open()
        w.write(b'partial data')
        w.abort()
        assert not path.exists()

    def test_write_empty_data_ignored(self, tmp_path):
        path = tmp_path / 'test.bbl'
        w = StreamWriter(path)
        w.open()
        w.write(b'')
        w.write(b'')
        w.close()
        assert w.bytes_written == 0
        assert path.read_bytes() == b''

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / 'sub' / 'dir' / 'test.bbl'
        w = StreamWriter(path)
        w.open()
        w.write(b'data')
        w.close()
        assert path.read_bytes() == b'data'
