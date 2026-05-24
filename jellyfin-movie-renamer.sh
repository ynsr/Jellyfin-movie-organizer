#!/usr/bin/env bash

set -euo pipefail

############################################
# Defaults
############################################
DRY_RUN=true
TARGET_DIR="."

has_tmdb_id() {
  [[ "$1" =~ \[tmdbid-[0-9]+\] ]]
}

############################################
# Parse arguments
############################################
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)
      DRY_RUN=false
      ;;
    --only-unresolved)
      ONLY_UNRESOLVED=true
      ;;
    --all)
      ONLY_UNRESOLVED=false
      ;;
    *)
      TARGET_DIR="$1"
      ;;
  esac
  shift
done

############################################
# Helpers
############################################

declare -A SEEN_MOVIES

TRASH_WORDS_REGEX="(1080p|720p|2160p|4K|HDR|BluRay|WEB-DL|WEBRip|x265|x264|10bit|8bit|6CH|SoftSub|HardSub|Dubbed|Subbed|Farsi|English|UPTV\.co|DigiMoviez|Pahe|PSA|Soren|AioFilm\.com|HQ|Disfilm|Unknown|DonyayeSerial)"

convert_part_words() {
  sed -E '
    s/[Pp]art[[:space:]]+[Oo]ne/Part 1/g;
    s/[Pp]art[[:space:]]+[Tt]wo/Part 2/g;
    s/[Pp]art[[:space:]]+[Tt]hree/Part 3/g;
    s/[Pp]art[[:space:]]+[Ff]our/Part 4/g;
    s/[Pp]art[[:space:]]+[Ff]ive/Part 5/g;
    s/[Pp]art[[:space:]]+[Ss]ix/Part 6/g;
    s/[Pp]art[[:space:]]+[Ss]even/Part 7/g;
    s/[Pp]art[[:space:]]+[Ee]ight/Part 8/g;
    s/[Pp]art[[:space:]]+[Nn]ine/Part 9/g;
    s/[Pp]art[[:space:]]+[Tt]en/Part 10/g;
  '
}

title_case() {
  awk '{
    for(i=1;i<=NF;i++){
      $i=toupper(substr($i,1,1)) tolower(substr($i,2))
    }
  }1'
}

rename_file() {

  local filepath="$1"
  local filename extension name cleaned year title newname key

  filename="$(basename "$filepath")"
  
  # Skip files that already have tmdbid
  if has_tmdb_id "$filename"; then
    echo "⏭️  Has tmdbid → skipping: $filename"
    return
  fi
  
  extension="${filename##*.}"
  name="${filename%.*}"

  # Replace separators
  cleaned="$(echo "$name" | sed -E 's/[._]+/ /g')"

  # Normalize Part words
  cleaned="$(echo "$cleaned" | convert_part_words)"

  # Extract year
  year="$(echo "$cleaned" | grep -oE '(19|20)[0-9]{2}' | head -n1 || true)"

  if [[ -z "$year" ]]; then
    echo "⚠️  No year → skipping: $filename"
    return
  fi

  # Remove the year and everything after it from the title
  cleaned="$(echo "$cleaned" | sed -E "s/(.*)$year.*/\1/")"

  # Remove trash tags
  cleaned="$(echo "$cleaned" | sed -E "s/$TRASH_WORDS_REGEX//Ig")"

  # Normalize whitespace
  cleaned="$(echo "$cleaned" | sed -E 's/[[:space:]]+/ /g' | sed -E 's/^ | $//g')"

  # Title case
  title="$(echo "$cleaned" | title_case)"

  newname="${title} (${year}).${extension}"
  newpath="$(dirname "$filepath")/$newname"

  # Duplicate detection key
  key="$(echo "${title}_${year}" | tr '[:upper:]' '[:lower:]')"

  if [[ -n "${SEEN_MOVIES[$key]:-}" ]]; then
    echo "🚫 Duplicate detected:"
    echo "   Existing: ${SEEN_MOVIES[$key]}"
    echo "   Skipping: $filepath"
    return
  fi

  SEEN_MOVIES["$key"]="$filepath"

  if [[ "$filename" == "$newname" ]]; then
    echo "✅ Already correct → $filename"
    return
  fi

  if [[ -e "$newpath" ]]; then
    echo "🚫 Target exists → $newpath"
    return
  fi

  if $DRY_RUN; then
    echo "[DRY] $filename → $newname"
  else
    mv -v -- "$filepath" "$newpath"
  fi
}

############################################
# Main recursive scan
############################################

while IFS= read -r -d '' file; do
  rename_file "$file"
done < <(find "$TARGET_DIR" -type f \( \
  -iname "*.mkv" -o \
  -iname "*.mp4" -o \
  -iname "*.avi" -o \
  -iname "*.mov" \) -print0)