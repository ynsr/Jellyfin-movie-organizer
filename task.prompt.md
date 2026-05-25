## Task Title: Enhance video file naming by integrating Filimo metadata API

## Task Description:

1. If the video file name contains `[fuid-{SOME_FILIMO_UID}]` which indicates an ID from www.filimo.com, use that uid to
   fetch metadata from Filimo metadata API directly.  If the video file name doesn't have IMDB ID, and searching IMDB ID via Bertina was not successful, use the fetched english name from Filimo API to search again in Bertina to find the IMDB ID. At last, drop the `[fuid-{SOME_FILIMO_UID}]` from the video file (
   and other video resources) name and rename the video (and its resources) file accordingly to be Jellyfin-compatible.

## Context:

- Related Files/Resources:
    - Whole codebase
