# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, unicode_literals

import json
import os
import sys

import xbmc
import xbmcgui
import xbmcvfs

try:
    from urllib.parse import unquote
except ImportError:
    from urllib import unquote


ADDON_NAME = "Local Artwork Refresh"
ART_TYPES = {
    "poster": [
        "poster.jpg", "poster.jpeg", "poster.png",
        "folder.jpg", "folder.jpeg", "folder.png",
        "{base}-poster.jpg", "{base}-poster.jpeg", "{base}-poster.png",
    ],
    "fanart": [
        "fanart.jpg", "fanart.jpeg", "fanart.png",
        "background.jpg", "background.jpeg", "background.png",
        "{base}-fanart.jpg", "{base}-fanart.jpeg", "{base}-fanart.png",
    ],
    "clearlogo": [
        "clearlogo.png", "clearlogo.jpg",
        "logo.png", "logo.jpg",
        "{base}-clearlogo.png", "{base}-clearlogo.jpg",
    ],
    "clearart": [
        "clearart.png", "clearart.jpg",
        "{base}-clearart.png", "{base}-clearart.jpg",
    ],
    "landscape": [
        "landscape.jpg", "landscape.jpeg", "landscape.png",
        "{base}-landscape.jpg", "{base}-landscape.jpeg", "{base}-landscape.png",
    ],
    "banner": [
        "banner.jpg", "banner.jpeg", "banner.png",
        "{base}-banner.jpg", "{base}-banner.jpeg", "{base}-banner.png",
    ],
    "discart": [
        "disc.png", "discart.png", "cdart.png",
        "{base}-disc.png", "{base}-discart.png", "{base}-cdart.png",
    ],
    "keyart": [
        "keyart.jpg", "keyart.jpeg", "keyart.png",
        "{base}-keyart.jpg", "{base}-keyart.jpeg", "{base}-keyart.png",
    ],
}


def log(message):
    xbmc.log("[{}] {}".format(ADDON_NAME, message), xbmc.LOGINFO)


def notify(message, icon=xbmcgui.NOTIFICATION_INFO, seconds=5000):
    xbmcgui.Dialog().notification(ADDON_NAME, message, icon, seconds)


def rpc(method, params=None):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or {},
    }
    raw = xbmc.executeJSONRPC(json.dumps(payload))
    data = json.loads(raw)
    if "error" in data:
        raise RuntimeError("{}: {}".format(method, data["error"]))
    return data.get("result")


def get_movies():
    result = rpc("VideoLibrary.GetMovies", {
        "properties": ["title", "file", "art"],
        "sort": {"method": "title", "order": "ascending"},
    })
    return result.get("movies", []) if result else []


def path_dirname(path):
    normalized = path.replace("\\", "/")
    if normalized.endswith("/"):
        return normalized.rstrip("/")
    index = normalized.rfind("/")
    return normalized[:index] if index >= 0 else ""


def path_basename_without_extension(path):
    normalized = path.replace("\\", "/").rstrip("/")
    name = normalized.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[0] if "." in name else name


def join_path(folder, name):
    if folder.endswith("/") or folder.endswith("\\"):
        return folder + name
    return folder + "/" + name


def find_local_art(movie):
    movie_file = movie.get("file") or ""
    folder = path_dirname(movie_file)
    base = path_basename_without_extension(movie_file)
    if not folder:
        return {}

    found = {}
    for art_type, names in ART_TYPES.items():
        for candidate in names:
            path = join_path(folder, candidate.format(base=base))
            if xbmcvfs.exists(path):
                found[art_type] = path
                break
    return found


def normalize_texture_url(url):
    if not url:
        return ""

    text = url.strip()
    if text.startswith("image://") and text.endswith("/"):
        text = unquote(text[len("image://"):-1])
    return text.rstrip("/")


def texture_url_variants(url):
    normalized = normalize_texture_url(url)
    values = set()
    for value in (url, normalized):
        if value:
            values.add(value)
            values.add(value.rstrip("/"))
            values.add("image://{}/".format(value.rstrip("/")))
    return values


def build_texture_index():
    result = rpc("Textures.GetTextures", {"properties": ["url", "cachedurl"]})
    textures = result.get("textures", []) if result else []
    index = {}
    for texture in textures:
        texture_id = texture.get("textureid")
        url = texture.get("url")
        if texture_id is None or not url:
            continue
        for variant in texture_url_variants(url):
            index.setdefault(variant, set()).add(texture_id)
    return index


