"""
Utilities for parsing and building Jellyfin-compatible movie file names.

Jellyfin format:
    {Movie Name} ({Year}) [imdbid-{ttXXXXXX}]{suffix}.{ext}

Example:
    Chickenhare and the Hamster of Darkness (2022) [imdbid-tt12532368].mp4
    Chickenhare and the Hamster of Darkness (2022) [imdbid-tt12532368]-poster.jpg
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from config.settings import JELLYFIN_MOVIE_PATTERN

_JELLYFIN_RE = re.compile(JELLYFIN_MOVIE_PATTERN)


@dataclass
class MovieInfo:
    name: str
    year: str
    imdb_id: str
    suffix: str = ""         # e.g. "-poster", "-backdrop"
    extension: str = ""      # e.g. ".mp4", ".jpg"  (includes leading dot)

    # ------------------------------------------------------------------ #
    # Builders
    # ------------------------------------------------------------------ #

    @property
    def base_name(self) -> str:
        """Stem without suffix: 'Movie Name (2022) [imdbid-ttXXX]'"""
        return f"{self.name} ({self.year}) [imdbid-{self.imdb_id}]"

    def file_name(self, suffix: str = "", extension: str = "") -> str:
        """Return a full file name, overriding suffix/extension if provided."""
        sfx = suffix or self.suffix
        ext = extension or self.extension
        return f"{self.base_name}{sfx}{ext}"

    # ------------------------------------------------------------------ #
    # Parsing
    # ------------------------------------------------------------------ #

    @classmethod
    def from_jellyfin_filename(cls, path: Path) -> Optional["MovieInfo"]:
        """
        Parse a Path whose stem already follows the Jellyfin convention.
        Returns None if the stem doesn't match.
        """
        stem = path.stem
        ext = path.suffix
        m = _JELLYFIN_RE.match(stem)
        if not m:
            return None
        return cls(
            name=m.group("name"),
            year=m.group("year"),
            imdb_id=m.group("imdb_id"),
            suffix=m.group("suffix") or "",
            extension=ext,
        )


def build_jellyfin_name(name: str, year: str, imdb_id: str, extension: str) -> str:
    """Return the canonical Jellyfin movie file name (with extension)."""
    ext = extension if extension.startswith(".") else f".{extension}"
    return f"{name} ({year}) [imdbid-{imdb_id}]{ext}"


def is_jellyfin_format(path: Path) -> bool:
    """Return True if the path stem matches the Jellyfin naming convention."""
    return MovieInfo.from_jellyfin_filename(path) is not None


def sanitize_movie_name(raw: str) -> str:
    """
    Remove characters that are illegal in Windows/Linux file names
    and collapse extra whitespace.
    """
    illegal = r'\/:*?"<>|'
    for ch in illegal:
        raw = raw.replace(ch, "")
    return " ".join(raw.split())
