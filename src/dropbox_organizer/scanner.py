from typing import Iterator
import dropbox
import dropbox.files

from .config import SUPPORTED_EXTENSIONS


class DropboxScanner:
    def __init__(self, dbx: dropbox.Dropbox):
        self.dbx = dbx

    def list_photos(self, root_path: str = "", recursive: bool = True) -> Iterator[dropbox.files.FileMetadata]:
        # Dropbox API uses "" for root, not "/"
        path = "" if root_path in ("/", "") else root_path.rstrip("/")

        result = self.dbx.files_list_folder(path, recursive=recursive)
        while True:
            for entry in result.entries:
                if isinstance(entry, dropbox.files.FileMetadata):
                    ext = _extension(entry.name)
                    if ext in SUPPORTED_EXTENSIONS:
                        yield entry
            if not result.has_more:
                break
            result = self.dbx.files_list_folder_continue(result.cursor)


def _extension(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot != -1 else ""
