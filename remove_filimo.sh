#!/bin/bash

# Check if directory argument is provided
if [ $# -eq 0 ]; then
    echo "Usage: $0 <directory>"
    echo "Example: $0 /path/to/nfo/files"
    exit 1
fi

TARGET_DIR="$1"

# Check if directory exists
if [ ! -d "$TARGET_DIR" ]; then
    echo "Error: Directory '$TARGET_DIR' does not exist"
    exit 1
fi

# Count total files for progress reporting
TOTAL_FILES=$(find "$TARGET_DIR" -maxdepth 1 -type f -name "*.nfo" | wc -l)
PROCESSED=0
MODIFIED=0

echo "Processing .nfo files in: $TARGET_DIR"
echo "Found $TOTAL_FILES .nfo files"
echo "----------------------------------------"

# Process each .nfo file
while IFS= read -r -d '' file; do
    PROCESSED=$((PROCESSED + 1))
    
    # Check if file contains the pattern
    if grep -q '<uniqueid type="filimo" default="true">.*</uniqueid>' "$file"; then
        # Remove lines containing the pattern and create backup
        cp "$file" "${file}.bak"
        sed -i '/<uniqueid type="filimo" default="true">.*<\/uniqueid>/d' "$file"
        MODIFIED=$((MODIFIED + 1))
        echo "✓ Modified: $(basename "$file")"
    else
        echo "  Skipped: $(basename "$file") (pattern not found)"
    fi
done < <(find "$TARGET_DIR" -maxdepth 1 -type f -name "*.nfo" -print0)

echo "----------------------------------------"
echo "Completed! Processed: $PROCESSED, Modified: $MODIFIED"
echo "Backup files created with .bak extension"

# Optional: Ask user if they want to remove backup files
read -p "Do you want to remove all .bak files? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    find "$TARGET_DIR" -maxdepth 1 -type f -name "*.nfo.bak" -delete
    echo "Backup files removed"
else
    echo "Backup files kept with .bak extension"
fi