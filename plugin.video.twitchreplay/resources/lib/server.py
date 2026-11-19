# -*- coding: utf-8 -*-
"""Локальный сервер, который отдаёт плееру подготовленный список фрагментов.

Адрес: http://127.0.0.1:<порт>/v/<номер записи>.m3u8 — запись целиком, с перемоткой.
Параметры: live=1 — идущая трансляция с текущего момента; q=720 (1080, 480, 360) — качество
не выше указанного, без q или q=source — исходник.
Не зависит от Kodi.
"""

import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import twitch

PORT_PROPERTY = "twitchreplay.port"  # свойство главного окна Kodi, в котором служба сообщает свой порт

_PATH_RE = re.compile(r"^/v/(\d+)\.m3u8$")


class _Handler(BaseHTTPRequestHandler):
    def _match(self):
        parts = urlsplit(self.path)
        match = _PATH_RE.match(parts.path)
        if not match:
            self.send_error(404)
            return None
        query = parse_qs(parts.query)
        quality = (query.get("q") or ["source"])[0]
        if quality not in twitch.QUALITIES:
            quality = "source"
        return match.group(1), query.get("live") == ["1"], quality

    def do_HEAD(self):
        if self._match():
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.apple.mpegurl")
            self.end_headers()

    def do_GET(self):
        found = self._match()
        if not found:
            return
        video_id, live, quality = found
        try:
            playlist = self.server.playlist(video_id, live, quality)
            if playlist is None:
                # папки записи недоступны — отправляем плеер к обычному списку качеств Twitch
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
        self._renditions = {}

    def playlist(self, video_id, live, quality):
        base = self._bases.get(video_id)
        if base is None:
            base = twitch.video_base(video_id)
            if base is None:
                return None
            self._bases[video_id] = base
        # во время эфира плеер перечитывает список каждые несколько секунд — выбор качества запоминается
        rendition = self._renditions.get((video_id, quality))
        if rendition is None:
            rendition = twitch.pick_rendition(video_id, base, quality)
            self._renditions[(video_id, quality)] = rendition
        playlist = twitch.media_playlist(base, rendition, live)
        if playlist is None and rendition != twitch.SOURCE:
            playlist = twitch.media_playlist(base, twitch.SOURCE, live)
        return playlist


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
