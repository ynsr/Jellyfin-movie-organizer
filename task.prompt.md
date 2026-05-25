## Task Title: IMDB ID Handling and Resource Renaming


## Task Description:

Tasks:
1. If the video file name contains `[tmdbid-{SOME_TMDB_ID}]` which indicates an ID from www.themoviedb.org, ignore searching for
IMDB ID.
2. If the video file name is in this format: `{MOVIE_OR_SERIES_NAME} ({MOVIE_OR_SERIES_YEAR})` without any ID, if there are any poster, backdrop, or NFO files in the same directory with same name as vidoe file, when the IMDB ID detected, also rename those resources.
3. When downloading a movie or series from Filimo, search for its IMDB ID and use it in the file or directory name(s) with Jellyfin-compatibility in mind.

## Context:

- Related Files/Resources:
    - Whole codebase
