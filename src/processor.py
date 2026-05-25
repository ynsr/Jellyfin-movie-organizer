"""
Per-movie processing pipeline.

Runs Tasks 1-4 in order for a single video file.
Returns a summary dict for reporting.
"""

import logging
import re
from pathlib import Path
from typing import Optional

from src.scrapers.filimo import FilimoMovie, search as filimo_search
from src.services.backdrop import download_backdrop
from src.services.nfo import generate_nfo
from src.services.poster import download_poster
from src.services.renamer import rename_movie_file
from src.utils.name_parser import MovieInfo

logger = logging.getLogger(__name__)
_FUID_TAG_RE = re.compile(r"\[fuid-([A-Za-z0-9_-]+)\]", re.IGNORECASE)


def _extract_filimo_uid(filename: str) -> Optional[str]:
    match = _FUID_TAG_RE.search(filename)
    return match.group(1) if match else None


def _filimo_movie_from_metadata(meta) -> FilimoMovie:
    director_raw = getattr(meta, "director", "")
    if isinstance(director_raw, list):
        names = [d.get("name", "").strip() for d in director_raw if isinstance(d, dict)]
        director = " - ".join([n for n in names if n])
    else:
        director = str(director_raw or "")

    description = (
        getattr(meta, "description_en", "")
        or getattr(meta, "description_fa", "")
        or ""
    )

    return FilimoMovie(
        movie_id=str(getattr(meta, "uid", "")),
        uid=str(getattr(meta, "uid", "")),
        title_en=getattr(meta, "title_en", ""),
        title_fa=getattr(meta, "title_fa", ""),
        year=getattr(meta, "year", ""),
        poster_url=getattr(meta, "poster_url", ""),
        backdrop_url=getattr(meta, "backdrop_url", ""),
        imdb_rate=str(getattr(meta, "imdb_rate", "")),
        description=description,
        duration_seconds=int(getattr(meta, "duration_seconds", 0) or 0),
        categories=getattr(meta, "categories", []) or [],
        countries=getattr(meta, "countries", []) or [],
        director=director,
        age_range=getattr(meta, "age_range", ""),
    )


def process_movie(
    video_path: Path,
    *,
    skip_rename: bool = False,
    skip_poster: bool = False,
    skip_backdrop: bool = False,
    skip_nfo: bool = False,
    dry_run: bool = False,
) -> dict:
    """
    Run the full pipeline for a single movie file.
    Returns a result dict with keys: file, renamed, poster, backdrop, nfo, error.
    """
    result = {
        "file": video_path.name,
        "renamed": False,
        "poster": False,
        "backdrop": False,
        "nfo": False,
        "error": None,
    }

    # ------------------------------------------------------------------ #
    # Task 1: Rename
    # ------------------------------------------------------------------ #
    movie_info: Optional[MovieInfo] = None
    current_path = video_path
    filimo_uid = _extract_filimo_uid(video_path.name)

    if not skip_rename:
        rename_result = rename_movie_file(current_path, dry_run=dry_run)
        if rename_result is None:
            result["error"] = "Could not determine IMDB data; skipping remaining tasks."
            logger.error("Skipping %s — no IMDB data found.", video_path.name)
            return result

        current_path, movie_info = rename_result
        result["renamed"] = True
        result["file"] = current_path.name
    else:
        # Even if rename is skipped, we need MovieInfo from the (already correct) filename
        from src.utils.name_parser import MovieInfo as MI
        movie_info = MI.from_jellyfin_filename(current_path)
        if movie_info is None:
            result["error"] = "File not in Jellyfin format and --skip-rename is set."
            logger.error(
                "Cannot process %s: not Jellyfin format and rename is skipped.",
                video_path.name,
            )
            return result

    movie_dir = current_path.parent

    # ------------------------------------------------------------------ #
    # Shared Filimo lookup (reused by Tasks 2, 3, 4)
    # ------------------------------------------------------------------ #
    filimo_movie = None
    if filimo_uid:
        try:
            from src.services.filimo_downloader import fetch_metadata, get_token
            meta = fetch_metadata(filimo_uid, get_token())
            filimo_movie = _filimo_movie_from_metadata(meta)
            logger.info("Filimo UID tag detected, using UID metadata: %s", filimo_uid)
        except Exception as exc:
            logger.warning("Filimo UID metadata fetch failed for %s: %s", filimo_uid, exc)

    if not filimo_movie:
        filimo_movie = filimo_search(movie_info.name, movie_info.year)

    # ------------------------------------------------------------------ #
    # Task 2: Poster
    # ------------------------------------------------------------------ #
    if not skip_poster:
        result["poster"] = download_poster(
            movie_dir, movie_info, filimo_movie, dry_run=dry_run
        )

    # ------------------------------------------------------------------ #
    # Task 3: Backdrop
    # ------------------------------------------------------------------ #
    if not skip_backdrop:
        result["backdrop"] = download_backdrop(
            movie_dir, movie_info, filimo_movie, dry_run=dry_run
        )

    # ------------------------------------------------------------------ #
    # Task 4: NFO
    # ------------------------------------------------------------------ #
    if not skip_nfo:
        result["nfo"] = generate_nfo(
            movie_dir, movie_info, filimo_movie, dry_run=dry_run
        )

    return result
