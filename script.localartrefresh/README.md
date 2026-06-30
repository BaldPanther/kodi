# Local Artwork Refresh

Kodi script add-on for Android TV and other platforms.

## What it does

- Reads all movies from the Kodi video library.
- Looks for local artwork files next to each movie file.
- Updates movie artwork links through `VideoLibrary.SetMovieDetails`.
- Removes matching texture-cache entries through `Textures.RemoveTexture`.

It does not delete `Textures*.db` or the whole `Thumbnails` directory.

## Modes

1. `Обновить фильмы из локальных poster/fanart файлов`
   - Use this when Kodi still points to scraped/old artwork and you now have local files next to movies.

2. `Только сбросить кэш текущих картинок фильмов`
   - Use this when the artwork path is already correct, but the image file was replaced and Kodi still shows the old cached image.

3. `Пробный запуск`
   - Reads the library and searches local artwork without changing Kodi data.

## Local filenames

The add-on checks common Kodi artwork names, including:

- `poster.jpg`, `poster.png`, `folder.jpg`
- `fanart.jpg`, `fanart.png`, `background.jpg`
- `clearlogo.png`, `clearart.png`
- `landscape.jpg`, `banner.jpg`
- `disc.png`, `discart.png`, `keyart.jpg`
- movie-name variants such as `Movie Name-poster.jpg`

