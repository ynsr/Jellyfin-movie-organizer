"""
Doostihaa.com poster scraper.

Flow:
  1. Use Bertina to find the Doostihaa page URL for the movie.
  2. Fetch the page and extract the poster <img> src.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup

from config.settings import DOOSTIHAA_POSTER_SELECTORS
from src.scrapers.bertina import search_doostihaa
from src.scrapers.filimo import FilimoMovie
from src.utils.http_client import get

logger = logging.getLogger(__name__)

_PERSIAN_DIGIT_TABLE = str.maketrans(
    "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9",
    "0123456789",
)

_META_KEYWORDS = (
    "نام",
    "ژانر",
    "تاریخ انتشار",
    "انتشار",
    "سال تولید",
    "سال ساخت",
    "مدت",
    "مدت زمان",
    "زمان",
    "محصول",
    "کارگردان",
    "امتیاز",
    "زبان",
    "کیفیت",
    "فرمت",
    "حجم",
    "قسمت",
    "زیرنویس",
)


@dataclass
class DoostihaaMetadata:
    title_fa: str = ""
    title_en: str = ""
    year: str = ""
    plot: str = ""
    imdb_rate: str = ""
    duration_minutes: int = 0
    genres: list[str] = None
    countries: list[str] = None
    director: str = ""
    poster_url: str = ""

    def __post_init__(self) -> None:
        if self.genres is None:
            self.genres = []
        if self.countries is None:
            self.countries = []


def _normalize_digits(text: str) -> str:
    return text.translate(_PERSIAN_DIGIT_TABLE).replace("٫", ".").replace("٬", "")


def _clean_line(text: str) -> str:
    return " ".join(text.split()).strip()


def _contains_persian(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text))


def _split_list(text: str) -> list[str]:
    parts = re.split(r"\s*(?:،|,| و |/|\+|\||\u200c)\s*", text)
    return [p.strip() for p in parts if p.strip()]


def _looks_like_metadata(line: str) -> bool:
    if ":" not in line:
        return False
    return any(keyword in line for keyword in _META_KEYWORDS)


def _extract_plot(lines: list[str]) -> str:
    for i, line in enumerate(lines):
        if line.startswith("خلاصه داستان"):
            remainder = line.split(":", 1)[1].strip() if ":" in line else ""
            parts = [remainder] if remainder else []
            for j in range(i + 1, len(lines)):
                candidate = lines[j]
                if _looks_like_metadata(candidate):
                    break
                parts.append(candidate)
            return _clean_line(" ".join(parts))
    return ""


def _split_title(value: str) -> tuple[str, str]:
    raw = value.strip()
    for sep in ("–", "—", "-"):
        if sep in raw:
            left, right = [p.strip() for p in raw.split(sep, 1)]
            if _contains_persian(left) and not _contains_persian(right):
                return left, right
            if _contains_persian(right) and not _contains_persian(left):
                return right, left
            return left, right
    if _contains_persian(raw):
        return raw, ""
    return "", raw


def _extract_year(segment: str) -> str:
    years = re.findall(r"[0-9\u06f0-\u06f9]{4}", segment)
    return _normalize_digits(years[0]) if years else ""


def _extract_duration_minutes(segment: str) -> int:
    match = re.search(r"([0-9\u06f0-\u06f9]+)\s*دقیقه", segment)
    if not match:
        return 0
    raw = _normalize_digits(match.group(1))
    return int(raw) if raw.isdigit() else 0


def _extract_imdb_rate(segment: str) -> str:
    match = re.search(
        r"امتیاز(?:\s*فیلم)?\s*:?[^0-9\u06f0-\u06f9]*([0-9\u06f0-\u06f9]+(?:[\.,٫][0-9\u06f0-\u06f9]+)?)",
        segment,
    )
    if not match:
        return ""
    return _normalize_digits(match.group(1)).replace(",", ".")


def parse_metadata_text(text: str) -> DoostihaaMetadata:
    lines = [_clean_line(line) for line in text.splitlines() if _clean_line(line)]
    meta = DoostihaaMetadata()

    for line in lines:
        for segment in [s.strip() for s in line.split("|") if s.strip()]:
            if "نام" in segment and ":" in segment:
                value = segment.split(":", 1)[1].strip()
                title_fa, title_en = _split_title(value)
                if title_fa and not meta.title_fa:
                    meta.title_fa = title_fa
                if title_en and not meta.title_en:
                    meta.title_en = title_en

            if "ژانر" in segment:
                value = segment.split("ژانر", 1)[1]
                if ":" in value:
                    value = value.split(":", 1)[1]
                meta.genres.extend(_split_list(value))

            if "محصول" in segment:
                value = segment.split("محصول", 1)[1]
                value = value.replace("کشور", "").strip()
                meta.countries.extend(_split_list(value))

            if "کارگردان" in segment and ":" in segment:
                value = segment.split(":", 1)[1].strip()
                if value:
                    meta.director = value

            if any(key in segment for key in ("تاریخ انتشار", "انتشار", "سال تولید", "سال ساخت", "سال")):
                year = _extract_year(segment)
                if year and not meta.year:
                    meta.year = year

            if "دقیقه" in segment and ("مدت" in segment or "زمان" in segment):
                minutes = _extract_duration_minutes(segment)
                if minutes and not meta.duration_minutes:
                    meta.duration_minutes = minutes

            if "امتیاز" in segment:
                rate = _extract_imdb_rate(segment)
                if rate and not meta.imdb_rate:
                    meta.imdb_rate = rate

    meta.plot = _extract_plot(lines)
    return meta


def _extract_poster_url(soup: BeautifulSoup, page_url: str) -> Optional[str]:
    for selector in DOOSTIHAA_POSTER_SELECTORS:
        img = soup.select_one(selector)
        if img and img.get("src"):
            src = img["src"].strip()
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                from urllib.parse import urlparse
                base = urlparse(page_url)
                src = f"{base.scheme}://{base.netloc}{src}"
            return src
    return None


def find_poster_url(movie_name: str, year: str) -> Optional[str]:
    """
    Find the poster image URL for *movie_name* + *year* on Doostihaa.
    Returns the src URL string, or None if not found.
    """
    bertina_result = search_doostihaa(movie_name, year)
    if not bertina_result:
        return None

    page_url = bertina_result.url
    logger.debug("Fetching Doostihaa page: %s", page_url)

    try:
        response = get(page_url)
    except RuntimeError as exc:
        logger.error("Could not fetch Doostihaa page %s: %s", page_url, exc)
        return None

    soup = BeautifulSoup(response.text, "lxml")
    poster = _extract_poster_url(soup, page_url)
    if poster:
        logger.info("Doostihaa poster found via selectors: %s", poster)
        return poster

    logger.warning("No poster img found on Doostihaa page: %s", page_url)
    return None


def extract_metadata_from_html(html: str) -> DoostihaaMetadata:
    soup = BeautifulSoup(html, "lxml")
    article = soup.select_one("article")
    source = article if article else soup
    text = source.get_text("\n", strip=True)
    return parse_metadata_text(text)


def fetch_metadata(movie_name: str, year: str) -> Optional[FilimoMovie]:
    bertina_result = search_doostihaa(movie_name, year)
    if not bertina_result:
        return None

    page_url = bertina_result.url
    logger.debug("Fetching Doostihaa page for metadata: %s", page_url)

    try:
        response = get(page_url)
    except RuntimeError as exc:
        logger.error("Could not fetch Doostihaa page %s: %s", page_url, exc)
        return None

    soup = BeautifulSoup(response.text, "lxml")
    metadata = extract_metadata_from_html(response.text)
    metadata.poster_url = _extract_poster_url(soup, page_url) or ""

    if not metadata.year:
        metadata.year = _normalize_digits(year)
    if not metadata.title_fa and not metadata.title_en:
        metadata.title_en = movie_name

    if not any([metadata.title_fa, metadata.title_en, metadata.plot, metadata.year]):
        logger.warning("No metadata parsed from Doostihaa page: %s", page_url)
        return None

    categories = [{"title_en": g} for g in metadata.genres]
    countries = [{"country_en": c} for c in metadata.countries]

    return FilimoMovie(
        movie_id="",
        uid="",
        title_en=metadata.title_en,
        title_fa=metadata.title_fa,
        year=metadata.year,
        poster_url=metadata.poster_url,
        backdrop_url="",
        imdb_rate=metadata.imdb_rate,
        description=metadata.plot,
        duration_seconds=metadata.duration_minutes * 60,
        categories=categories,
        countries=countries,
        director=metadata.director,
        age_range="",
    )
