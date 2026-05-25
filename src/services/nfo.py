"""
Task 4 — Generate (or update) a Jellyfin-compatible .nfo file.

NFO format used by Jellyfin:
https://jellyfin.org/docs/general/server/media/movies.html

If an .nfo already exists, missing fields are merged in without overwriting
existing ones.
"""

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
from xml.dom import minidom

from config.settings import MISSED_NFO_FILE
from src.scrapers.filimo import FilimoMovie
from src.utils.file_utils import append_missed
from src.utils.name_parser import MovieInfo

logger = logging.getLogger(__name__)


def _nfo_path(movie_dir: Path, info: MovieInfo) -> Path:
    return movie_dir / f"{info.base_name}.nfo"


def _pretty_xml(root: ET.Element) -> str:
    raw = ET.tostring(root, encoding="unicode")
    parsed = minidom.parseString(raw)
    return parsed.toprettyxml(indent="  ", encoding=None)


def _set_if_missing(parent: ET.Element, tag: str, text: str) -> None:
    """Add *tag* with *text* to *parent* only if needed."""
    existing = parent.find(tag)
    normalized_existing = (existing.text or "").strip() if existing is not None else ""
    normalized_new = text.strip() if text else ""

    if (existing is None or (normalized_existing != normalized_new and tag == "title")) and text:
        el = ET.SubElement(parent, tag)
        el.text = text


def _load_or_create_root(nfo_path: Path) -> ET.Element:
    if nfo_path.exists():
        try:
            tree = ET.parse(nfo_path)
            return tree.getroot()
        except ET.ParseError as exc:
            logger.warning("Corrupt .nfo file, will overwrite: %s — %s", nfo_path, exc)
    root = ET.Element("movie")
    return root


def _normalize_year(raw: str) -> str:
    persian_digits = "۰۱۲۳۴۵۶۷۸۹"
    result = raw.strip()
    for i, pd in enumerate(persian_digits):
        result = result.replace(pd, str(i))
    return result


def generate_nfo(
    movie_dir: Path,
    info: MovieInfo,
    filimo_movie: Optional[FilimoMovie] = None,
    *,
    dry_run: bool = False,
) -> bool:
    """
    Create or update the .nfo file for a movie.
    Returns True on success.
    """
    if not filimo_movie:
        logger.warning("No Filimo data — cannot generate NFO for: %s", info.base_name)
        append_missed(MISSED_NFO_FILE, info.base_name)
        return False

    nfo_path = _nfo_path(movie_dir, info)
    root = _load_or_create_root(nfo_path)

    # ------------------------------------------------------------------ #
    # Populate fields (only fill missing ones)
    # ------------------------------------------------------------------ #
    _set_if_missing(root, "title", filimo_movie.title_fa or info.name)
    _set_if_missing(root, "originaltitle", filimo_movie.title_en or info.name)
    _set_if_missing(root, "sorttitle", info.name)

    year_str = _normalize_year(filimo_movie.year) if filimo_movie.year else info.year
    _set_if_missing(root, "year", year_str)

    _set_if_missing(root, "uniqueid", info.imdb_id)
    # <uniqueid type="imdb"> variant that Jellyfin also understands
    id_type = info.id_type
    existing_uid = root.find(f"uniqueid[@type='{id_type}']")
    if existing_uid is None:
        uid_el = ET.SubElement(root, "uniqueid")
        uid_el.set("type", id_type)
        uid_el.set("default", "true")
        uid_el.text = info.imdb_id

    # <uniqueid type="filimo">
    filimo_id_type = "filimo"
    filimo_existing_uid = root.find(f"uniqueid[@type='{filimo_id_type}']")
    if filimo_existing_uid is None and filimo_movie.uid:
        uid_el = ET.SubElement(root, "uniqueid")
        uid_el.set("type", filimo_id_type)
        uid_el.set("default", "true")
        uid_el.text = filimo_movie.uid

    _set_if_missing(root, "plot", filimo_movie.description)
    _set_if_missing(root, "rating", filimo_movie.imdb_rate)

    # Runtime in minutes
    if filimo_movie.duration_seconds:
        _set_if_missing(
            root, "runtime", str(filimo_movie.duration_seconds // 60)
        )

    # Genres
    existing_genres = {el.text for el in root.findall("genre")}
    for cat in filimo_movie.categories:
        genre = cat.get("title_en", "").capitalize()
        if genre and genre not in existing_genres:
            el = ET.SubElement(root, "genre")
            el.text = genre
            existing_genres.add(genre)

    # Country
    existing_countries = {el.text for el in root.findall("country")}
    for country_info in filimo_movie.countries:
        country = country_info.get("country_en", "").capitalize()
        if country and country not in existing_countries:
            el = ET.SubElement(root, "country")
            el.text = country

    # Director
    if filimo_movie.director:
        _set_if_missing(root, "director", filimo_movie.director)

    # Mpaa / age rating
    if filimo_movie.age_range:
        _set_if_missing(root, "mpaa", filimo_movie.age_range)

    # ------------------------------------------------------------------ #
    # Write
    # ------------------------------------------------------------------ #
    xml_str = _pretty_xml(root)

    if dry_run:
        logger.info("[DRY RUN] Would write NFO: %s\n%s", nfo_path, xml_str[:500])
        return True

    nfo_path.write_text(xml_str, encoding="utf-8")
    logger.info("NFO written: %s", nfo_path.name)
    return True
