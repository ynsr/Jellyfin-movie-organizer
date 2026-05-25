"""
Unit tests for src/utils/name_parser.py
"""

import pytest
from pathlib import Path

from src.utils.name_parser import (
    MovieInfo,
    build_jellyfin_name,
    build_jellyfin_name_with_id_type,
    is_jellyfin_format,
    sanitize_movie_name,
)


class TestBuildJellyfinName:
    def test_basic(self):
        result = build_jellyfin_name("Inception", "2010", "tt1375666", ".mkv")
        assert result == "Inception (2010) [imdbid-tt1375666].mkv"

    def test_extension_without_dot(self):
        result = build_jellyfin_name("The Batman", "2022", "tt1877830", "mp4")
        assert result == "The Batman (2022) [imdbid-tt1877830].mp4"

    def test_spaces_preserved(self):
        result = build_jellyfin_name("Chickenhare and the Hamster of Darkness", "2022", "tt12532368", ".mp4")
        assert "Chickenhare and the Hamster of Darkness" in result

    def test_tmdb_build(self):
        result = build_jellyfin_name_with_id_type(
            "The Batman", "2022", "414906", ".mp4", id_type="tmdb"
        )
        assert result == "The Batman (2022) [tmdbid-414906].mp4"


class TestIsJellyfinFormat:
    def test_valid_format(self):
        assert is_jellyfin_format(Path("Inception (2010) [imdbid-tt1375666].mkv"))

    def test_invalid_format(self):
        assert not is_jellyfin_format(Path("Inception.2010.BluRay.mkv"))

    def test_with_suffix(self):
        assert is_jellyfin_format(Path("Inception (2010) [imdbid-tt1375666]-poster.jpg"))


class TestMovieInfoFromFilename:
    def test_parse_movie_file(self):
        path = Path("Chickenhare and the Hamster of Darkness (2022) [imdbid-tt12532368].mp4")
        info = MovieInfo.from_jellyfin_filename(path)
        assert info is not None
        assert info.name == "Chickenhare and the Hamster of Darkness"
        assert info.year == "2022"
        assert info.imdb_id == "tt12532368"
        assert info.id_type == "imdb"
        assert info.extension == ".mp4"

    def test_parse_poster_file(self):
        path = Path("Inception (2010) [imdbid-tt1375666]-poster.jpg")
        info = MovieInfo.from_jellyfin_filename(path)
        assert info is not None
        assert info.suffix == "-poster"

    def test_non_jellyfin_returns_none(self):
        path = Path("random.movie.file.mkv")
        assert MovieInfo.from_jellyfin_filename(path) is None

    def test_base_name(self):
        path = Path("Inception (2010) [imdbid-tt1375666].mkv")
        info = MovieInfo.from_jellyfin_filename(path)
        assert info.base_name == "Inception (2010) [imdbid-tt1375666]"

    def test_file_name_with_override(self):
        path = Path("Inception (2010) [imdbid-tt1375666].mkv")
        info = MovieInfo.from_jellyfin_filename(path)
        assert info.file_name(suffix="-backdrop", extension=".jpg") == \
               "Inception (2010) [imdbid-tt1375666]-backdrop.jpg"


class TestSanitizeMovieName:
    def test_removes_illegal_chars(self):
        assert ":" not in sanitize_movie_name("Movie: The Sequel")
        assert "/" not in sanitize_movie_name("A/B")

    def test_collapses_whitespace(self):
        assert sanitize_movie_name("  Movie   Name  ") == "Movie Name"
