"""
Tests for src.services.filimo_downloader
"""
import pytest
from src.services.filimo_downloader import (
    _extract_uid,
    _normalize_persian,
    _safe_filename,
    jellyfin_movie_folder,
    select_best_quality,
    FilimoMetadata,
    FilimoStreamOption,
)


# ---------------------------------------------------------------------------
# _extract_uid
# ---------------------------------------------------------------------------

class TestExtractUid:
    def test_bare_uid(self):
        assert _extract_uid("aVmdY") == "aVmdY"

    def test_short_url(self):
        assert _extract_uid("https://www.filimo.com/m/aVmdY") == "aVmdY"

    def test_full_url(self):
        long = (
            "https://www.filimo.com/m/aVmdY"
            "/%D8%AF%D9%88%D8%B1_%D8%AF%D9%86%DB%8C%D8%A7"
        )
        assert _extract_uid(long) == "aVmdY"

    def test_movie_path(self):
        assert _extract_uid("https://www.filimo.com/movie/aVmdY/watch") == "aVmdY"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError):
            _extract_uid("https://www.filimo.com/unknown/path")

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError):
            _extract_uid("not a uid or url!!")


# ---------------------------------------------------------------------------
# _normalize_persian
# ---------------------------------------------------------------------------

class TestNormalizePersian:
    def test_pure_persian(self):
        assert _normalize_persian("۱۹۹۶") == "1996"

    def test_ascii_unchanged(self):
        assert _normalize_persian("2024") == "2024"

    def test_mixed(self):
        assert _normalize_persian("۴۸۰p") == "480p"


# ---------------------------------------------------------------------------
# _safe_filename
# ---------------------------------------------------------------------------

class TestSafeFilename:
    def test_strips_illegal_chars(self):
        assert "<>:/\\|?*" not in _safe_filename('Movie: "Title" <2024>')

    def test_clean_name_unchanged(self):
        assert _safe_filename("Around the World") == "Around the World"


# ---------------------------------------------------------------------------
# select_best_quality
# ---------------------------------------------------------------------------

def _make_stream(height: int) -> FilimoStreamOption:
    return FilimoStreamOption(
        quality_label=f"{height}p",
        height=height,
        bandwidth=height * 1000,
        url=f"https://example.com/{height}.mp4",
        size_label=f"{height // 10}MB",
    )


class TestSelectBestQuality:
    def test_selects_1080_over_720(self):
        opts = [_make_stream(720), _make_stream(1080), _make_stream(360)]
        best = select_best_quality(opts)
        assert best.height == 1080

    def test_never_selects_4k(self):
        opts = [_make_stream(2160), _make_stream(1080), _make_stream(720)]
        best = select_best_quality(opts)
        assert best.height == 1080

    def test_only_4k_available_returns_it(self):
        # If only 4K is available, still return it (best effort)
        opts = [_make_stream(2160)]
        best = select_best_quality(opts)
        assert best is not None

    def test_empty_returns_none(self):
        assert select_best_quality([]) is None

    def test_exact_1080_included(self):
        opts = [_make_stream(1080)]
        assert select_best_quality(opts).height == 1080


# ---------------------------------------------------------------------------
# jellyfin_movie_folder
# ---------------------------------------------------------------------------

class TestJellyfinMovieFolder:
    def _meta(self, title_en="", title_fa="", year="1996"):
        return FilimoMetadata(
            uid="aVmdY",
            title_en=title_en,
            title_fa=title_fa,
            year=year,
            imdb_rate="6.5",
            description_fa="",
            description_en="",
            duration_seconds=3600,
            poster_url="",
            backdrop_url="",
        )

    def test_english_title(self):
        meta = self._meta(title_en="Around the World with Timon & Pumbaa", year="1996")
        assert jellyfin_movie_folder(meta) == "Around the World with Timon & Pumbaa (1996)"

    def test_falls_back_to_persian(self):
        meta = self._meta(title_fa="تست", year="2020")
        assert "2020" in jellyfin_movie_folder(meta)
