"""stdlib http.server web server for blackbox log retrieval.

Routes:
  GET  /                          Main UI page
  GET  /sessions                  JSON: all sessions
  GET  /download/<session_id>/raw_flash.bbl
  GET  /download/<session_id>/manifest.json
  GET  /status                    JSON: current sync status
  DELETE /sessions/<session_id>   Delete a session from Pi
  GET  /generate_204              Android captive portal probe
  GET  /hotspot-detect.html       iOS/macOS captive portal probe
  GET  /connecttest.txt           Windows captive portal probe
"""

from __future__ import annotations

import html
import json
import logging
import shutil
import socketserver
import time as _time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from bbsyncer.storage.manifest import list_sessions
from bbsyncer.sync.orchestrator import get_status
from bbsyncer.util.disk_space import used_and_free_gb

log = logging.getLogger(__name__)

_sessions_cache: tuple[float, list] = (0.0, [])
_SESSIONS_TTL = 10.0  # seconds


def _get_sessions(storage: Path) -> list:
    global _sessions_cache
    ts, data = _sessions_cache
    if _time.monotonic() - ts > _SESSIONS_TTL:
        data = list_sessions(storage) if storage.exists() else []
        _sessions_cache = (_time.monotonic(), data)
    return data


_CAPTIVE_PATHS = frozenset(
    {
        '/generate_204',
        '/gen_204',
        '/hotspot-detect.html',
        '/library/test/success.html',
        '/connecttest.txt',
        '/ncsi.txt',
    }
)

_CAPTIVE_HTML = (
    '<!DOCTYPE html><html><head>'
    '<meta http-equiv="refresh" content="0; url=/">'
    '<title>Betaflight Blackbox Syncer</title>'
    '</head><body>'
    '<p>Redirecting to <a href="/">Blackbox Syncer</a>...</p>'
    '</body></html>'
)


class _HTTPError(Exception):
    def __init__(self, code: int) -> None:
        self.code = code


class _ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True


def _e(s: object) -> str:
    """HTML-escape a value for safe inline embedding."""
    return html.escape(str(s))


def _render_sessions(sessions: list) -> str:
    if not sessions:
        return (
            '<div class="empty-state">'
            '<div class="icon">📭</div>'
            '<p>No sessions yet.<br>Plug in a Betaflight FC to start syncing.</p>'
            '</div>'
        )
    parts: list[str] = []
    current_fc: str | None = None
    for i, session in enumerate(sessions):
        fc_dir = session['fc_dir']
        if fc_dir != current_fc:
            if current_fc is not None:
                parts.append('</div></details>')
            current_fc = fc_dir
            parts.append(f'<details class="fc-group" open>\n<summary>{_e(fc_dir)}</summary>\n<div>')

        m = session.get('manifest') or {}
        fc = m.get('fc') or {}
        file_info = m.get('file') or {}
        fc_ver = fc.get('api_version', '?')
        file_size = file_info.get('bytes', 0)
        file_mb = round(file_size / 1048576, 1)
        erased = m.get('erase_completed', False)
        sha256 = file_info.get('sha256', '')
        session_id = session['session_id']
        bbl_path = session.get('bbl_path')

        erased_cls = 'erased' if erased else 'no-erase'
        erased_txt = 'Erased' if erased else 'Not erased'
        sha_html = (
            f'<span title="{_e(sha256)}">SHA-256: {_e(sha256[:12])}…</span>' if sha256 else ''
        )
        bbl_html = (
            f'<a class="btn btn-download" href="/download/{_e(session_id)}/raw_flash.bbl">'
            f'Download .bbl</a>'
            if bbl_path
            else ''
        )
        parts.append(
            f'<div class="session-card">'
            f'<div class="session-header">'
            f'<span class="session-title">{_e(session["session_dir"].replace("_", " "))}</span>'
            f'<span class="badge {erased_cls}">{erased_txt}</span>'
            f'</div>'
            f'<div class="session-meta">'
            f'<span>{file_mb} MB</span>'
            f'<span>API {_e(fc_ver)}</span>'
            f'{sha_html}'
            f'</div>'
            f'<div class="session-actions">'
            f'{bbl_html}'
            f'<a class="btn btn-manifest" href="/download/{_e(session_id)}/manifest.json">Manifest</a>'
            f'<button class="btn-delete" onclick="deleteSession(\'{_e(session_id)}\', this)">'
            f'Delete from Pi</button>'
            f'</div></div>'
        )

        if i == len(sessions) - 1:
            parts.append('</div></details>')

    return '\n'.join(parts)


