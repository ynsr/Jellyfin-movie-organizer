"""
Doostihaa.com poster scraper.

Flow:
  1. Use Bertina to find the Doostihaa page URL for the movie.
  2. Fetch the page and extract the poster <img> src.
"""

import logging
from typing import Optional

from bs4 import BeautifulSoup

from config.settings import DOOSTIHAA_POSTER_SELECTORS
from src.scrapers.bertina import search_doostihaa
from src.utils.http_client import get

logger = logging.getLogger(__name__)


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

    for selector in DOOSTIHAA_POSTER_SELECTORS:
        img = soup.select_one(selector)
        if img and img.get("src"):
            src = img["src"].strip()
            # Make absolute URL if needed
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                from urllib.parse import urlparse
                base = urlparse(page_url)
                src = f"{base.scheme}://{base.netloc}{src}"
            logger.info("Doostihaa poster found via selector %r: %s", selector, src)
            return src

    logger.warning("No poster img found on Doostihaa page: %s", page_url)
    return None
