"""
Shared HTTP session with retry / back-off logic.
All network code must go through this module so settings stay centralised.
"""

import logging
import time
from typing import Any

import requests
from requests import Response, Session

from config.settings import (
    HTTP_BACKOFF_FACTOR,
    HTTP_MAX_RETRIES,
    HTTP_TIMEOUT,
    REQUEST_HEADERS,
)

logger = logging.getLogger(__name__)

_session: Session | None = None


def get_session() -> Session:
    """Return (or lazily create) a shared requests Session."""
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(REQUEST_HEADERS)
    return _session


def _request_with_retry(
    method: str,
    url: str,
    *,
    stream: bool = False,
    **kwargs: Any,
) -> Response:
    """Issue an HTTP request with exponential back-off on failures."""
    session = get_session()
    last_exc: Exception | None = None

    for attempt in range(1, HTTP_MAX_RETRIES + 1):
        try:
            response = session.request(
                method,
                url,
                timeout=HTTP_TIMEOUT,
                stream=stream,
                **kwargs,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_exc = exc
            wait = HTTP_BACKOFF_FACTOR * (2 ** (attempt - 1))
            logger.warning(
                "HTTP %s %s — attempt %d/%d failed: %s. Retrying in %.1fs…",
                method.upper(),
                url,
                attempt,
                HTTP_MAX_RETRIES,
                exc,
                wait,
            )
            time.sleep(wait)

    raise RuntimeError(
        f"All {HTTP_MAX_RETRIES} attempts failed for {url}"
    ) from last_exc


def get(url: str, **kwargs: Any) -> Response:
    return _request_with_retry("GET", url, **kwargs)


def get_stream(url: str, **kwargs: Any) -> Response:
    return _request_with_retry("GET", url, stream=True, **kwargs)