def _render_index(storage: Path) -> str:
    sessions = _get_sessions(storage)
    try:
        used_gb, free_gb = used_and_free_gb(storage)
    except OSError:
        used_gb, free_gb = 0.0, 0.0
    total_gb = used_gb + free_gb
    pct = int(used_gb / total_gb * 100) if total_gb > 0 else 0
    sessions_html = _render_sessions(sessions)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Betaflight Blackbox Syncer</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      margin: 0; padding: 0;
      background: #0f0f12;
      color: #e0e0e8;
      min-height: 100vh;
    }}
    header {{
      background: #1a1a24;
      border-bottom: 1px solid #2e2e40;
      padding: 14px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: sticky; top: 0; z-index: 100;
    }}
    header h1 {{ margin: 0; font-size: 1.1rem; font-weight: 600; }}
    #status-badge {{
      font-size: 0.75rem;
      padding: 4px 10px;
      border-radius: 12px;
      background: #2e2e40;
      color: #a0a0b8;
    }}
    #status-badge.syncing  {{ background: #1a3a5c; color: #60b0ff; }}
    #status-badge.erasing  {{ background: #3a2a10; color: #ffaa40; }}
    #status-badge.verifying {{ background: #2a1a4a; color: #c060ff; }}
    #status-badge.error    {{ background: #3a1a1a; color: #ff6060; }}
    main {{ max-width: 700px; margin: 0 auto; padding: 16px; }}
    .disk-info {{
      background: #1a1a24;
      border: 1px solid #2e2e40;
      border-radius: 8px;
      padding: 12px 16px;
      margin-bottom: 16px;
      font-size: 0.85rem;
      color: #a0a0b8;
    }}
    .disk-bar-track {{
      background: #2e2e40;
      border-radius: 4px;
      height: 6px;
      margin-top: 6px;
      overflow: hidden;
    }}
    .disk-bar-fill {{
      background: #4060d0;
      height: 100%;
      border-radius: 4px;
      transition: width 0.3s;
    }}
    .fc-group {{ margin-bottom: 20px; }}
    .fc-group summary {{
      cursor: pointer;
      font-size: 0.9rem;
      font-weight: 600;
      color: #c0c0d8;
      padding: 8px 0;
      list-style: none;
      display: flex;
      align-items: center;
      gap: 8px;
      border-bottom: 1px solid #2e2e40;
      user-select: none;
    }}
    .fc-group summary::before {{ content: "▶"; font-size: 0.7rem; transition: transform 0.2s; }}
    .fc-group[open] summary::before {{ transform: rotate(90deg); }}
    .session-card {{
      background: #1a1a24;
      border: 1px solid #2e2e40;
      border-radius: 8px;
      padding: 12px 14px;
      margin-top: 8px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .session-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .session-title {{ font-size: 0.9rem; font-weight: 500; }}
    .session-meta {{ font-size: 0.75rem; color: #808098; display: flex; gap: 10px; flex-wrap: wrap; }}
    .badge {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 8px;
      font-size: 0.7rem;
      background: #2e2e40;
      color: #909098;
    }}
    .badge.erased {{ background: #1a3a1a; color: #60d060; }}
    .badge.no-erase {{ background: #3a2a10; color: #c08030; }}
    .session-actions {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    button, a.btn {{
      display: inline-block;
      padding: 6px 14px;
      border-radius: 6px;
      font-size: 0.8rem;
      cursor: pointer;
      border: none;
      text-decoration: none;
      font-weight: 500;
      transition: opacity 0.15s;
    }}
    button:hover, a.btn:hover {{ opacity: 0.8; }}
    .btn-download {{ background: #2a4a80; color: #a0c8ff; }}
    .btn-manifest {{ background: #2e2e40; color: #a0a0b8; }}
    .btn-delete   {{ background: #4a1a1a; color: #ff8080; }}
    .empty-state {{
      text-align: center;
      padding: 48px 24px;
      color: #505068;
    }}
    .empty-state .icon {{ font-size: 3rem; margin-bottom: 12px; }}
    .progress-bar-track {{
      background: #2e2e40;
      border-radius: 3px;
      height: 4px;
      overflow: hidden;
      display: none;
    }}
    .progress-bar-fill {{
      background: #60b0ff;
      height: 100%;
      width: 0%;
      border-radius: 3px;
      transition: width 0.5s;
    }}
  </style>
</head>
<body>

<header>
  <h1>Betaflight Blackbox Syncer</h1>
  <span id="status-badge">Idle</span>
</header>

<div id="sync-progress-container" style="background:#1a2a3a; padding:0 20px; display:none;">
  <div style="max-width:700px; margin:0 auto; padding:8px 0; font-size:0.8rem; color:#60b0ff;">
    <span id="sync-progress-label">Syncing...</span>
    <div class="progress-bar-track" id="progress-track" style="display:block; margin-top:4px;">
      <div class="progress-bar-fill" id="progress-fill"></div>
    </div>
  </div>
</div>

<main>
  <div class="disk-info">
    <span>Pi SD card: <strong>{used_gb:.1f} GB used</strong> / {free_gb:.1f} GB free</span>
    <div class="disk-bar-track">
      <div class="disk-bar-fill" style="width: {pct}%"></div>
    </div>
  </div>

  {sessions_html}
</main>

<script>
  // Poll sync status every 3 seconds
  function updateStatus() {{
    fetch('/status')
      .then(r => r.json())
      .then(data => {{
        const badge = document.getElementById('status-badge');
        const state = data.state || 'idle';
        const progress = data.progress || 0;
        const labels = {{
          idle: 'Idle', identifying: 'Identifying FC\u2026',
          querying: 'Querying flash\u2026', syncing: 'Syncing\u2026',
          verifying: 'Verifying\u2026', erasing: 'Erasing\u2026', error: 'Error'
        }};
        badge.textContent = (labels[state] || state) +
          (state === 'syncing' && progress > 0 ? ` ${{progress}}%` : '');
        badge.className = '';
        if (['syncing','identifying','querying'].includes(state)) badge.classList.add('syncing');
        else if (state === 'erasing') badge.classList.add('erasing');
        else if (state === 'verifying') badge.classList.add('verifying');
        else if (state === 'error') badge.classList.add('error');

        const progressContainer = document.getElementById('sync-progress-container');
        const progressFill = document.getElementById('progress-fill');
        const progressLabel = document.getElementById('sync-progress-label');
        if (state === 'syncing') {{
          progressContainer.style.display = 'block';
          progressFill.style.width = progress + '%';
          progressLabel.textContent = `Syncing flash... ${{progress}}%`;
        }} else {{
          progressContainer.style.display = 'none';
        }}
      }})
      .catch(() => {{}});
  }}
  updateStatus();
  setInterval(updateStatus, 3000);

  // Delete session
  function deleteSession(sessionId, btn) {{
    if (!confirm('Delete this session from the Pi?\\n\\nMake sure you have downloaded the .bbl file first.')) return;
    btn.disabled = true;
    btn.textContent = 'Deleting\u2026';
    fetch('/sessions/' + sessionId, {{ method: 'DELETE' }})
      .then(r => r.json())
      .then(data => {{
        if (data.deleted) {{
          const card = btn.closest('.session-card');
          card.style.transition = 'opacity 0.3s';
          card.style.opacity = '0';
          setTimeout(() => {{ card.remove(); location.reload(); }}, 300);
        }} else {{
          btn.disabled = false;
          btn.textContent = 'Delete from Pi';
          alert('Delete failed.');
        }}
      }})
      .catch(() => {{
        btn.disabled = false;
        btn.textContent = 'Delete from Pi';
        alert('Delete request failed.');
      }});
  }}
</script>
</body>
</html>"""


def _resolve_session_path(storage: Path, session_id: str) -> Path:
    """Safely resolve a session_id like 'fc_BTFL_uid-abc/2026-02-26_143012'."""
    parts = session_id.split('/')
    if len(parts) != 2:
        raise _HTTPError(400)
    fc_dir, session_dir = parts
    if '..' in fc_dir or '..' in session_dir:
        raise _HTTPError(400)
    try:
        path = storage / fc_dir / session_dir
        path.resolve().relative_to(storage.resolve())
    except ValueError:
        raise _HTTPError(400) from None
    return path


def _resolve_session_file(storage: Path, session_id: str, filename: str) -> Path:
    session_path = _resolve_session_path(storage, session_id)
    file_path = session_path / filename
    if not file_path.exists():
        raise _HTTPError(404)
    return file_path


def _make_handler(storage_path: str) -> type:
    storage = Path(storage_path)

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = self.path.split('?')[0]
            try:
                if path in _CAPTIVE_PATHS:
                    self._send_html(_CAPTIVE_HTML)
                elif path == '/':
                    self._send_html(_render_index(storage))
                elif path == '/sessions':
                    self._send_json(_get_sessions(storage))
                elif path == '/status':
                    self._send_json(get_status())
                elif path.startswith('/download/'):
                    self._handle_download(path[len('/download/') :])
                else:
                    self._send_error_response(404)
            except _HTTPError as exc:
                self._send_error_response(exc.code)
            except Exception:
                log.exception('Unhandled error in GET %s', path)
                self._send_error_response(500)

        def do_DELETE(self) -> None:
            path = self.path.split('?')[0]
            try:
                if path.startswith('/sessions/'):
                    self._handle_delete_session(path[len('/sessions/') :])
                else:
                    self._send_error_response(404)
            except _HTTPError as exc:
                self._send_error_response(exc.code)
            except Exception:
                log.exception('Unhandled error in DELETE %s', path)
                self._send_error_response(500)

        def _handle_download(self, sub_path: str) -> None:
            # sub_path is "<session_id>/<filename>"
            if sub_path.endswith('/raw_flash.bbl'):
                session_id = sub_path[: -len('/raw_flash.bbl')]
                file_path = _resolve_session_file(storage, session_id, 'raw_flash.bbl')
                self._send_file(file_path, 'raw_flash.bbl')
            elif sub_path.endswith('/manifest.json'):
                session_id = sub_path[: -len('/manifest.json')]
                file_path = _resolve_session_file(storage, session_id, 'manifest.json')
                self._send_file(file_path, 'manifest.json')
            else:
                raise _HTTPError(404)

        def _handle_delete_session(self, session_id: str) -> None:
            session_path = _resolve_session_path(storage, session_id)
            if not session_path.exists():
                raise _HTTPError(404)
            shutil.rmtree(session_path)
            global _sessions_cache
            _sessions_cache = (0.0, [])  # invalidate
            log.info('Deleted session: %s', session_path)
            self._send_json({'deleted': True, 'session_id': session_id})

        def _send_html(self, body: str, status: int = 200) -> None:
            data = body.encode()
            self.send_response(status)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, data: object, status: int = 200) -> None:
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_file(self, path: Path, filename: str) -> None:
            size = path.stat().st_size
            range_header = self.headers.get('Range')
            if range_header and range_header.startswith('bytes='):
                try:
                    range_spec = range_header[6:]
                    start_str, end_str = range_spec.split('-', 1)
                    start = int(start_str) if start_str else 0
                    end = int(end_str) if end_str else size - 1
                    end = min(end, size - 1)
                    if start > end or start >= size:
                        self.send_response(416)
                        self.send_header('Content-Range', f'bytes */{size}')
                        self.end_headers()
                        return
                    content_length = end - start + 1
                    self.send_response(206)
                    self.send_header('Content-Type', 'application/octet-stream')
                    self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                    self.send_header('Content-Length', str(content_length))
                    self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
                    self.send_header('Accept-Ranges', 'bytes')
                    self.end_headers()
                    with open(path, 'rb') as f:
                        f.seek(start)
                        remaining = content_length
                        while remaining > 0:
                            chunk = f.read(min(1 << 20, remaining))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
                    return
                except (ValueError, IndexError):
                    pass  # Fall through to full response

            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.send_header('Content-Length', str(size))
            self.send_header('Accept-Ranges', 'bytes')
            self.end_headers()
            with open(path, 'rb') as f:
                while True:
                    chunk = f.read(1 << 20)  # 1 MB
                    if not chunk:
                        break
                    self.wfile.write(chunk)

        def _send_error_response(self, code: int) -> None:
            self.send_response(code)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(f'{code} Error\n'.encode())

        def log_message(self, format: str, *args: object) -> None:
            log.debug('%s %s', self.address_string(), format % args)

    return _Handler


def run_server(storage_path: str = '/mnt/bbsyncer-logs', port: int = 80) -> None:
    """Start the HTTP server."""
    handler = _make_handler(storage_path)
    server = _ThreadedHTTPServer(('0.0.0.0', port), handler)
    log.info('Starting web server on 0.0.0.0:%d', port)
    server.serve_forever()
