"""
Unit tests for src/scrapers/filimo.py — pure logic, no HTTP calls.

Covers the real Filimo API response characteristics:
  - pro_year in Persian-Indic digits (۲۰۱۷)
  - URLs with JSON-escaped forward-slashes (backslash-slash)
  - Persian Unicode text in title_fa, descr, director, countries
"""

import json
import pytest
from src.scrapers.filimo import _title_similarity, normalize_year, _parse_movie, _clean_url


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_real_api_item() -> dict:
    """Return a dict that mirrors the actual Filimo API `included[0]` payload."""
    # Simulate what json.loads produces from the real API response:
    # "\/" becomes "/" automatically, Unicode escapes are real chars.
    return {
        "type": "movies",
        "id": 8789,
        "attributes": {
            "movie_id": "8789",
            "movie_title_en": "Olaf's Frozen Adventure",
            "movie_title": "ماجراجویی یخ زده اولاف",
            "pro_year": "۲۰۱۷",   # Persian-Indic digits
            # After json.loads the "\/" is already "/" — simulate that:
            "cover": "https://static.cdn.asset.filimo.com/flmt/mov_cvr_8789_4547.jpg?width=2560&quality=90",
            "pic": {
                "movie_img_s": "https://static.cdn.asset.filimo.com/flmt/mov_8789_1-b.jpg?width=165",
                "movie_img_m": "https://static.cdn.asset.filimo.com/flmt/mov_8789_1-b.jpg?width=300",
                "movie_img_b": "https://static.cdn.asset.filimo.com/flmt/mov_8789_1-b.jpg?width=800",
            },
            "imdb_rate": "5.80",
            "descr": "داستان از آن قرار است که فصل تعطیلات در قلمرو پادشاهی آرندل بزودی آغاز می شود.",
            "duration": {"value": 1335, "text": "۲۲ دقیقه"},
            "categories": [
                {"title_en": "animation", "title": "انیمیشن"},
                {"title_en": "adventure", "title": "ماجراجویی"},
            ],
            "countries": [{"country": "آمریکا", "country_en": "america"}],
            "director": "استیوی ورمرز - کوین دترز",
            "age_range": "6-12",
        },
    }


# ── normalize_year ────────────────────────────────────────────────────────────

class TestNormalizeYear:
    def test_ascii_passthrough(self):
        assert normalize_year("2022") == "2022"

    def test_persian_digits(self):
        assert normalize_year("۲۰۱۷") == "2017"

    def test_persian_2022(self):
        assert normalize_year("۲۰۲۲") == "2022"

    def test_mixed_digits(self):
        assert normalize_year("۲0۲2") == "2022"

    def test_strips_whitespace(self):
        assert normalize_year("  ۲۰۲۲  ") == "2022"

    def test_all_persian_digits(self):
        # ۰۱۲۳۴۵۶۷۸۹ → 0123456789
        assert normalize_year("۰۱۲۳۴۵۶۷۸۹") == "0123456789"


# ── _clean_url ────────────────────────────────────────────────────────────────

class TestCleanUrl:
    def test_normal_url_unchanged(self):
        url = "https://example.com/path/to/image.jpg"
        assert _clean_url(url) == url

    def test_escaped_slashes_unescaped(self):
        # Edge case: if the string somehow still has escaped slashes
        url = "https:\\/\\/example.com\\/image.jpg"
        result = _clean_url(url)
        assert "\\/" not in result
        assert "https://example.com/image.jpg" == result

    def test_strips_whitespace(self):
        assert _clean_url("  https://example.com/  ") == "https://example.com/"


# ── _parse_movie ──────────────────────────────────────────────────────────────

class TestParseMovie:
    def test_real_api_item(self):
        item = _make_real_api_item()
        movie = _parse_movie(item)
        assert movie is not None

        # English title preserved exactly
        assert movie.title_en == "Olaf's Frozen Adventure"

        # Persian title preserved as Unicode (not garbled)
        assert movie.title_fa == "ماجراجویی یخ زده اولاف"

        # Year converted from Persian digits to ASCII
        assert movie.year == "2017"
        assert movie.year.isdigit()

        # Poster URL is a clean HTTPS URL
        assert movie.poster_url.startswith("https://")
        assert "\\/" not in movie.poster_url
        assert "width=800" in movie.poster_url

        # Backdrop URL is a clean HTTPS URL
        assert movie.backdrop_url.startswith("https://")
        assert "\\/" not in movie.backdrop_url

        # Persian description preserved
        assert "آرندل" in movie.description

        # Duration
        assert movie.duration_seconds == 1335

        # Categories (English keys)
        genre_names = [c["title_en"] for c in movie.categories]
        assert "animation" in genre_names

        # Persian director preserved
        assert "ورمرز" in movie.director

    def test_year_is_comparable_integer(self):
        item = _make_real_api_item()
        movie = _parse_movie(item)
        assert movie is not None
        # Must be able to do arithmetic comparison after normalisation
        assert abs(int(movie.year) - 2017) == 0

    def test_missing_fields_dont_crash(self):
        item = {"type": "movies", "id": 1, "attributes": {}}
        # Should not raise; result may be a valid (empty) movie or None
        try:
            movie = _parse_movie(item)
            # If it returns something, basic fields should be strings
            if movie is not None:
                assert isinstance(movie.title_en, str)
        except Exception as exc:
            pytest.fail(f"_parse_movie raised unexpectedly: {exc}")

    def test_url_with_query_params_preserved(self):
        """Query-string secrets/tokens in URLs must survive parsing."""
        item = _make_real_api_item()
        item["attributes"]["pic"]["movie_img_b"] = (
            "https://static.cdn.asset.filimo.com/flmt/mov_8789_1-b.jpg"
            "?width=800&quality=85&sharpen=80&secret=7Ue0NF1q1KyntTFiMW4xfg"
        )
        movie = _parse_movie(item)
        assert movie is not None
        assert "secret=7Ue0NF1q1KyntTFiMW4xfg" in movie.poster_url


# ── _title_similarity ─────────────────────────────────────────────────────────

class TestTitleSimilarity:
    def test_identical(self):
        assert _title_similarity("Inception", "Inception") == 1.0

    def test_partial_overlap(self):
        score = _title_similarity("The Dark Knight", "The Dark Knight Rises")
        assert score > 0.5

    def test_empty_a(self):
        assert _title_similarity("", "anything") == 0.0

    def test_empty_b(self):
        assert _title_similarity("something", "") == 0.0

    def test_no_overlap(self):
        assert _title_similarity("Hello", "World") == 0.0

    def test_case_insensitive(self):
        assert _title_similarity("inception", "INCEPTION") == 1.0

    def test_olaf_match(self):
        score = _title_similarity(
            "Olaf's Frozen Adventure",
            "Olaf's Frozen Adventure",
        )
        assert score == 1.0
