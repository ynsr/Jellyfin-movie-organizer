"""
Filimo Downloader Service
=========================
Downloads movies AND TV series/episodes directly from Filimo.com.

Movie inputs
------------
  UID      : aVmdY
  Short URL: https://www.filimo.com/m/aVmdY
  Full URL : https://www.filimo.com/m/aVmdY/<persian-slug>

Series inputs
-------------
  Series ID  : 99963
  Short URL  : https://www.filimo.com/n/99963
  Tagged URL : https://www.filimo.com/tag/<tag>/n/99963

Output structure (Jellyfin-compatible)
---------------------------------------
Movies:
  {output}/
    {Title} ({Year})/
      {Title} ({Year}).mp4
      poster.jpg
      fanart.jpg
      {Title} ({Year}).nfo

TV Shows:
  {output}/
    {Show Title} ({Year})/
      poster.jpg          ← series-level poster
      fanart.jpg          ← series-level backdrop
      tvshow.nfo          ← series NFO
      Season 01/
        poster.jpg        ← season poster (if available)
        {Show} - S01E01 - {Episode Title}.mp4
        {Show} - S01E01 - {Episode Title}.nfo
        {Show} - S01E01 - {Episode Title}-thumb.jpg  ← episode thumb
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FILIMO_API_BASE = "https://www.filimo.com/api/fa/v1"
FILIMO_MOVIE_META_URL = FILIMO_API_BASE + "/movie/movie/one/uid/{uid}"
FILIMO_DOWNLOAD_URL = FILIMO_API_BASE + "/movie/movie/download_manager/uid/{uid}"
FILIMO_SERIES_EPS_URL = (
        FILIMO_API_BASE
        + "/movie/serial/episodebyseason/parent_id/{series_id}"
          "/part/{season}/sort/DESC/?episode_perpage={per_page}"
)
FILIMO_SERIES_META_URL = FILIMO_API_BASE + "/movie/movie/one/uid/{uid}"  # same endpoint, series uid

CONFIG_DIR = Path.home() / ".jellyfin-organizer"
TOKEN_FILE = CONFIG_DIR / "filimo_token.json"

MAX_QUALITY_HEIGHT = 1080  # Never download above Full HD
CHUNK_SIZE = 1024 * 1024 * 4  # 4 MB

_PERSIAN_DIGIT_TABLE = str.maketrans(
    "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9",
    "0123456789",
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FilimoStreamOption:
    quality_label: str
    height: int
    bandwidth: int
    url: str
    size_label: str
    payment: Optional[str] = None


@dataclass
class FilimoMetadata:
    uid: str
    title_en: str
    title_fa: str
    year: str
    imdb_rate: str
    description_fa: str
    description_en: str
    duration_seconds: int
    poster_url: str
    backdrop_url: str
    categories: list[dict] = field(default_factory=list)
    countries: list[dict] = field(default_factory=list)
    director: list[dict] = field(default_factory=list)
    age_range: str = ""
    content_type: str = "Movie"  # "Movie" | "Series"


@dataclass
class EpisodeInfo:
    """One episode as parsed from the series episodes API."""
    uid: str  # Filimo UID used for download_manager
    movie_id: str
    season_num: int
    episode_num: int
    title_en: str
    title_fa: str
    description_fa: str
    description_en: str
    duration_seconds: int
    thumb_url: str  # episode thumbnail (pic.movie_img_b)
    is_free: bool
    series_id: str  # parent_id


@dataclass
class SeasonInfo:
    season_num: int
    title_fa: str  # e.g. "فصل اول"
    episodes: list[EpisodeInfo] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _normalize_persian(text: str) -> str:
    return str(text).translate(_PERSIAN_DIGIT_TABLE)


def _safe_filename(name: str) -> str:
    """Remove characters illegal on Windows/Linux file systems."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name).strip()


def _clean_url(url: str) -> str:
    return url.replace("\\/", "/").strip()


# ---------------------------------------------------------------------------
# Input parsers
# ---------------------------------------------------------------------------

def _extract_movie_uid(input_str: str) -> str:
    """
    Accept movie UID, short URL (/m/{uid}), or full URL (/m/{uid}/...).
    Raises ValueError if the format is unrecognised.
    """
    input_str = input_str.strip()
    parsed = urlparse(input_str)
    if parsed.scheme in ("http", "https"):
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] in ("m", "movie"):
            return parts[1]
        raise ValueError(f"Cannot extract movie UID from URL: {input_str}")
    if re.match(r'^[A-Za-z0-9_-]+$', input_str):
        return input_str
    raise ValueError(f"Unrecognised movie input: {input_str!r}")


