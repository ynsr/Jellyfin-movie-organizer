## Task Title: Extract video metadata from Doostiha as a fallback when Filimo API fails

## Task Description:

Update selecting correct `article` tag when searching the Doostiha webpage via Bertina by ignoring all `article` tags which are not pointing to Doostiha webpage.

Sample occurring error:
```
2026-05-25 08:43:02 [WARNING] src.scrapers.bertina — First Bertina result is not a Doostihaa page: ads.bertina.ir
```


## Context:

- Related Files/Resources:
    - [bertina.py](src/scrapers/bertina.py)
    - Other codebase
