"""
Application configuration manager.
====================================
Reads/writes a TOML config file at ~/.jellyfin-organizer/config.toml.
Generates a fully-commented sample file with defaults if missing or empty.

Usage
-----
    from config.app_config import get_config, AppConfig

    cfg = get_config()
    print(cfg.download.max_quality_height)   # 1080
    print(cfg.idm.queue_name)                # "Default"
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

CONFIG_DIR  = Path.home() / ".jellyfin-organizer"
CONFIG_FILE = CONFIG_DIR / "config.toml"

# ---------------------------------------------------------------------------
# Tiny TOML parser/writer (stdlib tomllib is read-only; avoid extra deps)
# ---------------------------------------------------------------------------

def _parse_toml_simple(text: str) -> dict[str, Any]:
    """
    Parse a simple TOML file (flat sections, scalar values only).
    Supports strings, integers, floats, booleans.  No arrays / inline tables.
    """
    result: dict[str, Any] = {}
    section: dict[str, Any] = result

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Section header
        m = re.match(r'^\[([A-Za-z0-9_.]+)\]$', line)
        if m:
            key = m.group(1)
            section = result.setdefault(key, {})
            continue
        # Key = value
        m = re.match(r'^([A-Za-z0-9_]+)\s*=\s*(.+)$', line)
        if m:
            k, v = m.group(1), m.group(2).strip()
            # String
            if (v.startswith('"') and v.endswith('"')) or \
               (v.startswith("'") and v.endswith("'")):
                section[k] = v[1:-1]
            elif v.lower() == "true":
                section[k] = True
            elif v.lower() == "false":
                section[k] = False
            else:
                try:
                    section[k] = int(v)
                except ValueError:
                    try:
                        section[k] = float(v)
                    except ValueError:
                        section[k] = v
    return result


def _write_toml_simple(data: dict[str, Any]) -> str:
    """Serialize a flat-section dict back to TOML."""
    lines = []
    for section, values in data.items():
        lines.append(f"[{section}]")
        for k, v in values.items():
            if isinstance(v, bool):
                lines.append(f"{k} = {str(v).lower()}")
            elif isinstance(v, str):
                lines.append(f'{k} = "{v}"')
            else:
                lines.append(f"{k} = {v}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Default config template (written to disk on first run)
# ---------------------------------------------------------------------------

SAMPLE_CONFIG = """\
# ============================================================
# Jellyfin Movie Organizer — Configuration File
# Location: ~/.jellyfin-organizer/config.toml
# ============================================================

# ── Authentication ────────────────────────────────────────────
[auth]
# Filimo JWT token.  You can also supply it via --token on the CLI.
# Obtain it from DevTools → Network → any Filimo API request header:
#   authorization: Bearer <paste-here>
filimo_token = ""

# ── Download settings ─────────────────────────────────────────
[download]
# Maximum video height to download (e.g. 1080 = Full HD, 720 = HD).
# 4K (2160) is always excluded regardless of this setting.
max_quality_height = 1080

# Download chunk size in megabytes (affects memory and progress frequency).
chunk_size_mb = 4

# Number of seconds between progress log lines during a download.
progress_interval_sec = 5

# Root directory where downloaded content is placed.
# Each movie/show gets its own Jellyfin-named sub-folder.
output_dir = "downloads"

# ── Series / episode options ──────────────────────────────────
[series]
# How many episodes to fetch per API page.
episodes_per_page = 40

# If true, also download Season-level poster/backdrop for each season folder.
download_season_images = true

# ── IDM (Internet Download Manager) ──────────────────────────
[idm]
# Set to true to generate a .reg file that adds downloads to IDM.
enabled = false

# IDM queue name.  Use "Default" for the default queue,
# or enter any queue you have created in IDM.
queue_name = "Default"

