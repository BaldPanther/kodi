# -*- coding: utf-8 -*-
"""Запросы к Twitch и сборка списка фрагментов исходника записи.

Модуль не зависит от Kodi, его можно запускать и проверять на обычном Python 3.
"""

import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"  # публичный идентификатор веб-плеера Twitch
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
TIMEOUT = 15
CA_FILE = None  # путь к cacert.pem; задаёт обёртка Kodi

_LOGIN_RE = re.compile(r"^[a-z0-9_]{2,25}$")

_CHANNEL_QUERY = """query($login: String!, $n: Int!) {
  user(login: $login) {
    login displayName profileImageURL(width: 300)
    stream { id title createdAt game { displayName } }
    videos(first: $n, type: ARCHIVE, sort: TIME) { edges { node {
      id title publishedAt lengthSeconds status
      previewThumbnailURL(width: 640, height: 360) seekPreviewsURL animatedPreviewURL
      game { displayName }
    } } }
  }
}"""

_VIDEO_QUERY = """query($id: ID!) {
  video(id: $id) {
    id status seekPreviewsURL animatedPreviewURL
    previewThumbnailURL(width: 640, height: 360)
  }
}"""

_TOKEN_QUERY = """query($id: ID!) {
  videoPlaybackAccessToken(id: $id, params: {platform: "web", playerBackend: "mediaplayer", playerType: "site"}) {
    value signature
  }
}"""

_context = None


class TwitchError(Exception):
    pass


def _ssl_context():
    global _context
    if _context is None:
        try:
            _context = ssl.create_default_context(cafile=CA_FILE) if CA_FILE else ssl.create_default_context()
        except Exception:
            _context = ssl.create_default_context()
    return _context


def _open(url, data=None, headers=None):
    request_headers = {"User-Agent": USER_AGENT}
    request_headers.update(headers or {})
    request = urllib.request.Request(url, data=data, headers=request_headers)
    with urllib.request.urlopen(request, timeout=TIMEOUT, context=_ssl_context()) as response:
        return response.read().decode("utf-8", "replace")


def gql(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    try:
        text = _open("https://gql.twitch.tv/gql", data=body,
                     headers={"Client-ID": CLIENT_ID, "Content-Type": "application/json"})
    except (urllib.error.URLError, OSError) as error:
        raise TwitchError("gql: %s" % error)
    result = json.loads(text)
    if result.get("errors"):
        raise TwitchError("gql: %s" % result["errors"][0].get("message"))
    return result.get("data") or {}


def normalize_login(text):
    """Имя канала из того, что ввёл человек: имя, @имя или ссылка на канал."""
    text = (text or "").strip().lower()
    match = re.search(r"twitch\.tv/([a-z0-9_]+)", text)
    if match:
        text = match.group(1)
    text = text.lstrip("@")
    return text if _LOGIN_RE.match(text) else None


def source_base(video):
    """Адрес папки записи на сервере Twitch или None."""
    for key in ("seekPreviewsURL", "animatedPreviewURL"):
        match = re.match(r"https://([^/]+)/([^/]+)/storyboards/", video.get(key) or "")
        if match:
            return "https://%s/%s/" % match.groups()
    match = re.match(r"https://static-cdn\.jtvnw\.net/cf_vods/([^/]+)/([^/]+)/",
                     video.get("previewThumbnailURL") or "")
    if match:
        return "https://%s.cloudfront.net/%s/" % match.groups()
    return None


def channel(login, limit=30):
    """Канал со списком записей. None, если такого канала нет."""
    user = gql(_CHANNEL_QUERY, {"login": login, "n": limit}).get("user")
    if not user:
        return None
    stream = user.get("stream")
    videos = []
    for edge in ((user.get("videos") or {}).get("edges") or []):
        node = edge.get("node") or {}
        videos.append({
            "id": node.get("id"),
            "title": node.get("title") or "",
            "published": node.get("publishedAt") or "",
            "length": node.get("lengthSeconds") or 0,
            "recording": node.get("status") == "RECORDING",
            "thumb": node.get("previewThumbnailURL") or "",
            "game": (node.get("game") or {}).get("displayName") or "",
            "has_source": source_base(node) is not None,
        })
    return {
        "login": user.get("login") or login,
        "name": user.get("displayName") or login,
        "avatar": user.get("profileImageURL") or "",
        "live": bool(stream),
        "stream_title": (stream or {}).get("title") or "",
        "stream_game": ((stream or {}).get("game") or {}).get("displayName") or "",
        "live_thumb": "https://static-cdn.jtvnw.net/previews-ttv/live_user_%s-640x360.jpg" % (user.get("login") or login),
        "videos": videos,
    }


def video_base(video_id):
    """Адрес папки записи по её номеру или None."""
    video = gql(_VIDEO_QUERY, {"id": str(video_id)}).get("video")
    return source_base(video) if video else None


def official_url(video_id):
    """Обычный список качеств Twitch — запасной путь, если исходник недоступен."""
    token = gql(_TOKEN_QUERY, {"id": str(video_id)}).get("videoPlaybackAccessToken")
    if not token:
        raise TwitchError("no playback token")
    query = urllib.parse.urlencode({
        "sig": token["signature"], "token": token["value"], "allow_source": "true",
        "allow_audio_only": "true", "player": "twitchweb", "playlist_include_framerate": "true",
    })
    return "https://usher.ttvnw.net/vod/%s.m3u8?%s" % (video_id, query)


def source_url(base):
    return base + "chunked/index-dvr.m3u8"


def rewrite_playlist(text, base, live=False):
    """Список фрагментов исходника, пригодный для плеера.

    Адреса становятся полными. Фрагменты с приглушённым звуком в исходном списке названы
    «N-unmuted», но сервер отдаёт их только как «N-muted». Для идущей трансляции (live=False)
    список закрывается, чтобы плеер видел обычную запись с перемоткой.
    """
    prefix = base + "chunked/"
    lines = []
    ended = False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXT-X-MAP:"):
            line = re.sub(r'URI="([^"]+)"',
                          lambda match: 'URI="%s"' % urllib.parse.urljoin(prefix, match.group(1)), line)
        elif line == "#EXT-X-ENDLIST":
            ended = True
        elif line.startswith("#EXT-X-PLAYLIST-TYPE") and not live:
            line = "#EXT-X-PLAYLIST-TYPE:VOD"
        elif not line.startswith("#"):
            line = urllib.parse.urljoin(prefix, line.replace("-unmuted.", "-muted."))
        lines.append(line)
    if not ended and not live:
        lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


def source_playlist(base, live=False):
    """Скачать и подготовить список фрагментов исходника. None, если исходник недоступен."""
    try:
        text = _open(source_url(base))
    except urllib.error.HTTPError:
        return None
    except (urllib.error.URLError, OSError) as error:
        raise TwitchError("playlist: %s" % error)
    if "#EXTINF" not in text:
        return None
    return rewrite_playlist(text, base, live)