def _extract_series_id(input_str: str) -> str:
    """
    Accept series ID, short URL (/n/{id}), or tagged URL (/tag/.../n/{id}).
    Raises ValueError if the format is unrecognised.
    """
    input_str = input_str.strip()
    parsed = urlparse(input_str)
    if parsed.scheme in ("http", "https"):
        parts = [p for p in parsed.path.split("/") if p]
        # /n/{id}  or  /tag/{slug}/n/{id}
        for i, part in enumerate(parts):
            if part == "n" and i + 1 < len(parts):
                candidate = parts[i + 1]
                if candidate.isdigit():
                    return candidate
        raise ValueError(f"Cannot extract series ID from URL: {input_str}")
    if input_str.isdigit():
        return input_str
    raise ValueError(f"Unrecognised series input: {input_str!r}")


def is_series_input(input_str: str) -> bool:
    """Return True if the input looks like a series (numeric ID or /n/ URL)."""
    s = input_str.strip()
    if s.isdigit():
        return True
    parsed = urlparse(s)
    if parsed.scheme in ("http", "https"):
        parts = [p for p in parsed.path.split("/") if p]
        return "n" in parts
    return False


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------

def _load_token() -> Optional[str]:
    # First try the app config (preferred location)
    try:
        from config.app_config import get_config
        cfg_token = get_config().auth.filimo_token
        if cfg_token:
            return cfg_token
    except Exception:
        pass
    # Fallback: legacy JSON token file
    if not TOKEN_FILE.exists():
        return None
    try:
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        token = data.get("token", "")
        expiry = data.get("expires_at")
        if expiry and time.time() > expiry:
            logger.warning("Filimo JWT token has expired.")
            return None
        return token if token else None
    except Exception as exc:
        logger.warning("Could not read token file: %s", exc)
        return None


def _save_token(token: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(
        json.dumps({"token": token, "saved_at": int(time.time())}),
        encoding="utf-8",
    )
    logger.info("Token saved to %s", TOKEN_FILE)


def _prompt_token() -> str:
    print("\n" + "=" * 60)
    print("Filimo JWT token is missing or expired.")
    print("To get your token:")
    print("  1. Open https://www.filimo.com in your browser and log in.")
    print("  2. Open DevTools (F12) → Network tab → filter by 'api/fa'.")
    print("  3. Click any request and copy the header:")
    print("       authorization: Bearer <TOKEN>")
    print("  4. Paste only the token part (after 'Bearer ') below.")
    print("=" * 60)
    token = input("Paste your JWT token: ").strip()
    if not token:
        raise RuntimeError("No token provided — cannot continue.")
    _save_token(token)
    return token


def get_token(token_override: Optional[str] = None) -> str:
    if token_override:
        _save_token(token_override)
        return token_override
    token = _load_token()
    if not token:
        token = _prompt_token()
    return token


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _api_headers(token: str) -> dict:
    return {
        "accept": "application/json",
        "accept-language": "en-US,en;q=0.5",
        "authorization": f"Bearer {token}",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/147.0.0.0 Safari/537.36"
        ),
        "useragent": '{"os":"react","pf":"site"}',
        "trackerabtest": '{"leadToApp":"origin"}',
    }


def _api_get(url: str, token: str, timeout: int = 30) -> dict:
    resp = requests.get(url, headers=_api_headers(token), timeout=timeout)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.json()


# ---------------------------------------------------------------------------
# Movie metadata
# ---------------------------------------------------------------------------

def fetch_metadata(uid: str, token: str) -> FilimoMetadata:
    url = FILIMO_MOVIE_META_URL.format(uid=uid)
    logger.info("Fetching metadata for UID=%s", uid)
    data = _api_get(url, token)

    attrs = data["data"]["attributes"]
    gen = attrs["General"]

    raw_year = _normalize_persian(str(gen.get("pro_year", "")))
    poster_url = _clean_url((gen.get("thumbnails") or {}).get("movie_img_b", "")
                            or gen.get("cover", ""))
    backdrop_url = _clean_url(
        (gen.get("cover_data") or {}).get("horizontal", "") or gen.get("cover", "")
    )
    director_raw = gen.get("director", [])

    # Detect series
    serial_info = gen.get("serial", {})
    content_type = "Series" if serial_info and serial_info.get("enable") else "Movie"

    return FilimoMetadata(
        uid=uid,
        title_en=gen.get("title_en", ""),
        title_fa=gen.get("title_fa", ""),
        year=raw_year,
        imdb_rate=str(gen.get("imdb_rate", "")),
        description_fa=gen.get("descr", ""),
        description_en=gen.get("descr_en", ""),
        duration_seconds=int((gen.get("duration") or {}).get("value", 0)),
        poster_url=poster_url,
        backdrop_url=backdrop_url,
        categories=gen.get("categories", []),
        countries=gen.get("countries", []),
        director=director_raw,
        age_range=gen.get("age_range", ""),
        content_type=content_type,
    )