def remove_texture_ids(texture_ids):
    removed = 0
    for texture_id in sorted(texture_ids):
        try:
            rpc("Textures.RemoveTexture", {"textureid": texture_id})
            removed += 1
        except Exception as exc:
            log("Failed to remove texture {}: {}".format(texture_id, exc))
    return removed


def collect_texture_ids(texture_index, urls):
    texture_ids = set()
    for url in urls:
        for variant in texture_url_variants(url):
            texture_ids.update(texture_index.get(variant, set()))
    return texture_ids


def set_movie_art(movie_id, art):
    rpc("VideoLibrary.SetMovieDetails", {
        "movieid": movie_id,
        "art": art,
    })


def refresh_from_local_files(movies, dry_run=False):
    progress = xbmcgui.DialogProgress()
    progress.create(ADDON_NAME, "Ищу локальные картинки фильмов")

    texture_index = build_texture_index()
    updated_movies = 0
    changed_art = 0
    removed_textures = 0

    total = max(len(movies), 1)
    for index, movie in enumerate(movies):
        if progress.iscanceled():
            break

        title = movie.get("title") or "Movie {}".format(movie.get("movieid"))
        progress.update(int(index * 100 / total), title)

        local_art = find_local_art(movie)
        if not local_art:
            continue

        current_art = movie.get("art") or {}
        updates = {}
        urls_to_uncache = []
        for art_type, new_url in local_art.items():
            old_url = current_art.get(art_type)
            if old_url != new_url:
                updates[art_type] = new_url
                if old_url:
                    urls_to_uncache.append(old_url)
                urls_to_uncache.append(new_url)

        if not updates:
            # Same file path, but the file may have been replaced on disk.
            urls_to_uncache.extend(local_art.values())
        elif not dry_run:
            set_movie_art(movie["movieid"], updates)
            updated_movies += 1
            changed_art += len(updates)

        if urls_to_uncache and not dry_run:
            texture_ids = collect_texture_ids(texture_index, urls_to_uncache)
            removed_textures += remove_texture_ids(texture_ids)

    progress.close()
    return updated_movies, changed_art, removed_textures


def refresh_current_cache(movies, dry_run=False):
    progress = xbmcgui.DialogProgress()
    progress.create(ADDON_NAME, "Сбрасываю кэш текущих картинок")

    texture_index = build_texture_index()
    removed_textures = 0
    matched_movies = 0

    total = max(len(movies), 1)
    for index, movie in enumerate(movies):
        if progress.iscanceled():
            break

        title = movie.get("title") or "Movie {}".format(movie.get("movieid"))
        progress.update(int(index * 100 / total), title)

        art = movie.get("art") or {}
        urls = [value for value in art.values() if value]
        texture_ids = collect_texture_ids(texture_index, urls)
        if not texture_ids:
            continue

        matched_movies += 1
        if not dry_run:
            removed_textures += remove_texture_ids(texture_ids)

    progress.close()
    return matched_movies, removed_textures


def main():
    dialog = xbmcgui.Dialog()
    action = dialog.select(ADDON_NAME, [
        "Обновить фильмы из локальных poster/fanart файлов",
        "Только сбросить кэш текущих картинок фильмов",
        "Пробный запуск: найти локальные картинки без изменений",
    ])
    if action < 0:
        return

    movies = get_movies()
    if not movies:
        notify("Фильмы в медиатеке не найдены", xbmcgui.NOTIFICATION_WARNING)
        return

    try:
        if action == 0:
            updated, art_count, textures = refresh_from_local_files(movies)
            message = "Фильмов: {}, art: {}, кэш: {}".format(updated, art_count, textures)
        elif action == 1:
            matched, textures = refresh_current_cache(movies)
            message = "Фильмов с кэшем: {}, удалено: {}".format(matched, textures)
        else:
            updated, art_count, textures = refresh_from_local_files(movies, dry_run=True)
            message = "Пробный запуск завершён"

        xbmc.executebuiltin("Container.Refresh")
        notify(message)
        log(message)
    except Exception as exc:
        log("Error: {}".format(exc))
        dialog.ok(ADDON_NAME, "Ошибка: {}".format(exc))
        raise


if __name__ == "__main__":
    main()
