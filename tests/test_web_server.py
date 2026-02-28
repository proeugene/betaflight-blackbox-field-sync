"""Tests for web server routes."""

import json

import pytest

from bbsyncer.web import server as web_server_module
from bbsyncer.web.server import (
    _HTTPError,
    _render_index,
    _resolve_session_path,
)


@pytest.fixture(autouse=True)
def _clear_sessions_cache():
    """Reset the module-level sessions cache between tests."""
    web_server_module._sessions_cache = (0.0, [])
    yield
    web_server_module._sessions_cache = (0.0, [])


@pytest.fixture
def storage(tmp_path):
    # Create a fake session
    fc_dir = tmp_path / 'fc_BTFL_uid-deadbeef'
    session_dir = fc_dir / '2026-02-26_143012'
    session_dir.mkdir(parents=True)
    manifest = {
        'version': 1,
        'created_utc': '2026-02-26T14:30:12Z',
        'fc': {
            'variant': 'BTFL',
            'uid': 'deadbeef12345678',
            'api_version': '1.45',
            'blackbox_device': 3,
        },
        'file': {'name': 'raw_flash.bbl', 'bytes': 1024, 'sha256': 'abc123'},
        'erase_attempted': True,
        'erase_completed': True,
    }
    (session_dir / 'manifest.json').write_text(json.dumps(manifest))
    (session_dir / 'raw_flash.bbl').write_bytes(b'\x00' * 1024)
    return tmp_path


class TestResolveSessionPath:
    def test_valid_session_id(self, tmp_path):
        path = _resolve_session_path(tmp_path, 'fc_BTFL_uid-abc/2026-01-01_120000')
        assert path == tmp_path / 'fc_BTFL_uid-abc' / '2026-01-01_120000'

    def test_rejects_path_traversal(self, tmp_path):
        with pytest.raises(_HTTPError) as exc:
            _resolve_session_path(tmp_path, '../etc/passwd')
        assert exc.value.code == 400

    def test_rejects_dotdot_in_parts(self, tmp_path):
        with pytest.raises(_HTTPError) as exc:
            _resolve_session_path(tmp_path, 'fc_dir/../../../etc')
        assert exc.value.code == 400

    def test_rejects_single_part(self, tmp_path):
        with pytest.raises(_HTTPError) as exc:
            _resolve_session_path(tmp_path, 'only_one_part')
        assert exc.value.code == 400


class TestRenderIndex:
    def test_renders_html(self, storage):
        html = _render_index(storage)
        assert 'Betaflight Blackbox Syncer' in html
        assert 'fc_BTFL_uid-deadbeef' in html
        assert 'Download .bbl' in html

    def test_empty_storage(self, tmp_path):
        html = _render_index(tmp_path)
        assert 'No sessions yet' in html

    def test_nonexistent_storage(self, tmp_path):
        html = _render_index(tmp_path / 'nonexistent')
        assert 'No sessions yet' in html
