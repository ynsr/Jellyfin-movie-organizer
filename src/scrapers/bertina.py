"""
Bertina search engine scraper.

Handles two use-cases:
1. Find an IMDB page for a raw movie filename.
2. Find a Doostihaa page for a known movie name + year.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from config.settings import (
    BERTINA_DOOSTIHAA_QUERY_SUFFIX,
    BERTINA_IMDB_QUERY_SUFFIX,
    BERTINA_SEARCH_URL,
)
from src.utils.http_client import get

logger = logging.getLogger(__name__)

_IMDB_TITLE_RE = re.compile(r"imdb\.com/title/((?:tt|vi)\d+)", re.IGNORECASE)
_IMDB_TITLE_YEAR_RE = re.compile(r"^(.+?)\s*\((?:\w+ )?(\d{4})\)(?: - [a-zA-Z0-9& ]+)?")


@dataclass
class BertinaImdbResult:
    title: str
    year: str
    imdb_id: str
    url: str


@dataclass
class BertinaLinkResult:
    url: str
    title: str


def _article_href_and_text(article) -> Optional[tuple[str, str]]:
    """
    Extract (href, link_text) from a Bertina <article> block.
    """
    anchor = article.find("a", href=True)
    cite = article.find("cite")
    link_text = ""
    if anchor:
        link_text = anchor.get_text(strip=True)
    elif cite:
        link_text = cite.get_text(strip=True)
    url = ""
    if cite:
        url = (cite.get("title") or cite.get_text(strip=True) or "").strip()
    if not url and anchor:
        url = anchor["href"].strip()
    if not url:
        return None
    return url, link_text


def _first_article_href_and_text_matching(html: str, url_filter) -> Optional[tuple[str, str]]:
    """
    Parse Bertina results and return (href, link_text) for the first matching article.
    """
    soup = BeautifulSoup(html, "lxml")
    for article in soup.select("article"):
        result = _article_href_and_text(article)
        if not result:
            continue
        url, link_text = result
        if url_filter(url):
            return url, link_text
    return None

def search_imdb(raw_filename_stem: str) -> Optional[BertinaImdbResult]:
    """
    Search Bertina for an IMDB page matching *raw_filename_stem*.
    Returns structured result on success, None on failure.
    """
    query = f"{raw_filename_stem} {BERTINA_IMDB_QUERY_SUFFIX}"
    url = f"{BERTINA_SEARCH_URL}?q={quote_plus(query)}"
    logger.debug("Bertina IMDB search: %s", url)

    try:
        response = get(url)
    except RuntimeError as exc:
        logger.error("Bertina IMDB search failed: %s", exc)
        return None

    result = _first_article_href_and_text_matching(response.text, lambda _url: "www.imdb.com" in _url)
    if not result:
        logger.warning("No Bertina results for IMDB query: %s", raw_filename_stem)
        return None

    href, link_text = result

    # Extract IMDB ID from the URL
    id_match = _IMDB_TITLE_RE.search(href)
    if not id_match:
        # Try the cite element text as fallback
        soup = BeautifulSoup(response.text, "lxml")
        cite = soup.select_one("article cite")
        if cite:
            id_match = _IMDB_TITLE_RE.search(cite.get_text())
    if not id_match:
        logger.warning("IMDB ID not found in Bertina result href: %s", href)
        return None

    imdb_id = id_match.group(1)

    # Extract title + year from link text like "Movie Name (2022) - IMDb"
    clean_text = link_text.replace("- IMDb", "").strip()
    title_year_match = _IMDB_TITLE_YEAR_RE.match(clean_text)
    if not title_year_match:
        logger.warning("Could not parse title/year from Bertina text: %r", link_text)
        return None

    title = title_year_match.group(1).strip()
    year = title_year_match.group(2)

    logger.info("Bertina IMDB → %s (%s) [%s]", title, year, imdb_id)
    return BertinaImdbResult(title=title, year=year, imdb_id=imdb_id, url=href)


def search_doostihaa(movie_name: str, year: str) -> Optional[BertinaLinkResult]:
    """
    Search Bertina for a Doostihaa page for *movie_name* + *year*.
    Returns the URL of the first matching page, or None.
    """
    query = f"{movie_name} {year} {BERTINA_DOOSTIHAA_QUERY_SUFFIX}"
    url = f"{BERTINA_SEARCH_URL}?q={quote_plus(query)}"
    logger.debug("Bertina Doostihaa search: %s", url)

    try:
        response = get(url)
    except RuntimeError as exc:
        logger.error("Bertina Doostihaa search failed: %s", exc)
        return None

    result = _first_article_href_and_text_matching(
        response.text,
        lambda url: "doostihaa.com" in url or "doostiha.com" in url,
    )
    if not result:
        logger.warning("No Bertina Doostihaa results for: %s %s", movie_name, year)
        return None

    href, link_text = result

    logger.info("Bertina Doostihaa → %s", href)
    return BertinaLinkResult(url=href, title=link_text)
