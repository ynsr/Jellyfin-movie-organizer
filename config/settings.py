"""
Application-wide configuration constants.
All tuneable values live here — do not scatter magic strings in source files.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Supported video extensions
# ---------------------------------------------------------------------------
VIDEO_EXTENSIONS: set[str] = {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"}

# ---------------------------------------------------------------------------
# Jellyfin naming helpers
# ---------------------------------------------------------------------------
JELLYFIN_MOVIE_PATTERN = r"^(?P<name>.+?) \((?P<year>\d{4})\) \[imdbid-(?P<imdb_id>tt\d+)\](?P<suffix>[^.]*)?$"

# ---------------------------------------------------------------------------
# Bertina search engine
# ---------------------------------------------------------------------------
BERTINA_SEARCH_URL = "https://search.bertina.ir/search"
BERTINA_IMDB_QUERY_SUFFIX = "site:www.imdb.com"
BERTINA_DOOSTIHAA_QUERY_SUFFIX = "site:www.doostihaa.com"
BERTINA_FIRST_RESULT_SELECTOR = "article:nth-of-type(1)"

# ---------------------------------------------------------------------------
# Filimo API
# ---------------------------------------------------------------------------
FILIMO_SEARCH_URL = "https://www.filimo.com/api/fa/v1/movie/movie/list/tagid/1000300/text/{query}"
FILIMO_YEAR_TOLERANCE = 1   # Allow ±1 year when matching movie year

# ---------------------------------------------------------------------------
# Doostihaa selectors (in priority order)
# ---------------------------------------------------------------------------
DOOSTIHAA_POSTER_SELECTORS = [
    "#center_sides > article > div.article_txtc > div.textkian0 > p:nth-child(4) > a > img",
    "#center_sides > article > div.article_txtc > div.textkian0 > p:nth-child(3) > a > img",
    "div.textkian0 img",   # broad fallback
]

# ---------------------------------------------------------------------------
# HTTP client settings
# ---------------------------------------------------------------------------
HTTP_TIMEOUT = 20           # seconds
HTTP_MAX_RETRIES = 3
HTTP_BACKOFF_FACTOR = 1.5   # seconds between retries

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fa,en;q=0.9",
}

# ---------------------------------------------------------------------------
# Output / logging
# ---------------------------------------------------------------------------
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "organizer.log"

MISSED_POSTER_FILE = Path("movies-missed-poster.txt")
MISSED_BACKDROP_FILE = Path("movies-missed-backdrop.txt")
MISSED_NFO_FILE = Path("movies-missed-nfo.txt")

# ---------------------------------------------------------------------------
# Filimo Downloader
# ---------------------------------------------------------------------------
FILIMO_MAX_QUALITY_HEIGHT = 1080   # Never download above 1080p (Full HD)
FILIMO_DOWNLOAD_CHUNK_MB  = 4      # Chunk size in MB for resumable downloads
