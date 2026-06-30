# Bald Panther — Kodi repository

Личный репозиторий аддонов Kodi. Один репозиторий — много аддонов, со встроенным авто-обновлением.

## Аддоны
- **script.localartrefresh** — Local Artwork Refresh: обновление постеров/фанарта фильмов из локальных файлов + точечный сброс texture-cache.

## Установка (один раз, в т.ч. для родителей)

1. Kodi → **Settings → System → Add-ons** → включить **Unknown sources**.
2. Скачать zip репозитория:
   `https://baldpanther.github.io/kodi/repo/repository.baldpanther/repository.baldpanther-1.0.0.zip`
3. Kodi → **Add-ons → Install from zip file** → выбрать скачанный zip.
4. **Install from repository → Bald Panther Repository → Add-ons** → поставить нужный аддон.

Дальше Kodi обновляет аддоны автоматически (проверка ~раз в сутки; можно принудительно — «Check for updates» в репозитории).

> На приставке (Android TV / MiTV) zip можно залить через adb (см. `desk/tv`) или скачать браузером прямо на устройство.

## Разработка

Структура:
```
<addon.id>/                 исходник аддона (addon.xml + код)
repository.baldpanther/     аддон-репозиторий (ссылки на каталог)
repo/                       раздаётся через GitHub Pages (zip + addons.xml + md5)
_repo_generator.py          пересборка repo/
```

Цикл выпуска новой версии:
1. Поднять `version` в `<addon.id>/addon.xml`.
2. `python _repo_generator.py`
3. `git add -A && git commit -m "update: <addon> vX.Y.Z" && git push`

Хостинг — **GitHub Pages** (Settings → Pages → branch `main`, folder `/`). Обновление публикуется ~за минуту, ручной сброс кэша не нужен.
