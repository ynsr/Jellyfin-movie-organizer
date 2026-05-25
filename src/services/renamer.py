"""
Task 1 — Rename movie files to Jellyfin-compatible format.

If the file is already in Jellyfin format, this step is skipped.
Otherwise, Bertina is queried for the IMDB data and the file is renamed.
"""

import logging
import re
from pathlib import Path
from typing import Optional

from src.scrapers.bertina import search_imdb
from src.utils.name_parser import (
    MovieInfo,
    build_jellyfin_name,
    is_jellyfin_format,
    sanitize_movie_name,
)

logger = logging.getLogger(__name__)
_TMDB_TAG_RE = re.compile(r"\[tmdbid-\d+\]", re.IGNORECASE)


def _rename_related_resources(
    movie_path: Path,
    info: MovieInfo,
    *,
    dry_run: bool = False,
) -> None:
    old_base = movie_path.stem
    movie_dir = movie_path.parent

    for path in movie_dir.iterdir():
        if not path.is_file() or path == movie_path:
            continue

        if path.stem == old_base and path.suffix.lower() == ".nfo":
            target = movie_dir / f"{info.base_name}.nfo"
        elif path.stem == f"{old_base}-poster":
            target = movie_dir / info.file_name(suffix="-poster", extension=path.suffix)
        elif path.stem == f"{old_base}-backdrop":
            target = movie_dir / info.file_name(suffix="-backdrop", extension=path.suffix)
        else:
            continue

        if target == path:
            continue
        if target.exists():
            logger.warning("Target already exists, skipping rename: %s", target.name)
            continue
        if dry_run:
            logger.info("[DRY RUN] Would rename: %s → %s", path.name, target.name)
            continue
        path.rename(target)
        logger.info("Renamed resource: %s → %s", path.name, target.name)


def rename_movie_file(
    movie_path: Path,
    *,
    dry_run: bool = False,
) -> Optional[tuple[Path, MovieInfo]]:
    """
    Rename *movie_path* to Jellyfin format.

    Returns (new_path, MovieInfo) on success, or None on failure.
    If the file is already in Jellyfin format, returns (movie_path, info) without renaming.
    """
    # Check if already in Jellyfin format
    existing_info = MovieInfo.from_jellyfin_filename(movie_path)
    if existing_info:
        logger.info("Already Jellyfin format, skipping rename: %s", movie_path.name)
        return movie_path, existing_info

    if _TMDB_TAG_RE.search(movie_path.name):
        logger.info("TMDB tag detected, skipping IMDB search: %s", movie_path.name)
        logger.error("TMDB tag found but filename is not Jellyfin format: %s", movie_path.name)
        return None

    stem = movie_path.stem
    extension = movie_path.suffix

    logger.info("Searching IMDB for: %s", stem)
    result = search_imdb(stem)
    if not result:
        logger.error("Could not find IMDB data for: %s", movie_path.name)
        return None

    clean_name = sanitize_movie_name(result.title)
    new_filename = build_jellyfin_name(clean_name, result.year, result.imdb_id, extension)
    new_path = movie_path.parent / new_filename
    renamed = False

    if new_path == movie_path:
        logger.info("Name unchanged after Jellyfin formatting: %s", movie_path.name)
    elif dry_run:
        logger.info("[DRY RUN] Would rename:\n  %s\n  → %s", movie_path.name, new_filename)
        renamed = True
    else:
        if new_path.exists():
            logger.warning("Target already exists, skipping rename: %s", new_path.name)
        else:
            movie_path.rename(new_path)
            logger.info("Renamed: %s → %s", movie_path.name, new_filename)
            renamed = True

    info = MovieInfo(
        name=clean_name,
        year=result.year,
        imdb_id=result.imdb_id,
        id_type="imdb",
        extension=extension,
    )
    if renamed:
        _rename_related_resources(movie_path, info, dry_run=dry_run)
    return new_path, info
