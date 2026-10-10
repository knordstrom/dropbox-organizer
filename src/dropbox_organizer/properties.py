import json
import os
import dropbox
import dropbox.file_properties

from .labeler import LabelResult

TEMPLATE_CACHE_PATH = os.path.join("data", ".property_template_id")


class DropboxPropertyWriter:
    TEMPLATE_NAME = "photo-labels"

    def __init__(self, dbx: dropbox.Dropbox):
        self.dbx = dbx
        self._template_id: str | None = None

    def ensure_template(self) -> str:
        if self._template_id:
            return self._template_id

        # Check cached template ID on disk
        if os.path.exists(TEMPLATE_CACHE_PATH):
            with open(TEMPLATE_CACHE_PATH) as f:
                self._template_id = f.read().strip()
            return self._template_id

        # Check if template already exists in Dropbox
        result = self.dbx.file_properties_templates_list_for_user()
        for tmpl in result.template_ids:
            info = self.dbx.file_properties_templates_get_for_user(tmpl)
            if info.name == self.TEMPLATE_NAME:
                self._template_id = tmpl
                self._cache_template_id(tmpl)
                return tmpl

        # Create new template
        fields = [
            dropbox.file_properties.PropertyFieldTemplate(
                name="labels",
                description="Comma-separated content labels",
                type=dropbox.file_properties.PropertyType.string,
            ),
            dropbox.file_properties.PropertyFieldTemplate(
                name="description",
                description="Photo content description",
                type=dropbox.file_properties.PropertyType.string,
            ),
            dropbox.file_properties.PropertyFieldTemplate(
                name="analyzed_at",
                description="ISO8601 timestamp of analysis",
                type=dropbox.file_properties.PropertyType.string,
            ),
        ]
        result = self.dbx.file_properties_templates_add_for_user(
            name=self.TEMPLATE_NAME,
            description="AI-generated photo labels",
            fields=fields,
        )
        self._template_id = result.template_id
        self._cache_template_id(result.template_id)
        return self._template_id

    def write_labels(self, path: str, result: LabelResult):
        template_id = self.ensure_template()
        fields = [
            dropbox.file_properties.PropertyField(name="labels", value=", ".join(result.labels)),
            dropbox.file_properties.PropertyField(name="description", value=result.description[:1000]),
            dropbox.file_properties.PropertyField(name="analyzed_at", value=result.analyzed_at),
        ]
        prop_group = dropbox.file_properties.PropertyGroup(template_id=template_id, fields=fields)
        try:
            self.dbx.file_properties_properties_add(path, [prop_group])
        except dropbox.exceptions.ApiError as e:
            # Property group may already exist; overwrite it
            if "property_group_already_exists" in str(e):
                self.dbx.file_properties_properties_overwrite(path, [prop_group])
            else:
                raise

        for label in result.labels:
            try:
                self.dbx.files_tags_add(path, label)
            except dropbox.exceptions.ApiError:
                pass  # Tag may already exist; ignore

    def _cache_template_id(self, template_id: str):
        os.makedirs(os.path.dirname(TEMPLATE_CACHE_PATH) or ".", exist_ok=True)
        with open(TEMPLATE_CACHE_PATH, "w") as f:
            f.write(template_id)
