# Jellyfin Movie Organizer

A Python tool to organize local movie files and download Filimo movies/series with Jellyfin-compatible naming and metadata.

## Features

- **Rename** movie files to Jellyfin format: `{Movie Name} ({Year}) [imdbid-{ttXXXXX}].{ext}`
- **Download posters** from Filimo or Doostihaa
- **Download backdrop images** from Filimo
- **Generate `.nfo` metadata files** for Jellyfin
- **Download Filimo movies and TV series** with Jellyfin folder structure
- **IDM export**: generate `.reg` files for Internet Download Manager
- **Config file** auto-generated at `~/.jellyfin-organizer/config.toml`

## Project Structure

```
jellyfin-movie-organizer/
├── src/
│   ├── __init__.py
│   ├── main.py               # Entry point
│   ├── download.py           # Filimo downloader CLI
│   ├── processor.py          # Main orchestrator per movie
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── bertina.py        # Bertina search engine scraper
│   │   ├── filimo.py         # Filimo API client
│   │   └── doostihaa.py      # Doostihaa poster scraper
│   ├── services/
│   │   ├── __init__.py
│   │   ├── renamer.py        # Movie file renaming logic
│   │   ├── poster.py         # Poster download service
│   │   ├── backdrop.py       # Backdrop download service
│   │   └── nfo.py            # NFO file generator
│   │   ├── filimo_downloader.py  # Filimo movies/series downloader
│   │   └── idm_export.py      # IDM .reg export helper
│   └── utils/
│       ├── __init__.py
│       ├── file_utils.py     # File helpers
│       ├── http_client.py    # Shared HTTP session + retry
│       └── name_parser.py    # Jellyfin name format parser
├── config/
│   ├── app_config.py         # TOML config loader/writer
│   └── settings.py           # Config constants
├── tests/
│   └── ...
├── logs/                     # Runtime logs directory
├── requirements.txt
└── README.md
```

## Setup

```bash
pip install -r requirements.txt
```

Install helper scripts:

- Windows: `install-windows.ps1`
- Linux/macOS/WSL: `install-unix.sh`

## Usage

### Organizer (local files)

```bash
# Process a single directory
python -m src.main /path/to/movies

# Dry-run (preview changes without applying)
python -m src.main /path/to/movies --dry-run

# Skip specific tasks
python -m src.main /path/to/movies --skip-rename --skip-backdrop

# Verbose logs
python -m src.main /path/to/movies -v
```

If you installed the wrapper, use `jmo` instead of `python -m src.main`.
For the downloader, use `jmd` instead of `python -m src.download`.

### Filimo downloader

```bash
# Movie (UID or URL)
python -m src.download aVmdY --output ~/Movies
python -m src.download "https://www.filimo.com/m/aVmdY/..." --output ~/Movies

# Series (ID or URL)
python -m src.download 99963 --output ~/TV
python -m src.download "https://www.filimo.com/n/99963" --output ~/TV

# Batch mode (mix of movies and series)
python -m src.download --batch list.txt --output ~/Media

# IDM export (creates idm_downloads_<timestamp>.reg)
python -m src.download 99963 --output ~/TV --idm
```

If you installed the wrapper, use `jmd` instead of `python -m src.download`.

Common flags:

- `--metadata-only` (skip video; only images and NFO)
- `--dry-run` (preview only)
- `--token <JWT>` (supply/refresh Filimo token)
- `--max-quality <HEIGHT>` (cap video height; never 4K)

## Configuration

On first run, a config file is created at `~/.jellyfin-organizer/config.toml`.
Set your Filimo JWT token under `[auth]` or pass it via `--token`.

## Output Files

Organizer outputs:

- `movies-missed-poster.txt` — Movies where poster download failed
- `movies-missed-backdrop.txt` — Movies where backdrop download failed
- `movies-missed-nfo.txt` — Movies where NFO metadata was not found
- `logs/organizer.log` — Full run log

Filimo downloader outputs (per movie/series):

- Movie: `{Title} ({Year})/{Title} ({Year}).mp4`, `poster.jpg`, `fanart.jpg`, `{Title} ({Year}).nfo`
- Series: `{Show} ({Year})/tvshow.nfo`, `poster.jpg`, `fanart.jpg`, `Season 01/{Show} - S01E01 - {Episode}.mp4`, episode NFOs
- IDM export: `idm_downloads_<timestamp>.reg` when using `--idm`
