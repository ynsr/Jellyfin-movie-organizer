"""
Filimo Downloader — CLI entry point
====================================

Movie examples
--------------
  python -m src.download aVmdY --output ~/Movies
  python -m src.download "https://www.filimo.com/m/aVmdY/..." --output ~/Movies

Series examples
---------------
  python -m src.download 99963 --output ~/TV
  python -m src.download "https://www.filimo.com/n/99963" --output ~/TV
  python -m src.download "https://www.filimo.com/tag/frozen/n/99963" --output ~/TV

Batch (mix of movies and series)
---------------------------------
  python -m src.download --batch list.txt --output ~/Media

IDM integration
---------------
  python -m src.download 99963 --output ~/TV --idm
  python -m src.download 99963 --output ~/TV --idm --idm-queue "My Queue"
  # Generates: ./idm_downloads_<timestamp>.reg

Other flags
-----------
  --metadata-only    Skip video; only poster, backdrop, NFO
  --dry-run          Preview without writing files
  --token JWT        Supply/refresh JWT token
  -v / --verbose     Debug logging
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from config.app_config import get_config
from config.settings import LOG_DIR, LOG_FILE
from src.services.filimo_downloader import (
    download_batch,
    get_token,
    load_batch_file,
)
from src.services.idm_export import IdmEntry, generate_idm_reg


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _setup_logging(verbose: bool = False) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    logging.basicConfig(
        level=level, format=fmt, datefmt=datefmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
    )


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    cfg = get_config()  # ensures config file is generated on first run

    parser = argparse.ArgumentParser(
        prog="filimo-download",
        description=(
            "Download movies and TV series from Filimo.com\n"
            "with Jellyfin-compatible folder structure and naming.\n\n"
            "Movie input : UID (aVmdY), /m/{uid} URL, or full URL\n"
            "Series input: numeric ID (99963), /n/{id} URL, or /tag/.../n/{id} URL"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ── Input ──────────────────────────────────────────────────────────
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "target",
        nargs="?",
        metavar="UID_ID_OR_URL",
        help="Movie UID/URL  OR  Series numeric ID/URL.",
    )
    input_group.add_argument(
        "--batch", metavar="FILE", type=Path,
        help="Text file with one UID/ID/URL per line (# = comment lines).",
    )

    # ── Output ─────────────────────────────────────────────────────────
    parser.add_argument(
        "--output", "-o", metavar="DIR", type=Path,
        default=Path(cfg.download.output_dir),
        help=f"Root output directory (default: {cfg.download.output_dir!r}).",
    )

    # ── Auth ───────────────────────────────────────────────────────────
    parser.add_argument(
        "--token", metavar="JWT", default=None,
        help="Filimo JWT token (saved for future use).",
    )

    # ── Quality ────────────────────────────────────────────────────────
    parser.add_argument(
        "--max-quality", metavar="HEIGHT", type=int,
        default=cfg.download.max_quality_height,
        help=f"Max video height in pixels (default: {cfg.download.max_quality_height}, never 4K).",
    )

    # ── Series options ─────────────────────────────────────────────────
    parser.add_argument(
        "--no-season-images", action="store_true",
        help="Skip downloading season-level poster images.",
    )

    # ── IDM ────────────────────────────────────────────────────────────
    idm_group = parser.add_argument_group("IDM (Internet Download Manager)")
    idm_group.add_argument(
        "--idm", action="store_true",
        default=cfg.idm.enabled,
        help=(
            "Instead of downloading, generate a .reg file to add URLs to IDM. "
            f"(config default: {cfg.idm.enabled})"
        ),
    )
    idm_group.add_argument(
        "--idm-queue", metavar="NAME",
        default=cfg.idm.queue_name,
        help=f"IDM queue name (default: {cfg.idm.queue_name!r}).",
    )
    idm_group.add_argument(
        "--idm-out", metavar="FILE", type=Path, default=None,
        help="Output path for the .reg file (default: idm_downloads_<timestamp>.reg).",
    )

    # ── Behaviour ──────────────────────────────────────────────────────
    parser.add_argument(
        "--metadata-only", action="store_true",
        help="Skip video download; only fetch images and generate NFO files.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview actions without writing any files.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable DEBUG-level logging.",
    )

    return parser.parse_args()


# ---------------------------------------------------------------------------
# IDM .reg file output
# ---------------------------------------------------------------------------

def _collect_and_write_idm(
        results: list[dict],
        idm_out: Path | None,
        idm_exe_path: str,
) -> None:
    all_entries: list[IdmEntry] = []
    for r in results:
        entries = r.get("idm_entries", [])
        if entries:
            all_entries.extend(entries)

    if not all_entries:
        logger.warning("No IDM entries to export (all items may require payment or had errors).")
        return

    if idm_out is None:
        ts = int(time.time())
        idm_out = Path(f"idm_downloads_{ts}.reg")

    ok = generate_idm_reg(all_entries, idm_out, idm_exe_path=idm_exe_path)
    if ok:
        logger.info(
            "IDM .reg file written: %s  (%d URL(s))\n"
            "  → Double-click to import into IDM, or run: regedit /s %s",
            idm_out, len(all_entries), idm_out,
        )
    else:
        logger.error("Failed to write IDM .reg file.")


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def _print_summary(results: list[dict], metadata_only: bool, using_idm: bool) -> None:
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)

    total_items = len(results)
    total_episodes = sum(r.get("total_episodes", 0) for r in results)
    dl_episodes = sum(r.get("downloaded_episodes", 0) for r in results)
    ok_video = sum(1 for r in results if r.get("video"))
    ok_poster = sum(1 for r in results if r.get("poster"))
    ok_nfo = sum(
        1 for r in results
        if r.get("nfo") or r.get("downloaded_episodes", 0) > 0
    )
    all_errors: list[str] = []
    for r in results:
        if r.get("error"):
            all_errors.append(f"{r.get('uid') or r.get('series_id', '?')}: {r['error']}")
        for e in r.get("errors", []):
            all_errors.append(e)

    logger.info("Items processed : %d", total_items)

    if total_episodes:
        logger.info("Episodes found  : %d", total_episodes)
        if not metadata_only:
            verb = "Queued (IDM)" if using_idm else "Downloaded"
            logger.info("%-16s: %d / %d", verb, dl_episodes, total_episodes)
    elif not metadata_only:
        verb = "Queued (IDM)" if using_idm else "Downloaded"
        logger.info("%-16s: %d / %d", verb, ok_video, total_items)

    logger.info("Poster OK       : %d / %d", ok_poster, total_items)
    logger.info("NFO OK          : %d / %d", ok_nfo, total_items)

    if all_errors:
        logger.warning("Errors          : %d", len(all_errors))
        for e in all_errors:
            logger.warning("  ✗ %s", e)

    logger.info("Log saved to: %s", LOG_FILE)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = _parse_args()
    _setup_logging(args.verbose)
    cfg = get_config()

    if args.dry_run:
        logger.info("*** DRY RUN — no files will be written ***")

    output_dir: Path = args.output.resolve()
    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Output directory: %s", output_dir)

    # ── Token ──────────────────────────────────────────────────────────
    try:
        token = get_token(args.token)
    except RuntimeError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    # ── IDM queue (None = direct download) ─────────────────────────────
    idm_queue: str | None = args.idm_queue if args.idm else None

    # ── Item list ──────────────────────────────────────────────────────
    if args.batch:
        if not args.batch.is_file():
            logger.error("Batch file not found: %s", args.batch)
            sys.exit(1)
        items = load_batch_file(args.batch)
        if not items:
            logger.warning("Batch file is empty.")
            sys.exit(0)
        logger.info("Batch mode: %d item(s) from %s", len(items), args.batch)
    else:
        items = [args.target]

    # ── Process ────────────────────────────────────────────────────────
    results = download_batch(
        items,
        output_dir,
        token,
        metadata_only=args.metadata_only,
        dry_run=args.dry_run,
        max_height=args.max_quality,
        episodes_per_page=cfg.series.episodes_per_page,
        download_season_images=not args.no_season_images and cfg.series.download_season_images,
        progress_interval=cfg.download.progress_interval_sec,
        idm_queue=idm_queue,
    )

    # ── IDM .reg export ────────────────────────────────────────────────
    if args.idm and not args.metadata_only:
        _collect_and_write_idm(results, args.idm_out, cfg.idm.idm_exe_path)

    # ── Summary ────────────────────────────────────────────────────────
    _print_summary(results, args.metadata_only, using_idm=bool(idm_queue))

    all_errors = [
        r for r in results
        if r.get("error") or r.get("errors")
    ]
    sys.exit(1 if all_errors and len(all_errors) == len(results) else 0)


if __name__ == "__main__":
    main()
