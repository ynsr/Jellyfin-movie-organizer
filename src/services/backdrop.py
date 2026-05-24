"""
Task 3 — Download movie backdrop image from Filimo.
"""

import logging
from pathlib import Path
from typing import Optional

from config.settings import MISSED_BACKDROP_FILE
from src.scrapers.filimo import FilimoMovie
from src.utils.file_utils import append_missed, download_binary, ext_from_url
from src.utils.name_parser import MovieInfo

logger = logging.getLogger(__name__)


def _backdrop_destination(movie_dir: Path, info: MovieInfo, ext: str) -> Path:
    filename = info.file_name(suffix="-backdrop", extension=ext)
    return movie_dir / filename


def _has_existing_backdrop(movie_dir: Path, info: MovieInfo) -> bool:
    for path in movie_dir.iterdir():
        if path.stem == f"{info.base_name}-backdrop":
            return True
    return False


def download_backdrop(
    movie_dir: Path,
    info: MovieInfo,
    filimo_movie: Optional[FilimoMovie] = None,
    *,
    dry_run: bool = False,
) -> bool:
    """
    Download the movie backdrop into *movie_dir*.
    Returns True if backdrop was obtained or already existed.
    """
    if _has_existing_backdrop(movie_dir, info):
        logger.info("Backdrop already exists, skipping: %s", info.base_name)
        return True

    if not filimo_movie or not filimo_movie.backdrop_url:
        logger.warning("No Filimo backdrop available for: %s", info.base_name)
        append_missed(MISSED_BACKDROP_FILE, info.base_name)
        return False

    url = filimo_movie.backdrop_url
    ext = ext_from_url(url)
    dest = _backdrop_destination(movie_dir, info, ext)

    logger.info("Downloading backdrop from Filimo: %s", url)
    if dry_run:
        logger.info("[DRY RUN] Would download backdrop → %s", dest.name)
        return True

    if download_binary(url, dest):
        return True

    logger.warning("Backdrop download failed for: %s", info.base_name)
    append_missed(MISSED_BACKDROP_FILE, info.base_name)
    return False
