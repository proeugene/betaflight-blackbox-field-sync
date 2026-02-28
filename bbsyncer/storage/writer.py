"""Streaming file writer with running SHA-256 checksum."""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)


class StreamWriter:
    """Write binary data to a file while computing a running SHA-256 hash.

    Usage::

        writer = StreamWriter(path)
        writer.open()
        writer.write(chunk)
        writer.close()
        sha256 = writer.sha256_hex()
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file = None
        self._hasher = hashlib.sha256()
        self._bytes_written: int = 0

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.path, 'wb', buffering=256 * 1024)  # noqa: SIM115
        log.debug('Opened output file %s', self.path)

    def write(self, data: bytes) -> None:
        if not data:
            return
        self._file.write(data)
        self._hasher.update(data)
        self._bytes_written += len(data)

    def close(self) -> None:
        if self._file:
            self._file.flush()
            os.fsync(self._file.fileno())
            self._file.close()
            self._file = None
            log.debug('Closed output file %s (%d bytes)', self.path, self._bytes_written)

    def abort(self) -> None:
        """Close and delete the partial file."""
        self.close()
        if self.path.exists():
            self.path.unlink()
            log.warning('Deleted partial file %s', self.path)

    @property
    def bytes_written(self) -> int:
        return self._bytes_written

    def sha256_hex(self) -> str:
        return self._hasher.hexdigest()

    def verify_against_file(self) -> tuple[bool, str]:
        """Re-read the file from disk and compare SHA-256.

        Returns (match: bool, file_sha256_hex: str).
        """
        h = hashlib.sha256()
        with open(self.path, 'rb') as f:
            while True:
                block = f.read(1 << 20)
                if not block:
                    break
                h.update(block)
        file_sha256 = h.hexdigest()
        streaming_sha256 = self.sha256_hex()
        match = file_sha256 == streaming_sha256
        if not match:
            log.error(
                'SHA-256 mismatch! streaming=%s file=%s',
                streaming_sha256,
                file_sha256,
            )
        return match, file_sha256