# ---------------------------------------------------------------------------
# Series / Episode metadata
# ---------------------------------------------------------------------------

def _parse_episode(item: dict, series_id: str) -> Optional[EpisodeInfo]:
    """Parse one 'movies' entry from the episode list response."""
    attrs = item.get("attributes", {})
    try:
        serial = attrs.get("serial", {})
        season_raw = _normalize_persian(str(serial.get("season_id", "1") or "1"))
        episode_raw = _normalize_persian(str(serial.get("serial_part", "0") or "0"))

        season_num = int(season_raw) if season_raw.isdigit() else 1
        episode_num = int(episode_raw) if episode_raw.isdigit() else 0

        uid = attrs.get("uid", attrs.get("link_key", ""))
        movie_id = str(attrs.get("movie_id", attrs.get("id", "")))

        thumb_url = _clean_url(
            (attrs.get("pic") or {}).get("movie_img_b", "")
            or (attrs.get("thumbplay") or {}).get("thumbplay_img_b", "")
        )

        duration_raw = attrs.get("duration", "0")
        try:
            duration_sec = int(_normalize_persian(str(duration_raw)))
        except (ValueError, TypeError):
            duration_sec = 0

        title_en = attrs.get("movie_title_en", "")
        title_fa = attrs.get("movie_title", "")

        return EpisodeInfo(
            uid=uid,
            movie_id=movie_id,
            season_num=season_num,
            episode_num=episode_num,
            title_en=title_en,
            title_fa=title_fa,
            description_fa=attrs.get("descr", ""),
            description_en=attrs.get("descr_en", ""),
            duration_seconds=duration_sec,
            thumb_url=thumb_url,
            is_free=bool(attrs.get("is_free_movie", False)
                         or attrs.get("freemium", False)),
            series_id=str(series_id),
        )
    except Exception as exc:
        logger.debug("Failed to parse episode: %s", exc)
        return None


def fetch_season_episodes(
        series_id: str,
        season_num: int,
        token: str,
        per_page: int = 40,
) -> list[EpisodeInfo]:
    """Fetch all episodes for one season (handles pagination)."""
    episodes: list[EpisodeInfo] = []
    url = FILIMO_SERIES_EPS_URL.format(
        series_id=series_id,
        season=season_num,
        per_page=per_page,
    )
    logger.info("Fetching season %d episodes for series %s", season_num, series_id)
    try:
        data = _api_get(url, token)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return []  # Season doesn't exist
        raise

    included = data.get("included", [])
    for item in included:
        if item.get("type") != "movies":
            continue
        ep = _parse_episode(item, series_id)
        if ep:
            episodes.append(ep)

    # Sort by episode number ascending
    episodes.sort(key=lambda e: e.episode_num)
    return episodes


def fetch_all_seasons(
        series_id: str,
        token: str,
        per_page: int = 40,
        max_seasons: int = 30,
) -> list[SeasonInfo]:
    """
    Discover and fetch every season of a series.
    Stops when a season returns no episodes (gap = end of series).
    """
    seasons: list[SeasonInfo] = []
    for season_num in range(1, max_seasons + 1):
        episodes = fetch_season_episodes(series_id, season_num, token, per_page)
        if not episodes:
            break
        # Get season title from data.data[0].attributes.title if available
        # (we re-use the title from the first episode's serial block as fallback)
        season_fa = f"فصل {season_num}"
        seasons.append(SeasonInfo(
            season_num=season_num,
            title_fa=season_fa,
            episodes=episodes,
        ))
        logger.info(
            "  Season %d: %d episode(s) found.", season_num, len(episodes)
        )
    return seasons


# ---------------------------------------------------------------------------
# Download links
# ---------------------------------------------------------------------------

