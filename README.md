# Jellyfin Movie Organizer

A Python tool to rename movie files, download posters/backdrops, and generate `.nfo` metadata files in Jellyfin-compatible format.

## Features

- **Rename** movie files to Jellyfin format: `{Movie Name} ({Year}) [imdbid-{ttXXXXX}].{ext}`
- **Download posters** from Filimo or Doostihaa
- **Download backdrop images** from Filimo
- **Generate `.nfo` metadata files** for Jellyfin

## Project Structure

```
jellyfin-movie-organizer/
├── src/
│   ├── __init__.py
│   ├── main.py               # Entry point
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
│   └── utils/
│       ├── __init__.py
│       ├── file_utils.py     # File helpers
│       ├── http_client.py    # Shared HTTP session + retry
│       └── name_parser.py    # Jellyfin name format parser
├── config/
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

## Usage

```bash
# Process a single directory
python -m src.main /path/to/movies

# Dry-run (preview changes without applying)
python -m src.main /path/to/movies --dry-run

# Skip specific tasks
python -m src.main /path/to/movies --skip-rename --skip-backdrop
```

## Output Files

- `movies-missed-poster.txt` — Movies where poster download failed
- `movies-missed-backdrop.txt` — Movies where backdrop download failed  
- `movies-missed-nfo.txt` — Movies where NFO metadata was not found
- `logs/organizer.log` — Full run log
