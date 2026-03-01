"""Tests for web server routes."""

import io
import json
from unittest.mock import patch

import pytest

from bbsyncer.web import server as web_server_module
from bbsyncer.web.server import (
    _HTTPError,
    _make_handler,
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

    def test_settings_link_in_header(self, storage):
        html = _render_index(storage)
        assert '/settings' in html


class _FakeRequest(io.BytesIO):
    """Minimal request object for BaseHTTPRequestHandler."""

    def makefile(self, *args, **kwargs):
        return self


class _FakeWfile(io.BytesIO):
    """Writable file for capturing handler output."""

    pass


def _make_request_handler(storage_path, method, path, body=b'', headers=None):
    """Create a handler instance and invoke the given HTTP method."""
    handler_cls = _make_handler(storage_path)

    # Build raw HTTP request (headers only, without request line — parse_request
    # reads headers from rfile after raw_requestline is already consumed).
    request_line = f'{method} {path} HTTP/1.1\r\n'
    header_lines = f'Host: localhost\r\nContent-Length: {len(body)}\r\n'
    if headers:
        for k, v in headers.items():
            header_lines += f'{k}: {v}\r\n'
    headers_bytes = (header_lines + '\r\n').encode()

    wfile = _FakeWfile()

    # Suppress log output
    with patch.object(handler_cls, 'log_message', lambda *a, **kw: None):
        handler = handler_cls.__new__(handler_cls)
        handler.rfile = io.BufferedReader(io.BytesIO(headers_bytes))
        handler.wfile = wfile
        handler.client_address = ('127.0.0.1', 12345)
        handler.server = type('FakeServer', (), {'server_name': 'localhost', 'server_port': 80})()

        handler.raw_requestline = (request_line.strip() + '\r\n').encode()
        handler.parse_request()

        # Re-wrap rfile with remaining body
        handler.rfile = io.BytesIO(body)

        getattr(handler, f'do_{method}')()

    wfile.seek(0)
    return wfile.read().decode('utf-8', errors='replace')


class TestSettingsPage:
    def test_settings_page_renders(self, tmp_path):
        with patch(
            'bbsyncer.web.server._read_hostapd_config',
            return_value={'ssid': 'TestNet', 'wpa_passphrase': 'secret123'},
        ):
            response = _make_request_handler(str(tmp_path), 'GET', '/settings')
        assert '200' in response.split('\r\n')[0]
        assert 'Settings' in response
        assert 'TestNet' in response
        assert 'form' in response.lower()

    def test_settings_post_validates_ssid(self, tmp_path):
        body = b'ssid=&password=validpass1'
        with patch('bbsyncer.web.server._read_hostapd_config', return_value={}):
            response = _make_request_handler(
                str(tmp_path),
                'POST',
                '/settings',
                body=body,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
            )
        assert '400' in response.split('\r\n')[0]
        assert 'SSID must be' in response

    def test_settings_post_validates_password(self, tmp_path):
        body = b'ssid=ValidSSID&password=short'
        with patch('bbsyncer.web.server._read_hostapd_config', return_value={}):
            response = _make_request_handler(
                str(tmp_path),
                'POST',
                '/settings',
                body=body,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
            )
        assert '400' in response.split('\r\n')[0]
        assert 'Password must be' in response

    def test_settings_post_success(self, tmp_path):
        body = b'ssid=NewNetwork&password=securepass123'
        with (
            patch('bbsyncer.web.server._read_hostapd_config', return_value={}),
            patch('bbsyncer.web.server._update_config_file', return_value=True) as mock_update,
            patch('bbsyncer.web.server.subprocess.run') as mock_run,
        ):
            response = _make_request_handler(
                str(tmp_path),
                'POST',
                '/settings',
                body=body,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
            )
        assert '200' in response.split('\r\n')[0]
        assert 'NewNetwork' in response
        assert 'Settings saved' in response
        assert mock_update.call_count == 3
        mock_run.assert_called_once()
