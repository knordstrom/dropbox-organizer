import dropbox.files
import pytest

from dropbox_organizer.scanner import DropboxScanner
from tests.stubs import StubDropbox


def _paths(results) -> list[str]:
    return [e.path_display for e in results]


class TestListPhotos:
    def test_returns_all_photos_under_root(self):
        stub = StubDropbox()
        stub.add_file("/Photos/beach.jpg")
        stub.add_file("/Photos/sunset.png")
        stub.add_file("/Photos/party.webp")

        results = list(DropboxScanner(stub).list_photos("/"))

        assert _paths(results) == ["/Photos/beach.jpg", "/Photos/sunset.png", "/Photos/party.webp"]

    def test_excludes_non_photo_files(self):
        stub = StubDropbox()
        stub.add_file("/Photos/beach.jpg")
        stub.add_file("/Photos/notes.txt")
        stub.add_file("/Photos/data.csv")

        results = list(DropboxScanner(stub).list_photos("/"))

        assert _paths(results) == ["/Photos/beach.jpg"]

    def test_excludes_unsupported_image_formats(self):
        stub = StubDropbox()
        stub.add_file("/Photos/image.bmp")
        stub.add_file("/Photos/image.tiff")
        stub.add_file("/Photos/image.jpg")

        results = list(DropboxScanner(stub).list_photos("/"))

        assert _paths(results) == ["/Photos/image.jpg"]

    def test_all_supported_extensions_are_included(self):
        stub = StubDropbox()
        stub.add_file("/a.jpg")
        stub.add_file("/b.jpeg")
        stub.add_file("/c.png")
        stub.add_file("/d.gif")
        stub.add_file("/e.webp")

        results = list(DropboxScanner(stub).list_photos("/"))

        assert len(results) == 5

    def test_empty_folder_returns_nothing(self):
        stub = StubDropbox()
        results = list(DropboxScanner(stub).list_photos("/"))
        assert results == []

    def test_scoped_path_excludes_files_outside(self):
        stub = StubDropbox()
        stub.add_file("/Photos/beach.jpg")
        stub.add_file("/Videos/clip.jpg")

        results = list(DropboxScanner(stub).list_photos("/Photos"))

        assert _paths(results) == ["/Photos/beach.jpg"]

    def test_recursive_includes_nested_subdirectories(self):
        stub = StubDropbox()
        stub.add_file("/Photos/beach.jpg")
        stub.add_file("/Photos/2024/January/snow.jpg")
        stub.add_file("/Photos/2024/June/bbq.jpg")

        results = list(DropboxScanner(stub).list_photos("/Photos", recursive=True))

        assert len(results) == 3

    def test_non_recursive_excludes_subdirectories(self):
        stub = StubDropbox()
        stub.add_file("/Photos/beach.jpg")
        stub.add_file("/Photos/2024/snow.jpg")

        results = list(DropboxScanner(stub).list_photos("/Photos", recursive=False))

        assert _paths(results) == ["/Photos/beach.jpg"]

    def test_pagination_is_followed(self):
        # page_size=2 forces the scanner to call files_list_folder_continue
        stub = StubDropbox(page_size=2)
        stub.add_file("/a.jpg")
        stub.add_file("/b.jpg")
        stub.add_file("/c.jpg")

        results = list(DropboxScanner(stub).list_photos("/"))

        assert len(results) == 3
        continue_calls = stub._calls_to("files_list_folder_continue")
        assert len(continue_calls) == 1

    def test_results_carry_correct_metadata(self):
        stub = StubDropbox()
        HASH = "a" * 64
        stub.add_file("/Photos/beach.jpg", content=b"x" * 2048, content_hash=HASH)

        results = list(DropboxScanner(stub).list_photos("/"))

        assert len(results) == 1
        meta = results[0]
        assert meta.path_display == "/Photos/beach.jpg"
        assert meta.content_hash == HASH
        assert meta.size == 2048
        assert isinstance(meta, dropbox.files.FileMetadata)

    def test_slash_and_empty_string_both_mean_root(self):
        stub = StubDropbox()
        stub.add_file("/photo.jpg")

        via_slash = list(DropboxScanner(stub).list_photos("/"))
        via_empty = list(DropboxScanner(stub).list_photos(""))

        assert _paths(via_slash) == _paths(via_empty)
