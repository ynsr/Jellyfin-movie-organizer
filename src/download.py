"""
Filimo Movie Downloader — CLI entry point.

Usage examples
--------------
# Single movie by UID
python -m src.download aVmdY --output ~/Movies

# Single movie by URL
python -m src.download "https://www.filimo.com/m/aVmdY/..." --output ~/Movies

# Batch file (one UID/URL per line)
python -m src.download --batch /path/to/list.txt --output ~/Movies

# Metadata + images only (no video download)
python -m src.download aVmdY --output ~/Movies --metadata-only

# Dry run
python -m src.download aVmdY --output ~/Movies --dry-run

# Provide / refresh JWT token
python -m src.download aVmdY --output ~/Movies --token "eyJhbGci..."
"""

import argparse
import logging
import sys
from pathlib import Path

from config.settings import LOG_DIR, LOG_FILE
from src.services.filimo_downloader import (
    download_batch,
    download_movie,
    get_token,
    load_batch_file,
)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _setup_logging(verbose: bool = False) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level  = logging.DEBUG if verbose else logging.INFO
    fmt    = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
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
        prog="filimo-download",
        description=(
            "Download movies from Filimo.com with Jellyfin-compatible naming.\n"
            "Input can be a Filimo UID, short URL, or full movie URL."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ── Input ──────────────────────────────────────────────────────────
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "target",
        nargs="?",
        metavar="UID_OR_URL",
        help="Movie UID, short URL, or full Filimo URL.",
    )
    input_group.add_argument(
        "--batch",
        metavar="FILE",
        type=Path,
        help="Text file with one UID/URL per line (# lines are comments).",
    )

    # ── Output ─────────────────────────────────────────────────────────
    parser.add_argument(
        "--output", "-o",
        metavar="DIR",
        type=Path,
        default=Path("downloads"),
        help="Root output directory. Each movie gets its own sub-folder. Default: ./downloads",
    )

    # ── Auth ───────────────────────────────────────────────────────────
    parser.add_argument(
        "--token",
        metavar="JWT",
        default=None,
        help=(
            "Filimo JWT token (without 'Bearer '). "
            "Saved to ~/.jellyfin-organizer/filimo_token.json for future use."
        ),
    )

    # ── Behaviour flags ────────────────────────────────────────────────
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Skip video download; only fetch poster, backdrop, and generate NFO.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without writing any files or downloading.",
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

    if args.dry_run:
        logger.info("*** DRY RUN mode — no files will be written ***")

    # ── Resolve output directory ────────────────────────────────────────
    output_dir: Path = args.output.resolve()
    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Output directory: %s", output_dir)

    # ── Resolve token ───────────────────────────────────────────────────
    try:
        token = get_token(args.token)
    except RuntimeError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    # ── Build item list ─────────────────────────────────────────────────
    if args.batch:
        if not args.batch.is_file():
            logger.error("Batch file not found: %s", args.batch)
            sys.exit(1)
        items = load_batch_file(args.batch)
        if not items:
            logger.warning("Batch file is empty: %s", args.batch)
            sys.exit(0)
        logger.info("Batch mode: %d item(s) from %s", len(items), args.batch)
    else:
        items = [args.target]

    # ── Process ─────────────────────────────────────────────────────────
    results = download_batch(
        items,
        output_dir,
        token,
        metadata_only=args.metadata_only,
        dry_run=args.dry_run,
    )

    # ── Summary ─────────────────────────────────────────────────────────
    total     = len(results)
    ok_video  = sum(1 for r in results if r["video"])
    ok_poster = sum(1 for r in results if r["poster"])
    ok_nfo    = sum(1 for r in results if r["nfo"])
    errors    = [r for r in results if r["error"]]

    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info("Total processed : %d", total)
    if not args.metadata_only:
        logger.info("Video downloaded: %d / %d", ok_video, total)
    logger.info("Poster OK       : %d / %d", ok_poster, total)
    logger.info("NFO OK          : %d / %d", ok_nfo, total)

    if errors:
        logger.warning("Errors          : %d", len(errors))
        for r in errors:
            logger.warning("  ✗ %s — %s", r["uid"], r["error"])

    logger.info("Log saved to: %s", LOG_FILE)

    sys.exit(1 if errors and len(errors) == total else 0)


if __name__ == "__main__":
    main()
