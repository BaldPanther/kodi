# -*- coding: utf-8 -*-
"""Replay: записи каналов Twitch в исходном качестве."""

import calendar
import re
import sys
import time
from urllib.parse import parse_qsl, urlencode

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

from resources.lib import twitch
from resources.lib.server import PORT_PROPERTY

ADDON = xbmcaddon.Addon()
ADDON_NAME = ADDON.getAddonInfo("name")
ICON = ADDON.getAddonInfo("icon")
BASE_URL = sys.argv[0]
HANDLE = int(sys.argv[1])


def tr(string_id):
    return ADDON.getLocalizedString(string_id)


def log(message):
    xbmc.log("[{}] {}".format(ADDON_NAME, message), xbmc.LOGINFO)


def notify(message, error=False):
    xbmcgui.Dialog().notification(
        ADDON_NAME, message, xbmcgui.NOTIFICATION_ERROR if error else xbmcgui.NOTIFICATION_INFO)


def build_url(**params):
    return BASE_URL + "?" + urlencode(params)


# --- каналы -----------------------------------------------------------------

def load_channels():
    logins = []
    for part in ADDON.getSetting("channels").split(","):
        login = twitch.normalize_login(part)
        if login and login not in logins:
            logins.append(login)
    return logins


def save_channels(logins):
    ADDON.setSetting("channels", ",".join(logins))


def add_channel(text=None):
    if text is None:
        text = xbmcgui.Dialog().input(tr(30002))
        if not text:
            return
    login = twitch.normalize_login(text)
    found = twitch.channel(login, 1) if login else None
    if not found:
        notify(tr(30003), error=True)
        return
    logins = load_channels()
    if found["login"] not in logins:
        logins.append(found["login"])
        save_channels(logins)
    xbmc.executebuiltin("Container.Refresh")


def remove_channel(login):
    if not xbmcgui.Dialog().yesno(ADDON_NAME, "{} {}?".format(tr(30004), login)):
        return
    save_channels([item for item in load_channels() if item != login])
    xbmc.executebuiltin("Container.Refresh")


# --- качество ---------------------------------------------------------------

QUALITY_LABELS = {"source": 30014, "1080": 30015, "720": 30016, "480": 30017, "360": 30018}


def current_quality():
    value = ADDON.getSetting("quality")
    return value if value in twitch.QUALITIES else "source"


def choose_quality():
    options = [tr(QUALITY_LABELS[value]) for value in twitch.QUALITIES]
    index = xbmcgui.Dialog().select(tr(30013), options, preselect=twitch.QUALITIES.index(current_quality()))
    if index < 0:
        return
    ADDON.setSetting("quality", twitch.QUALITIES[index])
    xbmc.executebuiltin("Container.Refresh")


def add_quality_item():
    label = "[COLOR gray]{}:[/COLOR] {}".format(tr(30013), tr(QUALITY_LABELS[current_quality()]))
    item = folder_item(label)
    item.setProperty("IsPlayable", "false")
    xbmcplugin.addDirectoryItem(HANDLE, build_url(action="quality"), item, isFolder=False)


# --- списки -----------------------------------------------------------------

def format_date(iso):
    """'2026-11-18T15:07:14Z' -> ('18.11.2026', '2026-11-18 19:07:14') по местному времени."""
    numbers = [int(number) for number in re.findall(r"\d+", iso)[:6]]
    if len(numbers) < 6:
        return "", ""
    local = time.localtime(calendar.timegm(tuple(numbers)))
    return time.strftime("%d.%m.%Y", local), time.strftime("%Y-%m-%d %H:%M:%S", local)


