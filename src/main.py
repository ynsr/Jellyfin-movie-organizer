"""
Jellyfin Movie Organizer — entry point.

Usage:
    python -m src.main /path/to/movies [options]
"""

import argparse
import logging
import sys
from pathlib import Path

from config.settings import LOG_DIR, LOG_FILE
from src.processor import process_movie
from src.utils.file_utils import iter_video_files


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _setup_logging(verbose: bool = False) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt=datefmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
    )


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="jellyfin-organizer",
        description="Rename movies and fetch metadata/artwork for Jellyfin.",
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Directory containing movie files to process.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing any files.",
    )
    parser.add_argument(
        "--skip-rename",
        action="store_true",
        help="Skip Task 1 (file renaming). Files must already be in Jellyfin format.",
    )
    parser.add_argument(
        "--skip-poster",
        action="store_true",
        help="Skip Task 2 (poster download).",
    )
    parser.add_argument(
        "--skip-backdrop",
        action="store_true",
        help="Skip Task 3 (backdrop download).",
    )
    parser.add_argument(
        "--skip-nfo",
        action="store_true",
        help="Skip Task 4 (NFO generation).",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = _parse_args()
    _setup_logging(args.verbose)

    directory: Path = args.directory.resolve()
    if not directory.is_dir():
        logger.error("Not a directory: %s", directory)
        sys.exit(1)

    video_files = list(iter_video_files(directory))
    if not video_files:
        logger.warning("No video files found in: %s", directory)
        sys.exit(0)

    logger.info("Found %d video file(s) in: %s", len(video_files), directory)
    if args.dry_run:
        logger.info("*** DRY RUN mode — no files will be written ***")

    # ------------------------------------------------------------------ #
    # Process each movie
    # ------------------------------------------------------------------ #
    results = []
    for video_path in video_files:
        logger.info("=" * 60)
        logger.info("Processing: %s", video_path.name)
        result = process_movie(
            video_path,
            skip_rename=args.skip_rename,
            skip_poster=args.skip_poster,
            skip_backdrop=args.skip_backdrop,
            skip_nfo=args.skip_nfo,
            dry_run=args.dry_run,
        )
        results.append(result)

    # ------------------------------------------------------------------ #
    # Summary report
    # ------------------------------------------------------------------ #
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)

    total = len(results)
    renamed = sum(1 for r in results if r["renamed"])
    poster_ok = sum(1 for r in results if r["poster"])
    backdrop_ok = sum(1 for r in results if r["backdrop"])
    nfo_ok = sum(1 for r in results if r["nfo"])
    errors = [r for r in results if r["error"]]

    logger.info("Total files   : %d", total)
    if not args.skip_rename:
        logger.info("Renamed       : %d", renamed)
    if not args.skip_poster:
        logger.info("Poster OK     : %d / %d", poster_ok, total)
    if not args.skip_backdrop:
        logger.info("Backdrop OK   : %d / %d", backdrop_ok, total)
    if not args.skip_nfo:
        logger.info("NFO OK        : %d / %d", nfo_ok, total)

    if errors:
        logger.warning("Errors        : %d", len(errors))
        for r in errors:
            logger.warning("  ✗ %s — %s", r["file"], r["error"])

    logger.info("Log saved to: %s", LOG_FILE)


if __name__ == "__main__":
    main()
