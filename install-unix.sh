#!/usr/bin/env sh
# install-unix.sh — jellyfin-movie-organizer installer for Unix-like systems
#                   (Linux, macOS, WSL)
# Author: Younes Rahimi
#
# Usage:
#   ./install-unix.sh                           # install interactively
#   ./install-unix.sh --uninstall               # remove installed files
#   ./install-unix.sh --force                   # reinstall even if present
#   ./install-unix.sh --install-dir=/opt/bin    # custom install directory
#   ./install-unix.sh --socks-proxy=socks5://localhost:10808
#
# What this script does:
#   1. Verifies Python 3.10+ and pip are available.
#   2. Installs pip dependencies from requirements.txt (user-level, no venv).
#   3. Creates an executable wrapper at INSTALL_DIR/jmo (jellyfin-movie-organizer).
#   4. Optionally appends a PATH export to your shell profile.

set -e

# ── Helpers ───────────────────────────────────────────────────────────────────

INSTALLER_TAG="# added by jellyfin-movie-organizer installer"

info()  { printf '\033[1;32m[jmo]\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m[jmo]\033[0m %s\n' "$*" >&2; }
die()   { printf '\033[1;31m[jmo]\033[0m error: %s\n' "$*" >&2; exit 1; }

# ── Defaults ──────────────────────────────────────────────────────────────────

INSTALL_DIR="${HOME}/.local/bin"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FORCE=0
UNINSTALL=0
SOCKS_PROXY=""

# ── Argument parsing ──────────────────────────────────────────────────────────

for arg in "$@"; do
    case "$arg" in
        --force)          FORCE=1 ;;
        --uninstall)      UNINSTALL=1 ;;
        --install-dir=*)  INSTALL_DIR="${arg#*=}" ;;
        --socks-proxy=*)  SOCKS_PROXY="${arg#*=}" ;;
        -h|--help)
            sed -n '2,/^set -e/p' "$0" | grep '^#' | sed 's/^# \?//'
            exit 0
            ;;
        *)
            die "Unknown argument: $arg (use --help)"
            ;;
    esac
done

WRAPPER="${INSTALL_DIR}/jmo"

# ── Uninstall ─────────────────────────────────────────────────────────────────

if [ "$UNINSTALL" -eq 1 ]; then
    info "Uninstalling jellyfin-movie-organizer …"

    if [ -f "$WRAPPER" ]; then
        rm -f "$WRAPPER"
        info "Removed ${WRAPPER}"
    else
        warn "No wrapper found at ${WRAPPER}"
    fi

    for profile in "${HOME}/.profile" "${HOME}/.bashrc" "${HOME}/.zshrc"; do
        if [ -f "$profile" ] && grep -qF "$INSTALLER_TAG" "$profile"; then
            tmp="$(mktemp)"
            grep -v "$INSTALLER_TAG" "$profile" \
                | grep -v "export PATH.*${INSTALL_DIR}" > "$tmp" || true
            mv "$tmp" "$profile"
            info "Cleaned PATH entry from ${profile}"
        fi
    done

    info "Uninstall complete."
    exit 0
fi

# ── Verify Python version ─────────────────────────────────────────────────────

info "Checking Python …"
if ! command -v python3 >/dev/null 2>&1; then
    die "python3 not found. Install Python 3.10+ and try again."
fi

PYTHON_VER_TUPLE=$(python3 -c 'import sys; print(sys.version_info[:2])')
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info[1])')
PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info[0])')

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
    die "Python 3.10+ is required (found ${PYTHON_VER_TUPLE}). Please upgrade."
fi
info "Python OK: ${PYTHON_VER_TUPLE}"

# ── Verify pip ────────────────────────────────────────────────────────────────

if ! python3 -m pip --version >/dev/null 2>&1; then
    die "pip not found. Run: python3 -m ensurepip --upgrade"
fi

# ── Verify source layout ──────────────────────────────────────────────────────

