"""Session directory creation and manifest.json read/write."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from bbsyncer.fc.detector import FCInfo

log = logging.getLogger(__name__)

MANIFEST_FILENAME = 'manifest.json'
RAW_FLASH_FILENAME = 'raw_flash.bbl'


def make_session_dir(storage_root: Path, fc_info: FCInfo) -> Path:
    """Create and return a new timestamped session directory.

    Layout::

        <storage_root>/fc_BTFL_uid-<uid8>/<YYYY-MM-DD_HHMMSS>/
    """
    # Use first 8 chars of UID (or 'unknown') for the directory name
    uid_short = fc_info.uid[:8] if fc_info.uid != 'unknown' else 'unknown'
    fc_dir = storage_root / f'fc_BTFL_uid-{uid_short}'
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    session_dir = fc_dir / timestamp
    session_dir.mkdir(parents=True, exist_ok=True)
    log.info('Created session directory: %s', session_dir)
    return session_dir


def write_manifest(
    session_dir: Path,
    fc_info: FCInfo,
    sha256: str,
    used_size: int,
    erase_completed: bool = False,
    erase_attempted: bool = False,
) -> Path:
    """Write manifest.json to session_dir. Returns path to the file."""
    manifest = {
        'version': 1,
        'created_utc': datetime.now(UTC).isoformat(),
        'fc': {
            'variant': fc_info.variant.decode('ascii', errors='replace'),
            'uid': fc_info.uid,
            'api_version': f'{fc_info.api_major}.{fc_info.api_minor}',
            'blackbox_device': fc_info.blackbox_device,
        },
        'file': {
            'name': RAW_FLASH_FILENAME,
            'sha256': sha256,
            'bytes': used_size,
        },
        'erase_attempted': erase_attempted,
        'erase_completed': erase_completed,
    }
    path = session_dir / MANIFEST_FILENAME
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    try:
        os.write(fd, json.dumps(manifest, indent=2).encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    log.debug('Wrote manifest to %s', path)
    return path


def update_manifest_erase(session_dir: Path, erase_completed: bool) -> None:
    """Update erase_completed field in an existing manifest."""
    path = session_dir / MANIFEST_FILENAME
    try:
        data = json.loads(path.read_text())
        data['erase_completed'] = erase_completed
        data['erase_attempted'] = True
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
        try:
            os.write(fd, json.dumps(data, indent=2).encode())
            os.fsync(fd)
        finally:
            os.close(fd)
        log.debug('Updated manifest erase_completed=%s', erase_completed)
    except (OSError, json.JSONDecodeError) as exc:
        log.error('Failed to update manifest: %s', exc)


def list_sessions(storage_root: Path) -> list[dict]:
    """Return a list of all sessions on the Pi SD card, newest first."""
    sessions = []
    for fc_dir in sorted(storage_root.iterdir()):
        if not fc_dir.is_dir():
            continue
        for session_dir in sorted(fc_dir.iterdir(), reverse=True):
            if not session_dir.is_dir():
                continue
            manifest_path = session_dir / MANIFEST_FILENAME
            bbl_path = session_dir / RAW_FLASH_FILENAME
            if not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text())
            except json.JSONDecodeError:
                continue
            sessions.append(
                {
                    'session_id': f'{fc_dir.name}/{session_dir.name}',
                    'fc_dir': fc_dir.name,
                    'session_dir': session_dir.name,
                    'path': str(session_dir),
                    'bbl_path': str(bbl_path) if bbl_path.exists() else None,
                    'manifest': manifest,
                }
            )
    return sessions