def format_length(seconds):
    return "{}:{:02d}".format(int(seconds) // 3600, int(seconds) % 3600 // 60)


def folder_item(label, thumb=None):
    item = xbmcgui.ListItem(label=label, offscreen=True)
    item.setArt({"icon": thumb or ICON, "thumb": thumb or ICON})
    return item


def video_item(label, title, plot, thumb, duration=0, added=""):
    item = xbmcgui.ListItem(label=label, offscreen=True)
    item.setArt({"icon": thumb, "thumb": thumb})
    item.setProperty("IsPlayable", "true")
    try:
        tag = item.getVideoInfoTag()
        tag.setMediaType("video")
        tag.setTitle(title)
        tag.setPlot(plot)
        if duration:
            tag.setDuration(int(duration))
        if added:
            tag.setDateAdded(added)
    except AttributeError:  # Kodi 19
        info = {"mediatype": "video", "title": title, "plot": plot}
        if duration:
            info["duration"] = int(duration)
        if added:
            info["dateadded"] = added
        item.setInfo("video", info)
    return item


def list_root():
    logins = load_channels()
    if len(logins) == 1:
        list_channel(logins[0], with_channels_entry=True)
    else:
        list_channels(logins)


def list_channels(logins=None):
    if logins is None:
        logins = load_channels()
    xbmcplugin.setPluginCategory(HANDLE, tr(30001))
    for login in logins:
        try:
            found = twitch.channel(login, 1)
        except twitch.TwitchError as error:
            log(error)
            found = None
        label = found["name"] if found else login
        if found and found["live"]:
            label = "[COLOR red]●[/COLOR] {}  [COLOR gray]{}[/COLOR]".format(label, tr(30012))
        item = folder_item(label, found["avatar"] if found else None)
        item.addContextMenuItems([
            (tr(30004), "RunPlugin({})".format(build_url(action="remove", login=login))),
        ])
        xbmcplugin.addDirectoryItem(HANDLE, build_url(action="channel", login=login), item, isFolder=True)
    xbmcplugin.addDirectoryItem(HANDLE, build_url(action="add"), folder_item(tr(30000)), isFolder=False)
    add_quality_item()
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)


def list_channel(login, with_channels_entry=False):
    try:
        found = twitch.channel(login)
    except twitch.TwitchError as error:
        log(error)
        notify(tr(30008), error=True)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return
    if not found:
        notify(tr(30003), error=True)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    xbmcplugin.setPluginCategory(HANDLE, found["name"])
    xbmcplugin.setContent(HANDLE, "videos")

    for video in found["videos"]:
        date, added = format_date(video["published"])
        recording = video["recording"]
        thumb = found["live_thumb"] if recording else video["thumb"]
        if recording:
            # идущая трансляция с текущего момента; адрес каждый раз новый, чтобы Kodi
            # не предлагал продолжить с места, которого в эфире уже нет
            title = "{}: {}".format(tr(30005), found["stream_title"] or video["title"])
            item = video_item("[COLOR red]●[/COLOR] " + title, title, tr(30009), thumb)
            url = build_url(action="play", id=video["id"], live=1, t=int(time.time()))
            xbmcplugin.addDirectoryItem(HANDLE, url, item, isFolder=False)

        details = [date, format_length(video["length"])]
        if video["game"]:
            details.append(video["game"])
        if recording:
            details.append(tr(30006))
        label = video["title"]
        if recording:
            label += "  [COLOR gray]{}[/COLOR]".format(tr(30006))
        item = video_item(label, video["title"], " · ".join(details), thumb, video["length"], added)
        item.setLabel2(date)
        xbmcplugin.addDirectoryItem(HANDLE, build_url(action="play", id=video["id"]), item, isFolder=False)

    if not found["videos"]:
        xbmcplugin.addDirectoryItem(HANDLE, build_url(action="none"), folder_item(tr(30007), found["avatar"]),
                                    isFolder=False)
    add_quality_item()
    if with_channels_entry:
        xbmcplugin.addDirectoryItem(HANDLE, build_url(action="channels"), folder_item(tr(30001)), isFolder=True)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)


# --- воспроизведение ---------------------------------------------------------

def play(video_id, live=False):
    port = xbmcgui.Window(10000).getProperty(PORT_PROPERTY)
    quality = current_quality()
    try:
        if port:
            params = {"q": quality}
            if live:
                params["live"] = "1"
            url = "http://127.0.0.1:{}/v/{}.m3u8?{}".format(port, video_id, urlencode(params))
        else:
            # служба не запущена: играем список как есть (участки с приглушённым звуком могут не открыться)
            log("service is not running, playing the playlist directly")
            base = twitch.video_base(video_id)
            if base:
                url = twitch.playlist_url(base, twitch.pick_rendition(video_id, base, quality))
            else:
                url = twitch.official_url(video_id)
    except twitch.TwitchError as error:
        log(error)
        notify(tr(30008), error=True)
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem(offscreen=True))
        return
    item = xbmcgui.ListItem(path=url, offscreen=True)
    item.setMimeType("application/vnd.apple.mpegurl")
    item.setContentLookup(False)
    xbmcplugin.setResolvedUrl(HANDLE, True, item)


def router(query):
    params = dict(parse_qsl(query))
    action = params.get("action")
    if action is None:
        list_root()
    elif action == "channels":
        list_channels()
    elif action == "channel":
        list_channel(params["login"])
    elif action == "add":
        add_channel(params.get("login"))
    elif action == "remove":
        remove_channel(params["login"])
    elif action == "quality":
        choose_quality()
    elif action == "play":
        play(params["id"], live=params.get("live") == "1")


if __name__ == "__main__":
    router(sys.argv[2][1:])
