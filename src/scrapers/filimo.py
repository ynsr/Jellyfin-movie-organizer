"""
Filimo.com API client.

The Filimo search API returns JSON that lists movies with Persian and English
titles, year, poster (pic.movie_img_b) and backdrop (cover).

Encoding notes (based on real API responses):
  - The API response is UTF-8; requests decodes it automatically via .json().
  - Persian text fields (movie_title, descr, director, countries…) are
    returned as proper Unicode strings — no extra decoding needed.
  - `pro_year` contains Persian-Indic digits (e.g. "۲۰۱۷"). Use
    _normalize_year() to convert to ASCII before any integer comparison.
  - URL fields (cover, pic.*) may contain JSON-escaped forward-slashes
    (backslash + slash) which Python's json decoder unescapes to "/" automatically —
    the resulting strings are valid HTTPS URLs and need no further treatment.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote

from config.settings import FILIMO_SEARCH_URL, FILIMO_YEAR_TOLERANCE
from src.utils.http_client import get

logger = logging.getLogger(__name__)

# Persian-Indic digit range U+06F0–U+06F9 → ASCII '0'–'9'
_PERSIAN_DIGIT_TABLE = str.maketrans(
    "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9",
    "0123456789",
)


@dataclass
class FilimoMovie:
    movie_id: str
    uid: str
    title_en: str  # movie_title_en  (ASCII/Latin)
    title_fa: str  # movie_title     (Persian Unicode)
    year: str  # pro_year → normalised to ASCII digits
    poster_url: str  # pic.movie_img_b (unescaped HTTPS URL)
    backdrop_url: str  # cover           (unescaped HTTPS URL)
    imdb_rate: str
    description: str  # descr           (Persian Unicode)
    duration_seconds: int
    categories: list[dict] = field(default_factory=list)
    countries: list[dict] = field(default_factory=list)
    director: str = ""  # director        (Persian Unicode)
    age_range: str = ""


def normalize_year(raw: str) -> str:
    """
    Convert a year string that may contain Persian-Indic digits to ASCII.

    Example: "۲۰۱۷" → "2017", "2022" → "2022"
    """
    return raw.strip().translate(_PERSIAN_DIGIT_TABLE)


# Keep the private alias so existing internal callers and tests still work.
_normalize_year = normalize_year


def _clean_url(url: str) -> str:
    """
    Ensure a URL from the Filimo API is a clean, usable HTTPS string.

    Python's json.loads already unescapes backslash-slash sequences to plain
    forward slashes, so in practice this is a no-op. The explicit replace is
    a safety net for any edge-case where the string arrives pre-parsed.
    """
    return url.replace("\\/", "/").strip()


def _parse_movie(item: dict) -> Optional[FilimoMovie]:
    """Parse a single 'movies' entry from the Filimo `included` list."""
    attrs = item.get("attributes", {})
    try:
        raw_year = str(attrs.get("pro_year", ""))
        ascii_year = normalize_year(raw_year)

        poster_url = _clean_url(attrs.get("pic", {}).get("movie_img_b", ""))
        backdrop_url = _clean_url(attrs.get("cover", ""))

        return FilimoMovie(
            movie_id=str(attrs.get("movie_id", "")),
            uid=str(attrs.get("uid", "")),
            title_en=attrs.get("movie_title_en", ""),
            title_fa=attrs.get("movie_title", ""),  # already decoded Unicode
            year=ascii_year,
            poster_url=poster_url,
            backdrop_url=backdrop_url,
            imdb_rate=str(attrs.get("imdb_rate", "")),
            description=attrs.get("descr", ""),  # already decoded Unicode
            duration_seconds=int(attrs.get("duration", {}).get("value", 0)),
            categories=attrs.get("categories", []),
            countries=attrs.get("countries", []),
            director=attrs.get("director", ""),  # already decoded Unicode
            age_range=attrs.get("age_range", ""),
        )
    except Exception as exc:
        logger.debug("Failed to parse Filimo item id=%s — %s", attrs.get("movie_id"), exc)
        return None


def _title_similarity(a: str, b: str) -> float:
    """
    Lightweight word-overlap similarity after normalizing punctuation/stopwords.

    Ignores ":", "-", "&", "'", and the token "and" when comparing titles.
    Case-insensitive. Sufficient for movie title matching without extra deps.
    """
    if not a or not b:
        return 0.0

    def _words(text: str) -> set[str]:
        normalized = text.lower()
        for char in (":", "-", "&", "_", "."):
            normalized = normalized.replace(char, " ")
        for char in ("'", '"'):
            normalized = normalized.replace(char, "")
        return {word for word in normalized.split() if word and word != "and"}

    words_a = _words(a)
    words_b = _words(b)
    if not words_a:
        return 0.0
    return len(words_a & words_b) / len(words_a)


def _decode_response(response) -> dict:
    """
    Safely decode the Filimo API response as UTF-8 JSON.

    requests infers encoding from headers; Filimo sometimes omits the
    charset, so we force UTF-8 before calling .json() to guarantee
    Persian text is decoded correctly.
    """
    response.encoding = "utf-8"
    return response.json()


def search(movie_name: str, year: str) -> Optional[FilimoMovie]:
    """
    Search Filimo for *movie_name* + *year* and return the best-matching item.

    Matching rules:
      1. Year must be within FILIMO_YEAR_TOLERANCE of the target year.
      2. English title word-overlap score must be ≥ 0.75.

    Returns the highest-scoring candidate, or None.
    """
    query = quote(f"{movie_name} {year}")
    url = FILIMO_SEARCH_URL.format(query=query)
    logger.debug("Filimo search: %s", url)

    try:
        response = get(url)
        data = _decode_response(response)
    except Exception as exc:
        logger.error("Filimo search failed [%s %s]: %s", movie_name, year, exc)
        return None

    included = data.get("included", [])
    candidates: list[tuple[float, FilimoMovie]] = []

    target_year = int(year) if year.isdigit() else None

    for item in included:
        if item.get("type") != "movies":
            continue
        movie = _parse_movie(item)
        if not movie:
            continue

        # ── Year filter ──────────────────────────────────────────────────
        if target_year and movie.year.isdigit():
            if abs(int(movie.year) - target_year) > FILIMO_YEAR_TOLERANCE:
                logger.debug(
                    "Year mismatch for '%s': got %s, want %s",
                    movie.title_en, movie.year, year,
                )
                continue

        # ── Title similarity ─────────────────────────────────────────────
        score = _title_similarity(movie_name, movie.title_en)
        logger.debug(
            "Filimo candidate '%s' (%s) — similarity=%.2f",
            movie.title_en, movie.year, score,
        )
        if score >= 0.75:
            candidates.append((score, movie))

    if not candidates:
        logger.info("No Filimo match for: %s (%s)", movie_name, year)
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_movie = candidates[0]
    logger.info(
        "Filimo match (score=%.2f): '%s' / '%s' (%s)",
        best_score, best_movie.title_en, best_movie.title_fa, best_movie.year,
    )
    return best_movie
