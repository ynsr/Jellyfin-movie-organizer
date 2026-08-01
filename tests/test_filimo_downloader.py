"""
Tests for src.services.filimo_downloader
"""
import pytest
from src.services.filimo_downloader import (
    _extract_movie_uid,
    _extract_series_id,
    _normalize_persian,
    _safe_filename,
    is_series_input,
    jellyfin_movie_folder,
    jellyfin_series_folder,
    jellyfin_episode_base,
    jellyfin_season_folder,
    select_best_quality,
    FilimoMetadata,
    FilimoStreamOption,
)


# ---------------------------------------------------------------------------
# _extract_movie_uid
# ---------------------------------------------------------------------------

class TestExtractMovieUid:
    def test_bare_uid(self):
        assert _extract_movie_uid("aVmdY") == "aVmdY"

    def test_short_url(self):
        assert _extract_movie_uid("https://www.filimo.com/m/aVmdY") == "aVmdY"

    def test_full_url(self):
        long = (
            "https://www.filimo.com/m/aVmdY"
            "/%D8%AF%D9%88%D8%B1_%D8%AF%D9%86%DB%8C%D8%A7"
        )
        assert _extract_movie_uid(long) == "aVmdY"

    def test_movie_path(self):
        assert _extract_movie_uid("https://www.filimo.com/movie/aVmdY/watch") == "aVmdY"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError):
            _extract_movie_uid("https://www.filimo.com/unknown/path")

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError):
            _extract_movie_uid("not a uid or url!!")


# ---------------------------------------------------------------------------
# _extract_series_id
# ---------------------------------------------------------------------------

class TestExtractSeriesId:
    def test_bare_id(self):
        assert _extract_series_id("99963") == "99963"

    def test_short_url(self):
        assert _extract_series_id("https://www.filimo.com/n/99963") == "99963"

    def test_tagged_url(self):
        url = "https://www.filimo.com/tag/drama/n/99963"
        assert _extract_series_id(url) == "99963"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError):
            _extract_series_id("https://www.filimo.com/m/aVmdY")

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError):
            _extract_series_id("not a series id")


# ---------------------------------------------------------------------------
# is_series_input
# ---------------------------------------------------------------------------

class TestIsSeriesInput:
    def test_numeric_id_true(self):
        assert is_series_input("99963") is True

    def test_series_url_true(self):
        assert is_series_input("https://www.filimo.com/n/99963") is True

    def test_tagged_series_url_true(self):
        assert is_series_input("https://www.filimo.com/tag/drama/n/99963") is True

    def test_movie_url_false(self):
        assert is_series_input("https://www.filimo.com/m/aVmdY") is False

    def test_non_url_non_digit_false(self):
        assert is_series_input("aVmdY") is False


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

    def test_imdb_tag_added(self):
        meta = self._meta(title_en="Inception", year="2010")
        assert jellyfin_movie_folder(meta, imdb_id="tt1375666") == \
               "Inception (2010) [imdbid-tt1375666]"

    def test_falls_back_to_persian(self):
        meta = self._meta(title_fa="تست", year="2020")
        assert "2020" in jellyfin_movie_folder(meta)


# ---------------------------------------------------------------------------
# jellyfin_series_folder
# ---------------------------------------------------------------------------

class TestJellyfinSeriesFolder:
    def test_series_imdb_tag(self):
        meta = FilimoMetadata(
            uid="123",
            title_en="The Office",
            title_fa="",
            year="2005",
            imdb_rate="",
            description_fa="",
            description_en="",
            duration_seconds=0,
            poster_url="",
            backdrop_url="",
            content_type="Series",
        )
        assert jellyfin_series_folder(meta, imdb_id="tt0386676") == \
               "The Office (2005) [imdbid-tt0386676]"


# ---------------------------------------------------------------------------
# jellyfin_season_folder / jellyfin_episode_base
# ---------------------------------------------------------------------------

class TestJellyfinSeasonFolder:
    def test_single_digit_padded(self):
        assert jellyfin_season_folder(1) == "Season 01"

    def test_double_digit(self):
        assert jellyfin_season_folder(12) == "Season 12"


class TestJellyfinEpisodeBase:
    def test_with_title(self):
        assert jellyfin_episode_base("The Office", 1, 6, "The Alliance") == \
               "The Office - S01E06 - The Alliance"

    def test_without_title(self):
        assert jellyfin_episode_base("The Office", 2, 3) == "The Office - S02E03"

    def test_sanitizes_show_and_title(self):
        assert jellyfin_episode_base("Bad:Name", 1, 1, "A:B") == \
               "BadName - S01E01 - AB"
