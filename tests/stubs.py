"""StubDropbox — an in-memory replacement for dropbox.Dropbox.

Returned types use the real Dropbox SDK classes wherever the production code
does isinstance() checks (FileMetadata) or attribute access on typed results
(ListFolderResult, ListTemplateResult, etc.).  Everything else uses lightweight
dataclasses so tests have no network dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import dropbox.file_properties
import dropbox.files


# ---------------------------------------------------------------------------
# Lightweight response stubs for types the SDK would normally return
# ---------------------------------------------------------------------------

@dataclass
class _DownloadResponse:
    content: bytes


# ---------------------------------------------------------------------------
# StubDropbox
# ---------------------------------------------------------------------------

class StubDropbox:
    """Configurable in-memory Dropbox client.

    Add files via ``add_file`` before exercising production code.
    Inspect ``calls`` afterwards to assert which SDK methods were invoked.

    Args:
        page_size: Maximum entries returned per ``files_list_folder`` /
            ``files_list_folder_continue`` call.  Set below the total number
            of files to exercise pagination paths.
    """

    def __init__(self, page_size: int = 1000):
        # path -> (content_bytes, FileMetadata)
        self._files: dict[str, tuple[bytes, dropbox.files.FileMetadata]] = {}
        # template_id -> name
        self._templates: dict[str, str] = {}
        # path -> list[PropertyGroup]
        self._file_properties: dict[str, list] = {}
        # pending pages keyed by cursor string
        self._cursors: dict[str, list] = {}
        self._page_size = page_size
        self._next_template_id = 1000
        # Each entry is (method_name, positional_args, keyword_args)
        self.calls: list[tuple[str, tuple, dict]] = []

    # ------------------------------------------------------------------
    # Setup helpers (not part of the Dropbox API surface)
    # ------------------------------------------------------------------

    def add_file(
        self,
        path: str,
        content: bytes = b"",
        content_hash: str | None = None,
        size: int | None = None,
    ) -> dropbox.files.FileMetadata:
        """Register a file in the stub and return its FileMetadata."""
        name = path.rsplit("/", 1)[-1]
        if content_hash is None:
            # content_hash must be exactly 64 hex chars (Dropbox uses SHA-256 of 4 MB blocks)
            raw = path.encode()
            import hashlib
            content_hash = hashlib.sha256(raw).hexdigest()  # already 64 hex chars

        meta = dropbox.files.FileMetadata(
            name=name,
            path_lower=path.lower(),
            path_display=path,
            id=f"id:{path}",
            client_modified=datetime(2024, 1, 1, tzinfo=timezone.utc),
            server_modified=datetime(2024, 1, 1, tzinfo=timezone.utc),
            rev="0123456789abcdef",
            size=size if size is not None else len(content),
            content_hash=content_hash,
        )
        self._files[path] = (content, meta)
        return meta

    def add_template(self, template_id: str, name: str):
        """Pre-seed a property template (simulates one already existing in Dropbox).

        *template_id* must match the pattern ``(ptid:|/).*`` to satisfy SDK validation.
        """
        self._templates[template_id] = name

    def get_file_properties(self, path: str) -> list:
        """Return the stored PropertyGroups for *path* (test assertion helper)."""
        return self._file_properties.get(path, [])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record(self, name: str, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def _calls_to(self, method: str) -> list[tuple[tuple, dict]]:
        """Return [(args, kwargs), ...] for every call to *method*."""
        return [(a, kw) for (m, a, kw) in self.calls if m == method]

    def _matching_files(self, path: str, recursive: bool) -> list[dropbox.files.FileMetadata]:
        prefix = "" if path in ("", "/") else path.rstrip("/")
        result = []
        for file_path, (_, meta) in self._files.items():
            if recursive:
                match = (
                    prefix == ""
                    or file_path.lower().startswith(prefix.lower() + "/")
                )
            else:
                parent = file_path.rsplit("/", 1)[0] if "/" in file_path.lstrip("/") else ""
                match = parent == prefix or (prefix == "" and parent == "")
            if match:
                result.append(meta)
        return result

    def _paginate(self, entries: list, cursor_prefix: str) -> dropbox.files.ListFolderResult:
        page = entries[: self._page_size]
        rest = entries[self._page_size :]
        # cursor must be non-empty (SDK min_length=1); use a sentinel when exhausted
        if rest:
            cursor = f"{cursor_prefix}:{len(self._cursors)}"
            self._cursors[cursor] = rest
        else:
            cursor = "DONE"
        return dropbox.files.ListFolderResult(
            entries=page,
            cursor=cursor,
            has_more=bool(rest),
        )

    # ------------------------------------------------------------------
    # Dropbox files API
    # ------------------------------------------------------------------

    def files_list_folder(self, path: str, recursive: bool = False, **kwargs) -> dropbox.files.ListFolderResult:
        self._record("files_list_folder", path, recursive=recursive)
        entries = self._matching_files(path, recursive)
        return self._paginate(entries, f"lf:{path}")

    def files_list_folder_continue(self, cursor: str) -> dropbox.files.ListFolderResult:
        self._record("files_list_folder_continue", cursor)
        remaining = self._cursors.pop(cursor, [])
        return self._paginate(remaining, f"lfc:{cursor}")

    def files_download(self, path: str) -> tuple[dropbox.files.FileMetadata, _DownloadResponse]:
        self._record("files_download", path)
        if path not in self._files:
            raise KeyError(f"StubDropbox: no file registered at {path!r}")
        content, meta = self._files[path]
        return meta, _DownloadResponse(content=content)

    # ------------------------------------------------------------------
    # Dropbox file_properties API
    # ------------------------------------------------------------------

    def file_properties_templates_list_for_user(self) -> dropbox.file_properties.ListTemplateResult:
        self._record("file_properties_templates_list_for_user")
        return dropbox.file_properties.ListTemplateResult(
            template_ids=list(self._templates.keys())
        )

    def file_properties_templates_get_for_user(self, template_id: str) -> dropbox.file_properties.GetTemplateResult:
        self._record("file_properties_templates_get_for_user", template_id)
        return dropbox.file_properties.GetTemplateResult(
            name=self._templates.get(template_id, ""),
            description="",
            fields=[],
        )

    def file_properties_templates_add_for_user(
        self, name: str, description: str, fields: list
    ) -> dropbox.file_properties.AddTemplateResult:
        self._record("file_properties_templates_add_for_user", name, description)
        # template_id must match pattern (/|ptid:).* per SDK validation
        template_id = f"ptid:{self._next_template_id}"
        self._next_template_id += 1
        self._templates[template_id] = name
        return dropbox.file_properties.AddTemplateResult(template_id=template_id)

    def file_properties_properties_add(self, path: str, property_groups: list):
        self._record("file_properties_properties_add", path, property_groups)
        self._file_properties.setdefault(path, []).extend(property_groups)

    def file_properties_properties_overwrite(self, path: str, property_groups: list):
        self._record("file_properties_properties_overwrite", path, property_groups)
        self._file_properties[path] = property_groups
