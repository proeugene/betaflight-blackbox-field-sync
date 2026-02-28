"""Disk space utilities."""

from __future__ import annotations

import os
from pathlib import Path


def free_bytes(path: str | Path) -> int:
    """Return free bytes available at *path* (uses os.statvfs)."""
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize


def free_mb(path: str | Path) -> float:
    return free_bytes(path) / (1024 * 1024)


def used_and_free_gb(path: str | Path) -> tuple[float, float]:
    """Return (used_gb, free_gb) for the filesystem containing *path*."""
    st = os.statvfs(path)
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    used = total - free
    return used / (1024**3), free / (1024**3)
