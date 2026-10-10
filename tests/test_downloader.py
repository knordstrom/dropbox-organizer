import pytest

from dropbox_organizer.config import MAX_IMAGE_BYTES
from dropbox_organizer.downloader import FileTooLargeError, PhotoDownloader
from tests.stubs import StubDropbox


class TestDownloadToBytes:
    def test_returns_content_bytes(self):
        stub = StubDropbox()
        stub.add_file("/Photos/beach.jpg", content=b"\xff\xd8\xff" + b"\x00" * 100)

        data, _ = PhotoDownloader(stub).download_to_bytes("/Photos/beach.jpg")

        assert data[:3] == b"\xff\xd8\xff"

    def test_jpg_resolves_to_jpeg_media_type(self):
        stub = StubDropbox()
        stub.add_file("/Photos/beach.jpg", content=b"data")

        _, media_type = PhotoDownloader(stub).download_to_bytes("/Photos/beach.jpg")

        assert media_type == "image/jpeg"

    def test_jpeg_extension_resolves_to_jpeg_media_type(self):
        stub = StubDropbox()
        stub.add_file("/Photos/photo.jpeg", content=b"data")

        _, media_type = PhotoDownloader(stub).download_to_bytes("/Photos/photo.jpeg")

        assert media_type == "image/jpeg"

    def test_png_resolves_to_png_media_type(self):
        stub = StubDropbox()
        stub.add_file("/Photos/diagram.png", content=b"data")

        _, media_type = PhotoDownloader(stub).download_to_bytes("/Photos/diagram.png")

        assert media_type == "image/png"

    def test_gif_resolves_to_gif_media_type(self):
        stub = StubDropbox()
        stub.add_file("/Photos/anim.gif", content=b"data")

        _, media_type = PhotoDownloader(stub).download_to_bytes("/Photos/anim.gif")

        assert media_type == "image/gif"

    def test_webp_resolves_to_webp_media_type(self):
        stub = StubDropbox()
        stub.add_file("/Photos/photo.webp", content=b"data")

        _, media_type = PhotoDownloader(stub).download_to_bytes("/Photos/photo.webp")

        assert media_type == "image/webp"

    def test_unknown_extension_falls_back_to_jpeg(self):
        stub = StubDropbox()
        stub.add_file("/Photos/photo.unknown", content=b"data")

        _, media_type = PhotoDownloader(stub).download_to_bytes("/Photos/photo.unknown")

        assert media_type == "image/jpeg"

    def test_raises_file_too_large_error_when_content_exceeds_limit(self):
        stub = StubDropbox()
        oversized = b"x" * (MAX_IMAGE_BYTES + 1)
        stub.add_file("/Photos/huge.jpg", content=oversized)

        with pytest.raises(FileTooLargeError):
            PhotoDownloader(stub).download_to_bytes("/Photos/huge.jpg")

    def test_file_exactly_at_limit_is_accepted(self):
        stub = StubDropbox()
        at_limit = b"x" * MAX_IMAGE_BYTES
        stub.add_file("/Photos/big.jpg", content=at_limit)

        data, _ = PhotoDownloader(stub).download_to_bytes("/Photos/big.jpg")

        assert len(data) == MAX_IMAGE_BYTES

    def test_issues_one_download_call_per_invocation(self):
        stub = StubDropbox()
        stub.add_file("/Photos/a.jpg", content=b"data")

        PhotoDownloader(stub).download_to_bytes("/Photos/a.jpg")
        PhotoDownloader(stub).download_to_bytes("/Photos/a.jpg")

        assert len(stub._calls_to("files_download")) == 2