def fetch_download_options(uid: str, token: str) -> list[FilimoStreamOption]:
    url = FILIMO_DOWNLOAD_URL.format(uid=uid)
    data = _api_get(url, token)

    streams_raw = data["data"]["attributes"].get("stream", [])
    options: list[FilimoStreamOption] = []

    for s in streams_raw:
        quality_raw = _normalize_persian(s.get("quality", ""))
        height_raw = s.get("height", 0)
        try:
            height = int(height_raw)
        except (ValueError, TypeError):
            m = re.search(r'(\d+)', quality_raw)
            height = int(m.group(1)) if m else 0

        dl_url = _clean_url(s.get("url", ""))
        if not dl_url:
            continue

        options.append(FilimoStreamOption(
            quality_label=quality_raw,
            height=height,
            bandwidth=int(s.get("bandwidth", 0)),
            url=dl_url,
            size_label=_normalize_persian(s.get("size", "")),
            payment=s.get("payment"),
        ))

    options.sort(key=lambda o: o.height, reverse=True)
    return options


def select_best_quality(
        options: list[FilimoStreamOption],
        max_height: int = MAX_QUALITY_HEIGHT,
) -> Optional[FilimoStreamOption]:
    candidates = [o for o in options if 0 < o.height <= max_height]
    if not candidates:
        candidates = list(options)  # all are 4K → take best available
    if not candidates:
        return None
    candidates.sort(key=lambda o: o.height, reverse=True)
    best = candidates[0]
    logger.info(
        "Selected quality: %s (%dpx) — %s", best.quality_label, best.height, best.size_label
    )
    return best


# ---------------------------------------------------------------------------
# Jellyfin naming helpers
# ---------------------------------------------------------------------------

def _year_part(year: str) -> str:
    return year[:4] if len(year) >= 4 else year


def jellyfin_movie_folder(meta: FilimoMetadata) -> str:
    title = _safe_filename(meta.title_en or meta.title_fa)
    return f"{title} ({_year_part(meta.year)})"


def jellyfin_base_name(meta: FilimoMetadata) -> str:
    return jellyfin_movie_folder(meta)


def jellyfin_series_folder(meta: FilimoMetadata) -> str:
    title = _safe_filename(meta.title_en or meta.title_fa)
    return f"{title} ({_year_part(meta.year)})"


def jellyfin_season_folder(season_num: int) -> str:
    return f"Season {season_num:02d}"


def jellyfin_episode_base(
        show_title: str,
        season_num: int,
        episode_num: int,
        episode_title: str = "",
) -> str:
    """
    Returns: '{Show Title} - S01E06 - {Episode Title}'
    or just:  '{Show Title} - S01E06'  if title is empty.
    """
    code = f"S{season_num:02d}E{episode_num:02d}"
    safe_show = _safe_filename(show_title)
    safe_ep_title = _safe_filename(episode_title)
    if safe_ep_title:
        return f"{safe_show} - {code} - {safe_ep_title}"
    return f"{safe_show} - {code}"


# ---------------------------------------------------------------------------
# Resumable video download
# ---------------------------------------------------------------------------

