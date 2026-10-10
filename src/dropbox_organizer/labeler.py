import base64
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

import anthropic

from .config import CLAUDE_MODEL, build_label_prompt


@dataclass
class LabelResult:
    path: str
    content_hash: str
    labels: list[str]
    description: str
    people_count: int | None
    dominant_colors: list[str]
    analyzed_at: str
    model: str
    file_id: str = ""

    def to_dict(self) -> dict:
        return {
            "content_hash": self.content_hash,
            "labels": self.labels,
            "description": self.description,
            "people_count": self.people_count,
            "dominant_colors": self.dominant_colors,
            "analyzed_at": self.analyzed_at,
            "model": self.model,
        }

    @classmethod
    def from_dict(cls, path: str, d: dict) -> "LabelResult":
        return cls(
            path=path,
            content_hash=d["content_hash"],
            labels=d.get("labels", []),
            description=d.get("description", ""),
            people_count=d.get("people_count"),
            dominant_colors=d.get("dominant_colors", []),
            analyzed_at=d.get("analyzed_at", ""),
            model=d.get("model", ""),
            file_id=d.get("file_id", ""),
        )


class PhotoLabeler:
    def __init__(self, api_key: str, model: str = CLAUDE_MODEL):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def analyze(
        self,
        image_bytes: bytes,
        media_type: str,
        path: str,
        content_hash: str,
        file_id: str = "",
        allowed_labels: list[str] | None = None,
        strict: bool = False,
    ) -> LabelResult:
        b64 = base64.standard_b64encode(image_bytes).decode()
        prompt = build_label_prompt(allowed_labels, strict)
        allowed_set = set(allowed_labels) if allowed_labels else None

        for attempt in range(3):
            message = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": b64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )

            text = message.content[0].text.strip()
            # Strip markdown fences if the model wraps the response anyway
            if text.startswith("```"):
                lines = text.splitlines()
                text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

            try:
                data = json.loads(text)
                labels = data.get("labels", [])

                if strict and allowed_set is not None:
                    invalid = [l for l in labels if l not in allowed_set]
                    if invalid and attempt < 2:
                        # Feed the violation back and retry
                        prompt = (
                            prompt
                            + f"\n\nYour previous response included labels not in the allowed set: {invalid}. "
                            "Return only labels from the allowed set."
                        )
                        continue
                    # Final pass: silently drop any stragglers
                    labels = [l for l in labels if l in allowed_set]

                return LabelResult(
                    path=path,
                    content_hash=content_hash,
                    labels=labels,
                    description=data.get("description", ""),
                    people_count=data.get("people_count"),
                    dominant_colors=data.get("dominant_colors", []),
                    analyzed_at=datetime.now(timezone.utc).isoformat(),
                    model=self.model,
                    file_id=file_id,
                )
            except json.JSONDecodeError:
                if attempt == 2:
                    raise ValueError(f"Claude returned invalid JSON after 3 attempts for {path}:\n{text}")

        raise RuntimeError("Unreachable")