REQUIREMENTS="${SCRIPT_DIR}/requirements.txt"
if [ ! -f "$REQUIREMENTS" ]; then
    die "requirements.txt not found at ${REQUIREMENTS}. Run this script from the project root."
fi
if [ ! -f "${SCRIPT_DIR}/src/main.py" ]; then
    die "src/main.py not found. Run this script from the project root."
fi

# ── Install Python dependencies ───────────────────────────────────────────────

info "Installing Python dependencies …"
if python3 -c "import requests, bs4, lxml" 2>/dev/null; then
    info "Dependencies already available."
else
    python3 -m pip install --quiet --user -r "$REQUIREMENTS" 2>/dev/null \
        || python3 -m pip install --quiet --user --break-system-packages -r "$REQUIREMENTS" \
        || die "Could not install dependencies. Run manually: pip install -r requirements.txt"
fi

# ── Create bin directory ──────────────────────────────────────────────────────

if [ ! -d "$INSTALL_DIR" ]; then
    mkdir -p "$INSTALL_DIR"
    info "Created ${INSTALL_DIR}"
fi

# ── Write wrapper script ──────────────────────────────────────────────────────

if [ -f "$WRAPPER" ] && [ "$FORCE" -eq 0 ]; then
    info "Wrapper already exists at ${WRAPPER} (use --force to reinstall)."
else
    # Escape the source dir for embedding in the wrapper
    ESCAPED_DIR=$(printf '%s' "$SCRIPT_DIR" | sed "s/'/'\\\\''/g")
    cat > "$WRAPPER" << WRAPPER_EOF
#!/usr/bin/env python3
"""jellyfin-movie-organizer (jmo) — installed by install-unix.sh"""
import sys, os
_src = '${ESCAPED_DIR}'
if _src not in sys.path:
    sys.path.insert(0, _src)
os.chdir(_src)
from src.main import main
main()
WRAPPER_EOF
    chmod +x "$WRAPPER"
    info "Installed wrapper → ${WRAPPER}"
fi

# ── Update PATH in shell profile ──────────────────────────────────────────────

if [ -n "$BASH_VERSION" ]; then
    PROFILE="${HOME}/.bashrc"
elif [ -n "$ZSH_VERSION" ]; then
    PROFILE="${HOME}/.zshrc"
else
    PROFILE="${HOME}/.profile"
fi

case ":${PATH}:" in
    *":${INSTALL_DIR}:"*)
        info "${INSTALL_DIR} is already on PATH."
        ;;
    *)
        if [ -f "$PROFILE" ] && grep -qF "$INSTALLER_TAG" "$PROFILE"; then
            info "PATH entry already present in ${PROFILE}."
        else
            printf '\nexport PATH="%s:$PATH" %s\n' "$INSTALL_DIR" "$INSTALLER_TAG" >> "$PROFILE"
            info "Added ${INSTALL_DIR} to PATH in ${PROFILE}"
            info "Apply now: source ${PROFILE}"
        fi
        ;;
esac

# ── Proxy reminder ────────────────────────────────────────────────────────────

if [ -n "$SOCKS_PROXY" ]; then
    info "SOCKS proxy note: set the following in your shell to route traffic:"
    info "  export ALL_PROXY=${SOCKS_PROXY}"
    info "  export HTTPS_PROXY=${SOCKS_PROXY}"
fi

# ── Done ──────────────────────────────────────────────────────────────────────

info ""
info "Installation complete!"
info ""
info "Next steps:"
info "  1. Restart your shell or run: source ${PROFILE}"
info "  2. Organise a movie directory:  jmo /path/to/movies"
info "  3. Preview only (dry run):      jmo /path/to/movies --dry-run"
info "  4. Skip specific tasks:         jmo /path/to/movies --skip-rename --skip-backdrop"
info "  5. Verbose logs:                jmo /path/to/movies -v"
info ""
info "To uninstall: ./install-unix.sh --uninstall"
