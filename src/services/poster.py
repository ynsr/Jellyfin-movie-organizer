"""
Task 2 — Download movie poster.

Source priority:
  1. Filimo (pic.movie_img_b)
  2. Doostihaa (scraped img tag)

If no poster is found, the movie is logged in movies-missed-poster.txt.
"""

import logging
from pathlib import Path
from typing import Optional

from config.settings import MISSED_POSTER_FILE
from src.scrapers.doostihaa import find_poster_url as doostihaa_find_poster
from src.scrapers.filimo import FilimoMovie
from src.utils.file_utils import append_missed, download_binary, ext_from_url
from src.utils.name_parser import MovieInfo

logger = logging.getLogger(__name__)


def _poster_destination(movie_dir: Path, info: MovieInfo, ext: str) -> Path:
    filename = info.file_name(suffix="-poster", extension=ext)
    return movie_dir / filename


def _has_existing_poster(movie_dir: Path, info: MovieInfo) -> bool:
    """Return True if any poster file already exists for this movie."""
    for path in movie_dir.iterdir():
        if path.stem == f"{info.base_name}-poster":
            return True
    return False


def download_poster(
    movie_dir: Path,
    info: MovieInfo,
    filimo_movie: Optional[FilimoMovie] = None,
    *,
    dry_run: bool = False,
) -> bool:
    """
    Download the movie poster into *movie_dir*.
    Returns True if poster was obtained or already existed.
    """
    if _has_existing_poster(movie_dir, info):
        logger.info("Poster already exists, skipping: %s", info.base_name)
        return True

    # ------------------------------------------------------------------ #
    # Source 1: Filimo
    # ------------------------------------------------------------------ #
    if filimo_movie and filimo_movie.poster_url:
        url = filimo_movie.poster_url
        ext = ext_from_url(url)
        dest = _poster_destination(movie_dir, info, ext)
        logger.info("Downloading poster from Filimo: %s", url)
        if dry_run:
            logger.info("[DRY RUN] Would download poster → %s", dest.name)
            return True
        if download_binary(url, dest):
            return True
        logger.warning("Filimo poster download failed, trying Doostihaa…")

    # ------------------------------------------------------------------ #
    # Source 2: Doostihaa
    # ------------------------------------------------------------------ #
    logger.info("Trying Doostihaa poster for: %s (%s)", info.name, info.year)
    poster_url = doostihaa_find_poster(info.name, info.year)
    if poster_url:
        ext = ext_from_url(poster_url)
        dest = _poster_destination(movie_dir, info, ext)
        if dry_run:
            logger.info("[DRY RUN] Would download poster → %s", dest.name)
            return True
        if download_binary(poster_url, dest):
            return True

    # ------------------------------------------------------------------ #
    # All sources exhausted
    # ------------------------------------------------------------------ #
    logger.warning("Poster not found for: %s", info.base_name)
    append_missed(MISSED_POSTER_FILE, info.base_name)
    return False
