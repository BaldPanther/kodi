# -*- coding: utf-8 -*-
"""Служба: держит локальный сервер со списками фрагментов, пока работает Kodi."""

import os

import xbmc
import xbmcgui
import xbmcvfs

from resources.lib import server, twitch


def main():
    ca_file = xbmcvfs.translatePath("special://xbmc/system/certs/cacert.pem")
    if os.path.isfile(ca_file):
        twitch.CA_FILE = ca_file
    httpd = server.start()
    window = xbmcgui.Window(10000)
    window.setProperty(server.PORT_PROPERTY, str(httpd.server_address[1]))
    xbmc.log("[Replay] server on port %s" % httpd.server_address[1], xbmc.LOGINFO)
    xbmc.Monitor().waitForAbort()
    window.clearProperty(server.PORT_PROPERTY)
    server.stop(httpd)


if __name__ == "__main__":
    main()
