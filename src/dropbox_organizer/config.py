import os

# File extensions to discover in Dropbox
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# Extensions Claude's vision API accepts directly
CLAUDE_SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

EXTENSION_TO_MEDIA_TYPE = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB

CLAUDE_MODEL = "claude-opus-4-5"

DEFAULT_TOKEN_PATH = os.path.join("data", ".dropbox_token")
DEFAULT_STATE_PATH = os.path.join("data", "labels.db")

def build_label_prompt(allowed_labels: list[str] | None = None, strict: bool = False) -> str:
    if allowed_labels and strict:
        label_rule = (
            f"- labels: choose ONLY from this exact set — {allowed_labels} — "
            "pick every label from the set that applies to this photo; do not invent any others"
        )
    elif allowed_labels:
        label_rule = (
            f"- labels: prefer labels from this set — {allowed_labels} — "
            "but you may also add other descriptive tags if important content is not covered"
        )
    else:
        label_rule = "- labels: 5–15 short, lowercase tags describing objects, scenes, activities, mood, setting"

    return f"""Analyze this photo and return a JSON object with exactly these fields:

{{
  "labels": ["list", "of", "descriptive", "tags"],
  "description": "One to two sentence description of the image content.",
  "people_count": null,
  "dominant_colors": ["color1", "color2", "color3"]
}}

Rules:
{label_rule}
- description: factual, 1–2 sentences, no interpretation beyond what is visible
- people_count: integer count of visible people, or null if none or uncertain
- dominant_colors: 2–5 color names (e.g. "blue", "golden", "dark green")
- Respond with ONLY the JSON object, no markdown fences, no extra text."""