def _file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def download_video(
        stream: FilimoStreamOption,
        dest_dir: Path,
        base_name: str,
        token: str,
        *,
        dry_run: bool = False,
        progress_interval: int = 5,
) -> Optional[Path]:
    """Download video with HTTP Range resume support."""
    ext = Path(urlparse(stream.url).path).suffix or ".mp4"
    dest_path = dest_dir / f"{base_name}{ext}"

    if dry_run:
        logger.info("[DRY RUN] Would download %s → %s", stream.url, dest_path)
        return dest_path

    existing_bytes = _file_size(dest_path)
    headers = dict(_api_headers(token))

    if existing_bytes:
        headers["Range"] = f"bytes={existing_bytes}-"
        logger.info("Resuming from byte %d: %s", existing_bytes, dest_path.name)
    else:
        logger.info("Downloading %s → %s", stream.quality_label, dest_path.name)

    try:
        resp = requests.get(stream.url, headers=headers, stream=True, timeout=60)
        if resp.status_code == 416:
            logger.info("Already complete: %s", dest_path.name)
            return dest_path
        resp.raise_for_status()

        mode = "ab" if existing_bytes and resp.status_code == 206 else "wb"
        total = int(resp.headers.get("content-length", 0)) + existing_bytes
        downloaded = existing_bytes
        last_log = time.time()

        with open(dest_path, mode) as fh:
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    fh.write(chunk)
                    downloaded += len(chunk)
                    now = time.time()
                    if now - last_log >= progress_interval:
                        pct = (downloaded / total * 100) if total else 0
                        logger.info(
                            "  … %.1f MB (%.1f%%)", downloaded / 1024 / 1024, pct
                        )
                        last_log = now

        logger.info(
            "Done: %s (%.1f MB)", dest_path.name, downloaded / 1024 / 1024
        )
        return dest_path

    except requests.RequestException as exc:
        logger.error("Download failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def _download_image(url: str, dest: Path, label: str, dry_run: bool = False) -> bool:
    if not url:
        logger.warning("No %s URL.", label)
        return False
    if dry_run:
        logger.info("[DRY RUN] %s → %s", label, dest)
        return True
    if dest.exists():
        logger.debug("%s already exists, skipping.", dest.name)
        return True
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        logger.info("%s saved: %s", label, dest.name)
        return True
    except Exception as exc:
        logger.error("Failed to download %s: %s", label, exc)
        return False


def download_series_images(
        meta: FilimoMetadata,
        series_dir: Path,
        dry_run: bool = False,
) -> dict[str, bool]:
    return {
        "poster": _download_image(meta.poster_url, series_dir / "poster.jpg", "Series poster", dry_run),
        "backdrop": _download_image(meta.backdrop_url, series_dir / "fanart.jpg", "Series backdrop", dry_run),
    }


def download_movie_images(
        meta: FilimoMetadata,
        dest_dir: Path,
        dry_run: bool = False,
) -> dict[str, bool]:
    return {
        "poster": _download_image(meta.poster_url, dest_dir / "poster.jpg", "Poster", dry_run),
        "backdrop": _download_image(meta.backdrop_url, dest_dir / "fanart.jpg", "Backdrop", dry_run),
    }


def download_episode_thumb(
        ep: EpisodeInfo,
        season_dir: Path,
        base_name: str,
        dry_run: bool = False,
) -> bool:
    return _download_image(
        ep.thumb_url,
        season_dir / f"{base_name}-thumb.jpg",
        f"E{ep.episode_num:02d} thumb",
        dry_run,
    )


# ---------------------------------------------------------------------------
# NFO generators
# ---------------------------------------------------------------------------

def _pretty_xml(root) -> str:
    import xml.etree.ElementTree as ET
    from xml.dom import minidom
    raw = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ")
    return pretty


def generate_movie_nfo(
        meta: FilimoMetadata,
        dest_dir: Path,
        base_name: str,
        dry_run: bool = False,
) -> bool:
    import xml.etree.ElementTree as ET

    nfo_path = dest_dir / f"{base_name}.nfo"
    if nfo_path.exists():
        logger.debug("NFO exists, skipping: %s", nfo_path.name)
        return True

    root = ET.Element("movie")

    def add(tag: str, text: str) -> None:
        if text:
            el = ET.SubElement(root, tag)
            el.text = text

    add("title", meta.title_en or meta.title_fa)
    add("originaltitle", meta.title_fa)
    add("sorttitle", meta.title_en or meta.title_fa)
    add("year", meta.year)
    add("plot", meta.description_en or meta.description_fa)
    add("rating", meta.imdb_rate)

    if meta.duration_seconds:
        add("runtime", str(meta.duration_seconds // 60))
    if meta.age_range:
        add("mpaa", meta.age_range)

    for cat in meta.categories:
        add("genre", (cat.get("title_en") or cat.get("title", "")).capitalize())
    for country in meta.countries:
        add("country", (country.get("title_en") or country.get("title", "")).capitalize())
    for director in meta.director:
        add("director", director.get("name", ""))

    uid_el = ET.SubElement(root, "uniqueid")
    uid_el.set("type", "filimo")
    uid_el.text = meta.uid

    if dry_run:
        logger.info("[DRY RUN] Would write movie NFO: %s", nfo_path)
        return True

    nfo_path.write_text(_pretty_xml(root), encoding="utf-8")
    logger.info("NFO written: %s", nfo_path.name)
    return True


def generate_tvshow_nfo(
        meta: FilimoMetadata,
        series_dir: Path,
        dry_run: bool = False,
) -> bool:
    import xml.etree.ElementTree as ET

    nfo_path = series_dir / "tvshow.nfo"
    if nfo_path.exists():
        logger.debug("tvshow.nfo exists, skipping.")
        return True

    root = ET.Element("tvshow")

    def add(tag: str, text: str) -> None:
        if text:
            el = ET.SubElement(root, tag)
            el.text = text

    add("title", meta.title_en or meta.title_fa)
    add("originaltitle", meta.title_fa)
    add("sorttitle", meta.title_en or meta.title_fa)
    add("year", meta.year)
    add("plot", meta.description_en or meta.description_fa)
    add("rating", meta.imdb_rate)

    if meta.age_range:
        add("mpaa", meta.age_range)
    for cat in meta.categories:
        add("genre", (cat.get("title_en") or cat.get("title", "")).capitalize())
    for country in meta.countries:
        add("country", (country.get("title_en") or country.get("title", "")).capitalize())

    uid_el = ET.SubElement(root, "uniqueid")
    uid_el.set("type", "filimo")
    uid_el.text = meta.uid

    if dry_run:
        logger.info("[DRY RUN] Would write tvshow.nfo: %s", nfo_path)
        return True

    nfo_path.write_text(_pretty_xml(root), encoding="utf-8")
    logger.info("tvshow.nfo written.")
    return True


def generate_episode_nfo(
        ep: EpisodeInfo,
        show_meta: FilimoMetadata,
        season_dir: Path,
        base_name: str,
        dry_run: bool = False,
) -> bool:
    import xml.etree.ElementTree as ET

    nfo_path = season_dir / f"{base_name}.nfo"
    if nfo_path.exists():
        logger.debug("Episode NFO exists, skipping: %s", nfo_path.name)
        return True

    root = ET.Element("episodedetails")

    def add(tag: str, text: str) -> None:
        if text:
            el = ET.SubElement(root, tag)
            el.text = text

    add("title", ep.title_en or ep.title_fa)
    add("originaltitle", ep.title_fa)
    add("showtitle", show_meta.title_en or show_meta.title_fa)
    add("season", str(ep.season_num))
    add("episode", str(ep.episode_num))
    add("plot", ep.description_en or ep.description_fa)

    if ep.duration_seconds:
        add("runtime", str(ep.duration_seconds // 60))

    uid_el = ET.SubElement(root, "uniqueid")
    uid_el.set("type", "filimo")
    uid_el.text = ep.uid

    if dry_run:
        logger.info("[DRY RUN] Would write episode NFO: %s", nfo_path)
        return True

    nfo_path.write_text(_pretty_xml(root), encoding="utf-8")
    logger.info("Episode NFO written: %s", nfo_path.name)
    return True


# ---------------------------------------------------------------------------
# IDM entry builder helpers
# ---------------------------------------------------------------------------

def _build_idm_entries_for_stream(
        stream: FilimoStreamOption,
        dest_dir: Path,
        base_name: str,
        queue_name: str,
        description: str = "",
) -> list:
    """Import here to avoid circular issues; returns list[IdmEntry]."""
    from src.services.idm_export import IdmEntry
    ext = Path(urlparse(stream.url).path).suffix or ".mp4"
    filename = f"{base_name}{ext}"
    return [IdmEntry(
        url=stream.url,
        filename=filename,
        save_path=str(dest_dir),
        queue_name=queue_name,
        description=description,
    )]


# ---------------------------------------------------------------------------
# Movie pipeline
# ---------------------------------------------------------------------------

def download_movie(
        uid_or_url: str,
        output_dir: Path,
        token: str,
        *,
        metadata_only: bool = False,
        dry_run: bool = False,
        max_height: int = MAX_QUALITY_HEIGHT,
        progress_interval: int = 5,
        idm_queue: Optional[str] = None,  # None = direct download; str = collect for IDM
) -> dict:
    """
    Full pipeline for a single movie.

    Returns result dict with keys:
      uid, folder, video, poster, backdrop, nfo, error, idm_entries
    """
    result: dict = {
        "uid": uid_or_url, "folder": None, "video": None,
        "poster": False, "backdrop": False, "nfo": False,
        "error": None, "idm_entries": [],
    }

    try:
        uid = _extract_movie_uid(uid_or_url)
        result["uid"] = uid
    except ValueError as exc:
        result["error"] = str(exc)
        return result

    try:
        meta = fetch_metadata(uid, token)
        folder_name = jellyfin_movie_folder(meta)
        base_name = jellyfin_base_name(meta)
        dest_dir = output_dir / folder_name
        result["folder"] = str(dest_dir)

        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)

        imgs = download_movie_images(meta, dest_dir, dry_run=dry_run)
        result.update(imgs)

        result["nfo"] = generate_movie_nfo(meta, dest_dir, base_name, dry_run=dry_run)

        if not metadata_only:
            options = fetch_download_options(uid, token)
            if not options:
                raise RuntimeError("No download streams returned by API.")
            best = select_best_quality(options, max_height)
            if not best:
                raise RuntimeError("Could not select a quality stream.")

            if best.payment:
                logger.warning("Stream requires payment. Skipping video.")
            elif idm_queue is not None:
                # Collect for IDM instead of downloading
                result["idm_entries"] = _build_idm_entries_for_stream(
                    best, dest_dir, base_name, idm_queue,
                    description=f"{meta.title_en or meta.title_fa} ({meta.year})"
                )
                logger.info("IDM entry queued: %s", base_name)
            else:
                video_path = download_video(
                    best, dest_dir, base_name, token,
                    dry_run=dry_run, progress_interval=progress_interval,
                )
                result["video"] = str(video_path) if video_path else None

    except Exception as exc:
        result["error"] = str(exc)
        logger.error("Failed processing UID=%s: %s", result["uid"], exc)

    return result


# ---------------------------------------------------------------------------
# Series pipeline
# ---------------------------------------------------------------------------

def download_series(
        series_id_or_url: str,
        output_dir: Path,
        token: str,
        *,
        series_meta_uid: Optional[str] = None,
        metadata_only: bool = False,
        dry_run: bool = False,
        max_height: int = MAX_QUALITY_HEIGHT,
        episodes_per_page: int = 40,
        download_season_images: bool = True,
        progress_interval: int = 5,
        idm_queue: Optional[str] = None,
) -> dict:
    """
    Full pipeline for a TV series.

    Returns a result dict with:
      series_id, folder, seasons, total_episodes,
      downloaded_episodes, errors, idm_entries
    """
    result: dict = {
        "series_id": series_id_or_url,
        "folder": None,
        "seasons": 0,
        "total_episodes": 0,
        "downloaded_episodes": 0,
        "errors": [],
        "idm_entries": [],
    }

    try:
        series_id = _extract_series_id(series_id_or_url)
        result["series_id"] = series_id
    except ValueError as exc:
        result["errors"].append(str(exc))
        logger.error("Invalid series input '%s': %s", series_id_or_url, exc)
        return result

    try:
        # ── Series-level metadata ──────────────────────────────────────
        # We need a UID for the metadata API. If not given, try to derive
        # one from the first episode (which carries serial.parent_id).
        show_meta: Optional[FilimoMetadata] = None
        if series_meta_uid:
            try:
                show_meta = fetch_metadata(series_meta_uid, token)
            except Exception as exc:
                logger.warning("Could not fetch series metadata: %s", exc)

        # Fetch all seasons/episodes first so we can also grab show metadata
        logger.info("Discovering seasons for series ID=%s …", series_id)
        seasons = fetch_all_seasons(series_id, token, per_page=episodes_per_page)

        if not seasons:
            raise RuntimeError(f"No episodes found for series ID={series_id}")

        # If we still have no show_meta, try fetching from first episode's uid
        if not show_meta and seasons and seasons[0].episodes:
            first_ep_uid = seasons[0].episodes[0].uid
            try:
                ep_meta = fetch_metadata(first_ep_uid, token)
                # The episode metadata has the show title in some fields
                # We synthesise a show-level metadata from it
                show_meta = ep_meta
                # Override content type
                show_meta.content_type = "Series"
            except Exception as exc:
                logger.warning("Could not derive show metadata: %s", exc)

        # Fallback show title from season info
        if not show_meta:
            show_meta = FilimoMetadata(
                uid=series_id,
                title_en=f"Series {series_id}",
                title_fa="",
                year="",
                imdb_rate="",
                description_fa="",
                description_en="",
                duration_seconds=0,
                poster_url="",
                backdrop_url="",
                content_type="Series",
            )

        # ── Directory structure ────────────────────────────────────────
        series_folder = jellyfin_series_folder(show_meta)
        series_dir = output_dir / series_folder
        result["folder"] = str(series_dir)

        if not dry_run:
            series_dir.mkdir(parents=True, exist_ok=True)

        # Series-level images + NFO
        download_series_images(show_meta, series_dir, dry_run=dry_run)
        generate_tvshow_nfo(show_meta, series_dir, dry_run=dry_run)

        show_title = _safe_filename(show_meta.title_en or show_meta.title_fa)

        result["seasons"] = len(seasons)

        # ── Per-season / per-episode ──────────────────────────────────
        for season in seasons:
            season_folder = jellyfin_season_folder(season.season_num)
            season_dir = series_dir / season_folder

            if not dry_run:
                season_dir.mkdir(parents=True, exist_ok=True)

            # Optional season-level poster (re-use series poster as fallback)
            if download_season_images and show_meta.poster_url:
                _download_image(
                    show_meta.poster_url,
                    season_dir / "poster.jpg",
                    f"Season {season.season_num} poster",
                    dry_run,
                )

            for ep in season.episodes:
                result["total_episodes"] += 1
                ep_base = jellyfin_episode_base(
                    show_title, ep.season_num, ep.episode_num,
                    ep.title_en or "",
                )

                # Episode thumb
                download_episode_thumb(ep, season_dir, ep_base, dry_run=dry_run)

                # Episode NFO
                generate_episode_nfo(ep, show_meta, season_dir, ep_base, dry_run=dry_run)

                if metadata_only:
                    result["downloaded_episodes"] += 1
                    continue

                # Fetch download options
                try:
                    options = fetch_download_options(ep.uid, token)
                except Exception as exc:
                    msg = f"S{ep.season_num:02d}E{ep.episode_num:02d}: {exc}"
                    logger.error("Download options failed: %s", msg)
                    result["errors"].append(msg)
                    continue

                if not options:
                    logger.warning(
                        "No streams for S%02dE%02d, skipping.",
                        ep.season_num, ep.episode_num,
                    )
                    continue

                best = select_best_quality(options, max_height)
                if not best:
                    continue

                if best.payment:
                    logger.warning(
                        "S%02dE%02d requires payment, skipping.",
                        ep.season_num, ep.episode_num,
                    )
                    continue

                if idm_queue is not None:
                    entries = _build_idm_entries_for_stream(
                        best, season_dir, ep_base, idm_queue,
                        description=(
                            f"{show_meta.title_en or show_meta.title_fa} "
                            f"S{ep.season_num:02d}E{ep.episode_num:02d}"
                        ),
                    )
                    result["idm_entries"].extend(entries)
                    logger.info(
                        "IDM entry queued: %s", ep_base
                    )
                    result["downloaded_episodes"] += 1
                else:
                    video_path = download_video(
                        best, season_dir, ep_base, token,
                        dry_run=dry_run, progress_interval=progress_interval,
                    )
                    if video_path:
                        result["downloaded_episodes"] += 1
                    else:
                        result["errors"].append(
                            f"S{ep.season_num:02d}E{ep.episode_num:02d}: download failed"
                        )

    except Exception as exc:
        result["errors"].append(str(exc))
        logger.error("Series pipeline failed [%s]: %s", result["series_id"], exc)

    return result


# ---------------------------------------------------------------------------
# Unified dispatcher (movie vs series)
# ---------------------------------------------------------------------------

def download_item(
        input_str: str,
        output_dir: Path,
        token: str,
        *,
        metadata_only: bool = False,
        dry_run: bool = False,
        max_height: int = MAX_QUALITY_HEIGHT,
        episodes_per_page: int = 40,
        download_season_images: bool = True,
        progress_interval: int = 5,
        idm_queue: Optional[str] = None,
) -> dict:
    """Route to movie or series pipeline based on the input format."""
    if is_series_input(input_str):
        return download_series(
            input_str, output_dir, token,
            metadata_only=metadata_only,
            dry_run=dry_run,
            max_height=max_height,
            episodes_per_page=episodes_per_page,
            download_season_images=download_season_images,
            progress_interval=progress_interval,
            idm_queue=idm_queue,
        )
    else:
        return download_movie(
            input_str, output_dir, token,
            metadata_only=metadata_only,
            dry_run=dry_run,
            max_height=max_height,
            progress_interval=progress_interval,
            idm_queue=idm_queue,
        )


# ---------------------------------------------------------------------------
# Batch helpers
# ---------------------------------------------------------------------------

def download_batch(
        items: list[str],
        output_dir: Path,
        token: str,
        *,
        metadata_only: bool = False,
        dry_run: bool = False,
        max_height: int = MAX_QUALITY_HEIGHT,
        episodes_per_page: int = 40,
        download_season_images: bool = True,
        progress_interval: int = 5,
        idm_queue: Optional[str] = None,
) -> list[dict]:
    results = []
    total = len(items)
    for i, item in enumerate(items, 1):
        item = item.strip()
        if not item or item.startswith("#"):
            continue
        logger.info("=" * 60)
        logger.info("[%d/%d] %s", i, total, item)
        r = download_item(
            item, output_dir, token,
            metadata_only=metadata_only,
            dry_run=dry_run,
            max_height=max_height,
            episodes_per_page=episodes_per_page,
            download_season_images=download_season_images,
            progress_interval=progress_interval,
            idm_queue=idm_queue,
        )
        results.append(r)
    return results


def load_batch_file(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
