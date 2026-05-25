import types
from pathlib import Path

import src.processor as processor
from src.utils.name_parser import MovieInfo


def test_filimo_uid_uses_uid_metadata(monkeypatch, tmp_path: Path):
    movie_path = tmp_path / "Asterix [fuid-4AB0h].mkv"
    movie_info = MovieInfo(
        name="Asterix",
        year="2014",
        imdb_id="tt1234567",
        id_type="imdb",
        extension=".mkv",
    )

    def fake_rename(path: Path, dry_run: bool = False):
        return movie_path, movie_info

    monkeypatch.setattr(processor, "rename_movie_file", fake_rename)

    search_called = {"called": False}

    def fake_search(name: str, year: str):
        search_called["called"] = True
        return None

    monkeypatch.setattr(processor, "filimo_search", fake_search)

    meta = types.SimpleNamespace(
        uid="4AB0h",
        title_en="Asterix - The Mansions of the Gods",
        title_fa="",
        year="2014",
        imdb_rate="7.0",
        description_fa="",
        description_en="",
        duration_seconds=6000,
        poster_url="https://example.com/poster.jpg",
        backdrop_url="https://example.com/backdrop.jpg",
        categories=[],
        countries=[],
        director=[{"name": "Alexandre Astier"}],
        age_range="",
    )

    import src.services.filimo_downloader as filimo_downloader

    monkeypatch.setattr(filimo_downloader, "get_token", lambda: "token")
    monkeypatch.setattr(filimo_downloader, "fetch_metadata", lambda uid, token: meta)

    def assert_filimo_movie(movie_dir, info, filimo_movie, dry_run: bool = False):
        assert filimo_movie is not None
        assert filimo_movie.uid == "4AB0h"
        return True

    monkeypatch.setattr(processor, "download_poster", assert_filimo_movie)
    monkeypatch.setattr(processor, "download_backdrop", assert_filimo_movie)
    monkeypatch.setattr(processor, "generate_nfo", assert_filimo_movie)

    result = processor.process_movie(movie_path, dry_run=True)

    assert result["error"] is None
    assert search_called["called"] is False
