import io

import dropbox
from PIL import Image

from .config import MAX_IMAGE_BYTES, EXTENSION_TO_MEDIA_TYPE


class FileTooLargeError(Exception):
    pass


class PhotoDownloader:
    def __init__(self, dbx: dropbox.Dropbox):
        self.dbx = dbx

    def download_to_bytes(self, path: str) -> tuple[bytes, str]:
        _, response = self.dbx.files_download(path)
        data = response.content
        ext = path[path.rfind("."):].lower() if "." in path else ""
        media_type = EXTENSION_TO_MEDIA_TYPE.get(ext, "image/jpeg")

        if len(data) <= MAX_IMAGE_BYTES:
            return data, media_type

        # Downsample to JPEG until under the size limit
        data = _downsample_to_jpeg(data)
        return data, "image/jpeg"


def _downsample_to_jpeg(data: bytes) -> bytes:
    img = Image.open(io.BytesIO(data))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    quality = 85
    scale = 1.0

    while True:
        if scale < 1.0:
            w = max(1, int(img.width * scale))
            h = max(1, int(img.height * scale))
            candidate = img.resize((w, h), Image.LANCZOS)
        else:
            candidate = img

        buf = io.BytesIO()
        candidate.save(buf, format="JPEG", quality=quality, optimize=True)
        result = buf.getvalue()

        if len(result) <= MAX_IMAGE_BYTES:
            return result

        # Reduce quality first, then scale down
        if quality > 50:
            quality -= 10
        else:
            scale *= 0.75
