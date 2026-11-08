"""Build the two JPEG data URIs the v2 mock embeds.

The repo has no real camera frame (both _verify runs are the synthetic test
pattern), so the "live" picture here is a locally available photograph cropped
to the stream's 4:3 geometry and graded down to read like a dim webcam frame.
Nothing is fetched: the source file ships inside the checked-out venv samples.
"""

import base64
import io
from pathlib import Path

from PIL import Image, ImageEnhance

ROOT = Path(__file__).resolve().parents[5]
SRC = ROOT / ".venv/Lib/site-packages/matplotlib/mpl-data/sample_data/grace_hopper.jpg"
OUT = Path(__file__).resolve().parent


def grade(img):
    img = ImageEnhance.Brightness(img).enhance(0.82)
    img = ImageEnhance.Color(img).enhance(0.9)
    img = ImageEnhance.Contrast(img).enhance(0.98)
    return img


def uri(img, quality):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True, progressive=False)
    return base64.b64encode(buf.getvalue()).decode("ascii")


src = Image.open(SRC).convert("RGB")
print("source", src.size)

# Stream frame: 4:3 window from the top of the portrait, resampled to 320x240.
frame = grade(src.crop((2, 30, 509, 410)).resize((320, 240), Image.LANCZOS))
frame.save(OUT / "_frame-preview.jpg", "JPEG", quality=88)

# Clip thumbnail: a different crop so the list does not look copy-pasted.
thumb = grade(src.crop((96, 96, 416, 336)).resize((156, 117), Image.LANCZOS))

(OUT / "_frame.b64").write_text(uri(frame, 74), encoding="ascii")
(OUT / "_thumb.b64").write_text(uri(thumb, 62), encoding="ascii")
print("frame b64", (OUT / "_frame.b64").stat().st_size)
print("thumb b64", (OUT / "_thumb.b64").stat().st_size)


