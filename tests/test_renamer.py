"""
Integration tests for src.services.renamer
"""
from pathlib import Path

from src.scrapers.bertina import BertinaImdbResult
from src.services import renamer


def _touch(path: Path) -> None:
    path.write_text("", encoding="utf-8")


def test_tmdb_tag_skips_imdb_search(tmp_path, monkeypatch):
    movie_path = tmp_path / "The Batman (2022) [tmdbid-414906].mp4"
    _touch(movie_path)

    def _fail_search(*_args, **_kwargs):
        raise AssertionError("IMDB search should not run for tmdbid files")

    monkeypatch.setattr(renamer, "search_imdb", _fail_search)

    result = renamer.rename_movie_file(movie_path)
    assert result is not None
    new_path, info = result
    assert new_path == movie_path
    assert info.id_type == "tmdb"
    assert info.imdb_id == "414906"


def test_renames_related_resources(tmp_path, monkeypatch):
    movie_path = tmp_path / "Inception (2010).mkv"
    poster_path = tmp_path / "Inception (2010)-poster.jpg"
    backdrop_path = tmp_path / "Inception (2010)-backdrop.png"
    nfo_path = tmp_path / "Inception (2010).nfo"

    for path in (movie_path, poster_path, backdrop_path, nfo_path):
        _touch(path)

    imdb_result = BertinaImdbResult(
        title="Inception",
        year="2010",
        imdb_id="tt1375666",
        url="https://www.imdb.com/title/tt1375666/",
    )
    monkeypatch.setattr(renamer, "search_imdb", lambda _stem: imdb_result)

    result = renamer.rename_movie_file(movie_path)
    assert result is not None
    new_path, info = result

    assert new_path.name == "Inception (2010) [imdbid-tt1375666].mkv"
    assert info.base_name == "Inception (2010) [imdbid-tt1375666]"

    assert (tmp_path / "Inception (2010) [imdbid-tt1375666]-poster.jpg").exists()
    assert (tmp_path / "Inception (2010) [imdbid-tt1375666]-backdrop.png").exists()
    assert (tmp_path / "Inception (2010) [imdbid-tt1375666].nfo").exists()

    assert not poster_path.exists()
    assert not backdrop_path.exists()
    assert not nfo_path.exists()


def test_filimo_uid_fallback_to_filimo_title(tmp_path, monkeypatch):
    movie_path = tmp_path / "Unknown Title [fuid-aVmdY].mkv"
    _touch(movie_path)

    class _Meta:
        title_en = "Inception"
        year = "2010"

    monkeypatch.setattr(renamer, "_fetch_filimo_metadata", lambda _uid: _Meta())

    imdb_result = BertinaImdbResult(
        title="Inception",
        year="2010",
        imdb_id="tt1375666",
        url="https://www.imdb.com/title/tt1375666/",
    )

    def _search(query: str):
        if query == "Unknown Title":
            return None
        if query == "Inception":
            return imdb_result
        raise AssertionError(f"Unexpected IMDB query: {query}")

    monkeypatch.setattr(renamer, "search_imdb", _search)

    result = renamer.rename_movie_file(movie_path)
    assert result is not None
    new_path, _info = result

    assert new_path.name == "Inception (2010) [imdbid-tt1375666].mkv"
    assert "[fuid-" not in new_path.name
    assert new_path.exists()
