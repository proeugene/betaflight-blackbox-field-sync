"""Native C acceleration for MSP protocol hot paths.

Provides transparent fallback: if the C extension fails to import
(unsupported platform, missing compiler at install time), the pure
Python implementations are used instead.

Individual modules (crc.py, framing.py, huffman.py) handle their
own imports from _msp_fast with try/except fallback.
"""

from __future__ import annotations

try:
    import bbsyncer._native._msp_fast  # noqa: F401

    _NATIVE_AVAILABLE = True
except ImportError:
    _NATIVE_AVAILABLE = False

__all__ = ['_NATIVE_AVAILABLE']
