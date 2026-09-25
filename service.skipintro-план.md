# План на будущее: Kodi service-аддон `service.skipintro` (EDL-first + онлайн-кнопка)

> Статус: **отложено, реализацию пока не начинаем.** Это готовый план, чтобы вернуться к нему,
> когда надумаем. Связано с `EDL-заметки.md` в личных заметках media-toolkit (`notes/`, раздел
> «Идея собственного Kodi-аддона»).

## Зачем

Утилита [media-toolkit](https://github.com/BaldPanther/media-toolkit) локально генерирует `.edl` рядом с видео
(`episode.mkv` → `episode.edl`, action `3`), и Kodi по ним **сам тихо авто-пропускает**
интро/титры — для коллекционной библиотеки это уже работает.

Не хватает пропуска для **проходного контента** (посмотрел и удалил), под который `.edl` не
генерировали. Гибридный service-аддон закрывает это:

- **Локальный `.edl` есть → аддон молчит.** Приоритет у точных локальных таймингов, Kodi
  авто-пропускает нативно, аддон не вмешивается и свою кнопку не показывает.
- **Локального `.edl` нет → аддон идёт в TheIntroDB** по TMDb/IMDb ID тайтла и, если находит
  тайминги, показывает экранную **кнопку «Пропустить»** (Netflix-стиль).

Смысл делать своё, а не брать готовый `plugin.video.tidb`: ни один существующий аддон не уступает
локальным `.edl` — они бы дублировали/конфликтовали с нативным EDL-пропуском. Наш — уступает.

Решения (сессия 2026-07-02): онлайн-источник — **только TheIntroDB (TMDb/IMDb)** (AniSkip пока
не делаем — ему нужен MyAnimeList ID, которого у Kodi нет); при наличии `.edl` — **молчать**.

## Куда кладём

Внутрь этого репозитория (`d:\Projects\AI\kodi\`) новой папкой верхнего уровня — генератор
`_repo_generator.py` подхватит её автоматически. Образец структуры и стиля кода —
`script.localartrefresh\` (JSON-RPC хелпер `rpc()` в `script.localartrefresh\default.py:67-78`).

id: **`service.skipintro`** (легко переименовать). Тип — `xbmc.service`, Kodi 19+.

> Лицензия: `plugin.video.tidb` — **GPLv3**. Его код НЕ копируем — пишем оригинально по
> задокументированному API и стандартным паттернам Kodi, чтобы остаться на MIT (как весь репо).

## Поведение (спека)

Service стартует с Kodi, держит `xbmc.Monitor` + подкласс `xbmc.Player`. По началу
воспроизведения (`onAVStarted`/`onPlayBackStarted`):

1. Путь текущего файла (`Player.getPlayingFile()` / JSON-RPC `Player.GetItem` → `file`).
2. **EDL-гейт:** сиблинг `<путь без расширения>.edl`, проверка `xbmcvfs.exists()`. Есть →
   **ничего не делаем**, выходим (Kodi авто-пропустит сам). Отражает `edl.py:143 edl_path`
   (with_suffix `.edl`) и `edl.py:147 has_external_edl`.
3. Нет `.edl` → ID и номера серии через JSON-RPC `Player.GetItem` (properties `uniqueid`,
   `imdbnumber`, `season`, `episode`, `type`), фолбэк — `player.getVideoInfoTag()`
   (`getUniqueID('tmdb')`, `getIMDBNumber()`, `getSeason/getEpisode`). Приоритет ID:
   TMDb (`uniqueid['tmdb']`/`'themoviedb'`) → IMDb (`tt…`). Библиотека заполняется через
   tinyMediaManager `.nfo`, где эти ID есть — матчинг рабочий.
4. Запрос к TheIntroDB:
   `GET https://api.theintrodb.org/v3/media?tmdb_id=<id>&season=<s>&episode=<e>&duration_ms=<dur>`
   (для фильмов — без season/episode; `imdb_id=` если нет tmdb). **Ключ для чтения не нужен.**
   Ответ JSON: `intro[]`, `recap[]`, `credits[]`, `preview[]`; поля `start_ms`/`end_ms` (могут
   быть `null`), `confidence`. Переводим в секунды (÷1000). `null end` у credits = до конца.
5. Мониторим позицию (`waitForAbort(1.0)` + `player.getTime()`). Текущее время попало в окно
   сегмента → показываем оверлей-кнопку. Клик → `player.seekTime(segment_end + skip_offset)`.
   Оверлей авто-скрывается через N сек (дефолт 6) или когда сегмент пройден/плеер остановлен.

Сегменты по умолчанию: **intro + credits + recap** (кнопки «Пропустить …»). `preview` — выкл.
Опция авто-скипа без кнопки — есть, но дефолт — именно кнопка.

## Файлы (создать в `service.skipintro\`)

- **`addon.xml`** — `<extension point="xbmc.service" library="service.py" start="startup"/>`,
  `<import addon="xbmc.python" version="3.0.0"/>`, двуязычные `summary`/`description`
  (en_GB + ru_RU), `<platform>all</platform>`, `<license>MIT</license>`, `provider-name="BaldPanther"`.
- **`service.py`** — точка входа: `SkipMonitor(xbmc.Monitor)` + `SkipPlayer(xbmc.Player)`;
  EDL-гейт, запуск запроса, цикл поллинга, показ/скрытие оверлея. Импортирует `xbmc*`.
- **`introdb.py`** — HTTP-клиент к TheIntroDB на stdlib **`urllib.request`** (без внешних
  зависимостей): URL, GET, разбор JSON в сегменты `(kind, start_s, end_s)`; rate-limit ≥0.4 c,
  обработка 404 (нет в базе) и 429 (`Retry-After`); лёгкий in-memory кэш на сессию.
  **Без `import xbmc`** → тестируется headless.
- **`logic.py`** — чистые функции: `edl_sidecar(path)`, парсинг ответа TheIntroDB,
  `active_segment(now, segments)`, выбор ID из словаря uniqueid. **Без `import xbmc`** → тесты.
- **`kodi_rpc.py`** — `rpc()` (по образцу `script.localartrefresh\default.py:67`) +
  `get_playing_item()`. Импортирует `xbmc`.
- **`overlay.py`** — `SkipOverlay(xbmcgui.WindowXMLDialog)`: skin XML, кнопка, `onClick`/`onAction`
  (SELECT → скип, BACK → закрыть), авто-скрытие по таймеру.
- **`resources/skins/Default/1080i/SkipButton.xml`** — `<group>` в правом-нижнем углу, фон +
  `<button>` (default control) с меткой сегмента, лёгкая анимация появления. (720p при желании.)
- **`resources/settings.xml`** — тумблеры: `introdb_enabled`, `enable_intro`/`enable_credits`/
  `enable_recap`, `auto_skip` (дефолт off), `skip_offset` (сек, дефолт 2), `button_timeout`
  (сек, дефолт 6), `debug_logging`.
- **`resources/language/resource.language.en_gb/strings.po`** и `…ru_ru/strings.po` — метки
  настроек и кнопок («Skip intro»/«Пропустить интро», «Skip credits»/«Пропустить титры», …).
- **`resources/icon.png`** — простая иконка (можно позже).
- **`README.md`** — что делает, EDL-приоритет, установка, настройки.

## Проверка (когда будем делать)

1. `python -m py_compile service.py introdb.py logic.py kodi_rpc.py overlay.py`.
2. Headless-тесты чистой логики (`tests/`, без Kodi): `logic.edl_sidecar` (`a/b.mkv`→`a/b.edl`);
   разбор JSON TheIntroDB (мс→сек, `null end`, выбор сегментов); `active_segment` на границах окон;
   выбор TMDb→IMDb из uniqueid.
3. Живой запрос к API (разово, вне Kodi):
   `curl "https://api.theintrodb.org/v3/media?tmdb_id=<известный сериал>&season=1&episode=1"` —
   подтвердить формат ответа перед вшиванием парсера (исследование бралось из исходников
   клиентов, не из «живого» ответа).
4. Сборка: `python _repo_generator.py` — новый аддон должен спаковаться в `repo/`.
5. В Kodi:
   - Эпизод **с** локальным `.edl` → кнопки НЕТ, тихий авто-пропуск работает как раньше;
     в `xbmc.log` строка вида `[service.skipintro] local .edl found → staying silent`.
   - Эпизод **без** `.edl`, который есть в TheIntroDB (мейнстрим-сериал с TMDb ID) → на интро
     появляется кнопка «Пропустить интро», клик перематывает за интро; аналогично титры.
   - Контента нет в базе → тихо, без кнопки (ожидаемо; для зап. мультсериалов часто так).

## Release (когда проверено)

По циклу из `README.md`: версия в `addon.xml` → `python _repo_generator.py` →
`git add -A && git commit -m "add: service.skipintro vX.Y.Z" && git push`.

## Каветы

- TheIntroDB для западных мультсериалов слабый — кнопка часто не появится (ожидаемо; аддон полезен
  в основном для мейнстрим-сериалов/фильмов из проходного контента). Коллекция закрыта локальными `.edl`.
- Нативный EDL-авто-скип Kodi (action 3) должен быть включён в настройках Kodi — у пользователя уже
  работает, аддон на это не влияет.
- Точность TheIntroDB зависит от TMDb ID в библиотеке (есть, т.к. заполняется через tMM/.nfo).
- API молодой/меняется — версия зашита в путь (`/v3`), парсер делаем терпимым к отсутствующим полям.

## Факты по TheIntroDB (из веб-исследования, 2026-07)

- API жив, base `https://api.theintrodb.org/v3`, endpoint `GET /media`, **ключ для чтения не нужен**
  (нужен только для `POST /submit`).
- Тайминги в **миллисекундах**, сегменты `intro/recap/credits/preview` (каждый — массив).
- Матчинг: TMDb ID приоритет → IMDb (`tt…`) + season/episode → TVDB (менее точно).
- Референс: `github.com/TheIntroDB/kodi-addon` (`plugin.video.tidb`, **GPLv3**) — service-аддон,
  Monitor-поллинг раз в 1 с, кнопка через `WindowXMLDialog`, перемотка `player.seekTime()`,
  HTTP на `urllib` без внешних зависимостей. Код не копируем (лицензия) — берём как ориентир.
