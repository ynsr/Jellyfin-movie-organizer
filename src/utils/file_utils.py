"""
General file-system helpers used across the project.
"""

import logging
from pathlib import Path
from typing import Generator

from config.settings import VIDEO_EXTENSIONS

logger = logging.getLogger(__name__)


def iter_video_files(directory: Path) -> Generator[Path, None, None]:
    """Yield all video files (non-recursive) inside *directory*."""
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            yield path


def download_binary(url: str, destination: Path) -> bool:
    """
    Stream-download *url* and save to *destination*.
    Returns True on success, False on any error.
    """
    from src.utils.http_client import get_stream  # local import to avoid circular

    try:
        with get_stream(url) as response:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with open(destination, "wb") as fh:
                for chunk in response.iter_content(chunk_size=8192):
                    fh.write(chunk)
        logger.info("Downloaded: %s → %s", url, destination)
        return True
    except Exception as exc:
        logger.error("Download failed [%s]: %s", url, exc)
        return False


def append_missed(filepath: Path, entry: str) -> None:
    """Append *entry* as a new line to *filepath*, creating the file if needed."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "a", encoding="utf-8") as fh:
        fh.write(entry.strip() + "\n")


def ext_from_url(url: str, default: str = ".jpg") -> str:
    """Guess file extension from a URL path."""
    from urllib.parse import urlparse

    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    return suffix if suffix else default
