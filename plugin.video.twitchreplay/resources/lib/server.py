# -*- coding: utf-8 -*-
"""Локальный сервер, который отдаёт плееру подготовленный список фрагментов.

Адрес: http://127.0.0.1:<порт>/v/<номер записи>.m3u8 — запись целиком, с перемоткой;
с параметром ?live=1 — идущая трансляция с текущего момента.
Не зависит от Kodi.
"""

import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import twitch

PORT_PROPERTY = "twitchreplay.port"  # свойство главного окна Kodi, в котором служба сообщает свой порт

_PATH_RE = re.compile(r"^/v/(\d+)\.m3u8(?:\?(.*))?$")


class _Handler(BaseHTTPRequestHandler):
    def _match(self):
        match = _PATH_RE.match(self.path)
        if not match:
            self.send_error(404)
            return None
        return match.group(1), "live=1" in (match.group(2) or "")

    def do_HEAD(self):
        if self._match():
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.apple.mpegurl")
            self.end_headers()

    def do_GET(self):
        found = self._match()
        if not found:
            return
        video_id, live = found
        try:
            playlist = self.server.playlist(video_id, live)
            if playlist is None:
                # исходника нет — отправляем плеер к обычному списку качеств Twitch
                self.send_response(302)
                self.send_header("Location", twitch.official_url(video_id))
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        except Exception as error:
            self.send_error(502, str(error)[:200])
            return
        body = playlist.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.apple.mpegurl")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address):
        ThreadingHTTPServer.__init__(self, address, _Handler)
        self._bases = {}

    def playlist(self, video_id, live):
        base = self._bases.get(video_id)
        if base is None:
            base = twitch.video_base(video_id)
            if base is None:
                return None
            self._bases[video_id] = base
        return twitch.source_playlist(base, live)


def start(port=0):
    """Запустить сервер в фоновом потоке. Порт 0 — любой свободный."""
    server = _Server(("127.0.0.1", port))
    thread = threading.Thread(target=server.serve_forever, name="twitchreplay-server")
    thread.daemon = True
    thread.start()
    return server


def stop(server):
    server.shutdown()
    server.server_close()
