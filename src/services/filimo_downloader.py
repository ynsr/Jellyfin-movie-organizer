"""
Filimo Downloader Service
=========================
Downloads movies (and future TV episodes) directly from Filimo.com.

Features
--------
- Parse input as full URL, short URL, or bare UID
- Fetch movie metadata via /api/fa/v1/movie/movie/one/uid/{UID}
- Fetch download links via /api/fa/v1/movie/movie/download_manager/uid/{UID}
- Select highest quality ≤ 1080p (never 4K)
- Resumable download (Content-Range / partial content)
- Download poster and backdrop images
- Generate Jellyfin-compatible NFO
- Batch mode: accept a file with one URL/UID per line
- --metadata-only flag: skip video, only fetch images + NFO
- JWT token read from config file; prompts user if missing/expired

Jellyfin file naming
--------------------
Movies  : {Title} ({Year})/{Title} ({Year}).{ext}
Episodes: {Show} ({Year})/Season {N}/{Show} S{NN}E{NN}.{ext}   (future)
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
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
FILIMO_DOWNLOAD_URL   = FILIMO_API_BASE + "/movie/movie/download_manager/uid/{uid}"

CONFIG_DIR  = Path.home() / ".jellyfin-organizer"
TOKEN_FILE  = CONFIG_DIR / "filimo_token.json"

MAX_QUALITY_HEIGHT = 1080    # Never download above Full HD
CHUNK_SIZE = 1024 * 1024 * 4  # 4 MB chunks

# Persian-Indic → ASCII digit translation table
_PERSIAN_DIGIT_TABLE = str.maketrans(
    "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9",
    "0123456789",
)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FilimoStreamOption:
    quality_label: str   # e.g. "480p"
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
    content_type: str = "Movie"   # Movie | Series (future)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_persian(text: str) -> str:
    """Translate Persian-Indic digits to ASCII digits."""
    return text.translate(_PERSIAN_DIGIT_TABLE)


def _safe_filename(name: str) -> str:
    """Strip characters that are illegal in file/directory names."""
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()


def _extract_uid(input_str: str) -> str:
    """
    Accept any of:
      - Full URL  : https://www.filimo.com/m/aVmdY/...
      - Short URL : https://www.filimo.com/m/aVmdY
      - Bare UID  : aVmdY

    Returns the UID portion (alphanumeric, 5 chars, but we don't enforce length).
    """
    input_str = input_str.strip()
    # Try to parse as URL first
    parsed = urlparse(input_str)
    if parsed.scheme in ("http", "https"):
        # Path looks like /m/{uid}/... or /movie/{uid}/...
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] in ("m", "movie"):
            return parts[1]
        raise ValueError(f"Cannot extract UID from URL: {input_str}")
    # Treat as bare UID
    if re.match(r'^[A-Za-z0-9_-]+$', input_str):
        return input_str
    raise ValueError(f"Unrecognised input format: {input_str!r}")


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------

def _load_token() -> Optional[str]:
    """Load JWT token from config file. Returns None if absent or expired."""
    if not TOKEN_FILE.exists():
        return None
    try:
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        token = data.get("token", "")
        # Optional: check stored expiry if we saved it
        expiry = data.get("expires_at")
        if expiry and time.time() > expiry:
            logger.warning("Filimo JWT token has expired.")
            return None
        return token if token else None
    except Exception as exc:
        logger.warning("Could not read token file: %s", exc)
        return None


def _save_token(token: str) -> None:
    """Persist JWT token to config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(
        json.dumps({"token": token, "saved_at": int(time.time())}),
        encoding="utf-8",
    )
    logger.info("Token saved to %s", TOKEN_FILE)


def _prompt_token() -> str:
    """Ask the user to paste a fresh JWT token interactively."""
    print("\n" + "="*60)
    print("Filimo JWT token is missing or expired.")
    print("To get your token:")
    print("  1. Open https://www.filimo.com in your browser and log in.")
    print("  2. Open DevTools → Network → filter 'api/fa'.")
    print("  3. Copy the 'authorization: Bearer <TOKEN>' value from any request.")
    print("="*60)
    token = input("Paste your JWT token (without 'Bearer '): ").strip()
    if not token:
        raise RuntimeError("No token provided — cannot continue.")
    _save_token(token)
    return token


def get_token(token_override: Optional[str] = None) -> str:
    """Return a valid JWT token, prompting the user if necessary."""
    if token_override:
        _save_token(token_override)
        return token_override
    token = _load_token()
    if not token:
        token = _prompt_token()
    return token


# ---------------------------------------------------------------------------
# API helpers
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
    }


