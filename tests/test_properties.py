import pytest

import dropbox.file_properties

from dropbox_organizer import properties as props_module
from dropbox_organizer.labeler import LabelResult
from dropbox_organizer.properties import DropboxPropertyWriter
from tests.stubs import StubDropbox


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(path: str = "/Photos/beach.jpg") -> LabelResult:
    return LabelResult(
        path=path,
        content_hash="abc123",
        labels=["outdoor", "beach", "sunset"],
        description="A golden beach at sunset.",
        people_count=2,
        dominant_colors=["orange", "blue"],
        analyzed_at="2026-01-01T00:00:00+00:00",
        model="claude-opus-4-5",
    )


# ---------------------------------------------------------------------------
# ensure_template
# ---------------------------------------------------------------------------

class TestEnsureTemplate:
    def test_creates_template_when_none_exist(self, tmp_path, monkeypatch):
        monkeypatch.setattr(props_module, "TEMPLATE_CACHE_PATH", str(tmp_path / ".tid"))
        stub = StubDropbox()

        writer = DropboxPropertyWriter(stub)
        tid = writer.ensure_template()

        assert tid.startswith("ptid:")
        create_calls = stub._calls_to("file_properties_templates_add_for_user")
        assert len(create_calls) == 1
        assert create_calls[0][0][0] == DropboxPropertyWriter.TEMPLATE_NAME

    def test_reuses_template_that_already_exists_in_dropbox(self, tmp_path, monkeypatch):
        monkeypatch.setattr(props_module, "TEMPLATE_CACHE_PATH", str(tmp_path / ".tid"))
        stub = StubDropbox()
        stub.add_template("ptid:existing", DropboxPropertyWriter.TEMPLATE_NAME)

        writer = DropboxPropertyWriter(stub)
        tid = writer.ensure_template()

        assert tid == "ptid:existing"
        assert len(stub._calls_to("file_properties_templates_add_for_user")) == 0

    def test_second_call_uses_in_memory_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(props_module, "TEMPLATE_CACHE_PATH", str(tmp_path / ".tid"))
        stub = StubDropbox()

        writer = DropboxPropertyWriter(stub)
        tid1 = writer.ensure_template()
        tid2 = writer.ensure_template()

        assert tid1 == tid2
        # List should only be called once; the second call hits the in-memory cache
        assert len(stub._calls_to("file_properties_templates_list_for_user")) == 1

    def test_disk_cache_is_written_after_creation(self, tmp_path, monkeypatch):
        cache_path = tmp_path / ".tid"
        monkeypatch.setattr(props_module, "TEMPLATE_CACHE_PATH", str(cache_path))
        stub = StubDropbox()

        writer = DropboxPropertyWriter(stub)
        tid = writer.ensure_template()

        assert cache_path.read_text().strip() == tid

    def test_disk_cache_is_read_on_next_instantiation(self, tmp_path, monkeypatch):
        cache_path = tmp_path / ".tid"
        monkeypatch.setattr(props_module, "TEMPLATE_CACHE_PATH", str(cache_path))
        stub = StubDropbox()

        # First writer creates the template and writes the cache
        DropboxPropertyWriter(stub).ensure_template()
        recorded_tid = cache_path.read_text().strip()

        # Second writer (fresh instance, same cache file) should skip API calls
        stub.calls.clear()
        writer2 = DropboxPropertyWriter(stub)
        tid = writer2.ensure_template()

        assert tid == recorded_tid
        assert len(stub._calls_to("file_properties_templates_list_for_user")) == 0


# ---------------------------------------------------------------------------
# write_labels
# ---------------------------------------------------------------------------

class TestWriteLabels:
    def test_properties_are_stored_on_the_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(props_module, "TEMPLATE_CACHE_PATH", str(tmp_path / ".tid"))
        stub = StubDropbox()
        result = _make_result("/Photos/beach.jpg")

        DropboxPropertyWriter(stub).write_labels("/Photos/beach.jpg", result)

        groups = stub.get_file_properties("/Photos/beach.jpg")
        assert len(groups) == 1

    def test_labels_field_contains_comma_joined_labels(self, tmp_path, monkeypatch):
        monkeypatch.setattr(props_module, "TEMPLATE_CACHE_PATH", str(tmp_path / ".tid"))
        stub = StubDropbox()
        result = _make_result()

        DropboxPropertyWriter(stub).write_labels(result.path, result)

        fields = {f.name: f.value for f in stub.get_file_properties(result.path)[0].fields}
        assert fields["labels"] == "outdoor, beach, sunset"

    def test_description_field_is_stored(self, tmp_path, monkeypatch):
        monkeypatch.setattr(props_module, "TEMPLATE_CACHE_PATH", str(tmp_path / ".tid"))
        stub = StubDropbox()
        result = _make_result()

        DropboxPropertyWriter(stub).write_labels(result.path, result)

        fields = {f.name: f.value for f in stub.get_file_properties(result.path)[0].fields}
        assert fields["description"] == result.description

    def test_analyzed_at_field_is_stored(self, tmp_path, monkeypatch):
        monkeypatch.setattr(props_module, "TEMPLATE_CACHE_PATH", str(tmp_path / ".tid"))
        stub = StubDropbox()
        result = _make_result()

        DropboxPropertyWriter(stub).write_labels(result.path, result)

        fields = {f.name: f.value for f in stub.get_file_properties(result.path)[0].fields}
        assert fields["analyzed_at"] == result.analyzed_at

    def test_property_group_uses_template_id(self, tmp_path, monkeypatch):
        monkeypatch.setattr(props_module, "TEMPLATE_CACHE_PATH", str(tmp_path / ".tid"))
        stub = StubDropbox()
        result = _make_result()

        writer = DropboxPropertyWriter(stub)
        writer.write_labels(result.path, result)

        group = stub.get_file_properties(result.path)[0]
        assert group.template_id == writer._template_id

    def test_long_description_is_truncated_to_1000_chars(self, tmp_path, monkeypatch):
        monkeypatch.setattr(props_module, "TEMPLATE_CACHE_PATH", str(tmp_path / ".tid"))
        stub = StubDropbox()
        result = _make_result()
        result.description = "x" * 2000

        DropboxPropertyWriter(stub).write_labels(result.path, result)

        fields = {f.name: f.value for f in stub.get_file_properties(result.path)[0].fields}
        assert len(fields["description"]) == 1000

    def test_write_labels_calls_properties_add(self, tmp_path, monkeypatch):
        monkeypatch.setattr(props_module, "TEMPLATE_CACHE_PATH", str(tmp_path / ".tid"))
        stub = StubDropbox()
        result = _make_result()

        DropboxPropertyWriter(stub).write_labels(result.path, result)

        assert len(stub._calls_to("file_properties_properties_add")) == 1