# Full path to the IDM executable (used only for reference in comments).
# Leave empty to use the system default install path.
idm_exe_path = "C:\\\\Program Files (x86)\\\\Internet Download Manager\\\\IDMan.exe"

# ── HTTP client ───────────────────────────────────────────────
[http]
# Request timeout in seconds.
timeout_sec = 30

# Maximum number of retry attempts for failed API calls.
max_retries = 3

# Base back-off factor (seconds) between retries (exponential: factor * 2^attempt).
backoff_factor = 1.5

# ── Logging ───────────────────────────────────────────────────
[logging]
# Log directory (relative paths are relative to the working directory).
log_dir = "logs"

# Log file name inside log_dir.
log_file = "organizer.log"
"""


# ---------------------------------------------------------------------------
# Dataclasses for typed config sections
# ---------------------------------------------------------------------------

@dataclass
class AuthConfig:
    filimo_token: str = ""


@dataclass
class DownloadConfig:
    max_quality_height: int = 1080
    chunk_size_mb: int = 4
    progress_interval_sec: int = 5
    output_dir: str = "downloads"


@dataclass
class SeriesConfig:
    episodes_per_page: int = 40
    download_season_images: bool = True


@dataclass
class IdmConfig:
    enabled: bool = False
    queue_name: str = "Default"
    idm_exe_path: str = r"C:\Program Files (x86)\Internet Download Manager\IDMan.exe"


@dataclass
class HttpConfig:
    timeout_sec: int = 30
    max_retries: int = 3
    backoff_factor: float = 1.5


@dataclass
class LoggingConfig:
    log_dir: str = "logs"
    log_file: str = "organizer.log"


@dataclass
class AppConfig:
    auth:     AuthConfig     = field(default_factory=AuthConfig)
    download: DownloadConfig = field(default_factory=DownloadConfig)
    series:   SeriesConfig   = field(default_factory=SeriesConfig)
    idm:      IdmConfig      = field(default_factory=IdmConfig)
    http:     HttpConfig     = field(default_factory=HttpConfig)
    logging:  LoggingConfig  = field(default_factory=LoggingConfig)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _apply_section(dataclass_obj: Any, raw: dict[str, Any]) -> None:
    """Copy values from raw dict into a dataclass instance, type-coercing."""
    for f in fields(dataclass_obj):
        if f.name in raw:
            v = raw[f.name]
            try:
                # Coerce to the declared type if needed
                target_type = f.type if isinstance(f.type, type) else type(getattr(dataclass_obj, f.name))
                if target_type == bool and isinstance(v, int):
                    v = bool(v)
                elif not isinstance(v, target_type):
                    v = target_type(v)
            except (TypeError, ValueError):
                pass
            setattr(dataclass_obj, f.name, v)


def _ensure_config_file() -> None:
    """Create the config file with sample defaults if absent or empty."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists() or CONFIG_FILE.stat().st_size == 0:
        CONFIG_FILE.write_text(SAMPLE_CONFIG, encoding="utf-8")
        print(f"[jellyfin-organizer] Created default config: {CONFIG_FILE}")
        print("  Edit it to set your Filimo token, output directory, IDM options, etc.\n")


def load_config() -> AppConfig:
    """Load config from file, creating it with defaults if missing."""
    _ensure_config_file()
    cfg = AppConfig()
    try:
        raw = _parse_toml_simple(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not parse config file (%s): %s — using defaults.", CONFIG_FILE, exc)
        return cfg

    section_map = {
        "auth":     cfg.auth,
        "download": cfg.download,
        "series":   cfg.series,
        "idm":      cfg.idm,
        "http":     cfg.http,
        "logging":  cfg.logging,
    }
    for section_name, obj in section_map.items():
        if section_name in raw:
            _apply_section(obj, raw[section_name])

    return cfg


# Module-level singleton
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Return the cached AppConfig, loading it on first call."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> AppConfig:
    """Force reload from disk."""
    global _config
    _config = load_config()
    return _config