def _api_get(url: str, token: str) -> dict:
    resp = requests.get(url, headers=_api_headers(token), timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.json()


# ---------------------------------------------------------------------------
# Metadata fetching
# ---------------------------------------------------------------------------

def fetch_metadata(uid: str, token: str) -> FilimoMetadata:
    url = FILIMO_MOVIE_META_URL.format(uid=uid)
    logger.info("Fetching metadata for UID=%s", uid)
    data = _api_get(url, token)

    attrs  = data["data"]["attributes"]
    gen    = attrs["General"]

    raw_year = _normalize_persian(str(gen.get("pro_year", "")))

    # Poster / backdrop
    poster_url   = (gen.get("thumbnails") or {}).get("movie_img_b", "")
    backdrop_url = (gen.get("cover_data") or {}).get("horizontal", "") or gen.get("cover", "")
    # Fall back to thumbnails block (same key set as search API)
    if not poster_url:
        poster_url = gen.get("cover", "")

    # Director name(s) as list of dicts [{"name": ..., "link_key": ...}]
    director_raw = gen.get("director", [])

    return FilimoMetadata(
        uid=uid,
        title_en=gen.get("title_en", ""),
        title_fa=gen.get("title_fa", ""),
        year=raw_year,
        imdb_rate=str(gen.get("imdb_rate", "")),
        description_fa=gen.get("descr", ""),
        description_en=gen.get("descr_en", ""),
        duration_seconds=int((gen.get("duration") or {}).get("value", 0)),
        poster_url=poster_url.replace("\\/", "/"),
        backdrop_url=backdrop_url.replace("\\/", "/"),
        categories=gen.get("categories", []),
        countries=gen.get("countries", []),
        director=director_raw,
        age_range=gen.get("age_range", ""),
    )


# ---------------------------------------------------------------------------
# Download links
# ---------------------------------------------------------------------------

def fetch_download_options(uid: str, token: str) -> list[FilimoStreamOption]:
    url = FILIMO_DOWNLOAD_URL.format(uid=uid)
    logger.info("Fetching download options for UID=%s", uid)
    data = _api_get(url, token)

    streams_raw = data["data"]["attributes"].get("stream", [])
    options: list[FilimoStreamOption] = []

    for s in streams_raw:
        quality_raw = _normalize_persian(s.get("quality", ""))
        height_raw  = s.get("height", 0)
        try:
            height = int(height_raw)
        except (ValueError, TypeError):
            # Try to parse from quality label like "480p"
            m = re.search(r'(\d+)', quality_raw)
            height = int(m.group(1)) if m else 0

        dl_url = s.get("url", "").replace("\\/", "/")
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

    # Sort descending by height
    options.sort(key=lambda o: o.height, reverse=True)
    return options


def select_best_quality(options: list[FilimoStreamOption]) -> Optional[FilimoStreamOption]:
    """
    Pick the highest quality stream whose height is ≤ MAX_QUALITY_HEIGHT (1080).
    Never selects 4K (2160p) or above.
    """
    candidates = [o for o in options if 0 < o.height <= MAX_QUALITY_HEIGHT]
    if not candidates:
        # All options are above 1080p — still prefer the lowest 4K over nothing
        candidates = list(options)
    if not candidates:
        return None
    candidates.sort(key=lambda o: o.height, reverse=True)
    best = candidates[0]
    logger.info(
        "Selected quality: %s (%dpx) — %s",
        best.quality_label, best.height, best.size_label,
    )
    return best


# ---------------------------------------------------------------------------
# Jellyfin directory/filename helpers
# ---------------------------------------------------------------------------

def jellyfin_movie_folder(meta: FilimoMetadata) -> str:
    """Return Jellyfin-style folder name: 'Title (Year)'"""
    title = _safe_filename(meta.title_en or meta.title_fa)
    year  = meta.year[:4] if len(meta.year) >= 4 else meta.year
    return f"{title} ({year})"


def jellyfin_base_name(meta: FilimoMetadata) -> str:
    """Return base name (no extension): 'Title (Year)'"""
    return jellyfin_movie_folder(meta)


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
    dry_run: bool = False,
) -> Optional[Path]:
    """
    Download the video file with resume support (HTTP Range requests).
    Returns the final Path, or None on failure.
    """
    ext = Path(urlparse(stream.url).path).suffix or ".mp4"
    dest_path = dest_dir / f"{base_name}{ext}"

    if dry_run:
        logger.info("[DRY RUN] Would download %s → %s", stream.url, dest_path)
        return dest_path

    existing_bytes = _file_size(dest_path)
    headers = dict(_api_headers(token))
    if existing_bytes:
        headers["Range"] = f"bytes={existing_bytes}-"
        logger.info("Resuming download from byte %d: %s", existing_bytes, dest_path.name)
    else:
        logger.info("Starting download: %s → %s", stream.quality_label, dest_path.name)

    try:
        resp = requests.get(stream.url, headers=headers, stream=True, timeout=60)
        # 416 = Range Not Satisfiable → file already complete
        if resp.status_code == 416:
            logger.info("File already fully downloaded: %s", dest_path.name)
            return dest_path

        resp.raise_for_status()

        mode = "ab" if existing_bytes and resp.status_code == 206 else "wb"
        total = int(resp.headers.get("content-length", 0)) + existing_bytes

        downloaded = existing_bytes
        last_log   = time.time()

        with open(dest_path, mode) as fh:
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    fh.write(chunk)
                    downloaded += len(chunk)
                    now = time.time()
                    if now - last_log >= 5:
                        pct = (downloaded / total * 100) if total else 0
                        mb  = downloaded / 1024 / 1024
                        logger.info(
                            "  … %.1f MB downloaded (%.1f%%)", mb, pct
                        )
                        last_log = now

        logger.info("Download complete: %s (%.1f MB)", dest_path.name, downloaded / 1024 / 1024)
        return dest_path

    except requests.RequestException as exc:
        logger.error("Download failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Image downloads
# ---------------------------------------------------------------------------

def _download_image(url: str, dest: Path, label: str, dry_run: bool = False) -> bool:
    if not url:
        logger.warning("No %s URL available.", label)
        return False
    if dry_run:
        logger.info("[DRY RUN] Would download %s → %s", label, dest)
        return True
    if dest.exists():
        logger.info("%s already exists, skipping.", dest.name)
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


def download_images(
    meta: FilimoMetadata,
    dest_dir: Path,
    base_name: str,
    dry_run: bool = False,
) -> dict[str, bool]:
    """Download poster (folder.jpg) and backdrop (fanart.jpg)."""
    results = {}
    results["poster"]   = _download_image(
        meta.poster_url,   dest_dir / "poster.jpg",   "Poster",   dry_run
    )
    results["backdrop"] = _download_image(
        meta.backdrop_url, dest_dir / "fanart.jpg",   "Backdrop", dry_run
    )
    return results


# ---------------------------------------------------------------------------
# NFO generation
# ---------------------------------------------------------------------------

def generate_nfo(
    meta: FilimoMetadata,
    dest_dir: Path,
    base_name: str,
    dry_run: bool = False,
) -> bool:
    """Write Jellyfin-compatible movie.nfo."""
    import xml.etree.ElementTree as ET
    from xml.dom import minidom

    nfo_path = dest_dir / f"{base_name}.nfo"
    if nfo_path.exists():
        logger.info("NFO already exists, skipping: %s", nfo_path.name)
        return True

    root = ET.Element("movie")

    def add(tag: str, text: str) -> None:
        if text:
            el = ET.SubElement(root, tag)
            el.text = text

    add("title",         meta.title_en or meta.title_fa)
    add("originaltitle", meta.title_fa)
    add("sorttitle",     meta.title_en or meta.title_fa)
    add("year",          meta.year)
    add("plot",          meta.description_en or meta.description_fa)
    add("rating",        meta.imdb_rate)

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

    # Filimo-specific unique id
    uid_el = ET.SubElement(root, "uniqueid")
    uid_el.set("type", "filimo")
    uid_el.text = meta.uid

    # Pretty-print
    raw    = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ")

    if dry_run:
        logger.info("[DRY RUN] Would write NFO: %s", nfo_path)
        return True

    nfo_path.write_text(pretty, encoding="utf-8")
    logger.info("NFO written: %s", nfo_path.name)
    return True


# ---------------------------------------------------------------------------
# Main download orchestrator
# ---------------------------------------------------------------------------

def download_movie(
    uid_or_url: str,
    output_dir: Path,
    token: str,
    *,
    metadata_only: bool = False,
    dry_run: bool = False,
) -> dict:
    """
    Full pipeline for a single movie UID/URL.

    Returns a result dict with keys: uid, folder, video, poster, backdrop, nfo, error.
    """
    result = {
        "uid": uid_or_url,
        "folder": None,
        "video": None,
        "poster": False,
        "backdrop": False,
        "nfo": False,
        "error": None,
    }

    try:
        uid = _extract_uid(uid_or_url)
        result["uid"] = uid
    except ValueError as exc:
        result["error"] = str(exc)
        logger.error("Invalid input '%s': %s", uid_or_url, exc)
        return result

    try:
        # 1. Metadata
        meta = fetch_metadata(uid, token)

        # 2. Determine output folder
        folder_name = jellyfin_movie_folder(meta)
        base_name   = jellyfin_base_name(meta)
        dest_dir    = output_dir / folder_name
        result["folder"] = str(dest_dir)

        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)

        # 3. Images
        img_results = download_images(meta, dest_dir, base_name, dry_run=dry_run)
        result["poster"]   = img_results["poster"]
        result["backdrop"] = img_results["backdrop"]

        # 4. NFO
        result["nfo"] = generate_nfo(meta, dest_dir, base_name, dry_run=dry_run)

        # 5. Video (skip if metadata_only)
        if metadata_only:
            logger.info("--metadata-only: skipping video download.")
        else:
            options = fetch_download_options(uid, token)
            if not options:
                raise RuntimeError("No download streams returned by API.")

            best = select_best_quality(options)
            if not best:
                raise RuntimeError("Could not select a suitable quality stream.")

            if best.payment:
                logger.warning(
                    "Stream requires payment (%s). Skipping video.", best.payment
                )
            else:
                video_path = download_video(best, dest_dir, base_name, token, dry_run=dry_run)
                result["video"] = str(video_path) if video_path else None

    except Exception as exc:
        result["error"] = str(exc)
        logger.error("Failed processing UID=%s: %s", result["uid"], exc)

    return result


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------

def download_batch(
    items: list[str],
    output_dir: Path,
    token: str,
    *,
    metadata_only: bool = False,
    dry_run: bool = False,
) -> list[dict]:
    """Process a list of UID/URLs."""
    results = []
    total = len(items)
    for i, item in enumerate(items, 1):
        item = item.strip()
        if not item or item.startswith("#"):
            continue
        logger.info("=" * 60)
        logger.info("[%d/%d] Processing: %s", i, total, item)
        r = download_movie(
            item, output_dir, token,
            metadata_only=metadata_only,
            dry_run=dry_run,
        )
        results.append(r)
    return results


def load_batch_file(path: Path) -> list[str]:
    """Read a file where each non-empty, non-comment line is a URL/UID."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
