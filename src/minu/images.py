"""Attaching images to messages and showing them in the terminal."""
import base64, io, shlex
from pathlib import Path

from textual.widgets import Static

from .config import IMG_EXT, IMG_RE

def find_images(text):  # image paths in a message (drag-and-drop pastes a path)
    try: toks = shlex.split(text)
    except ValueError: toks = text.split()
    out = []
    for t in toks:
        p = Path(t.strip(",;:")).expanduser()
        if p.suffix.lower() in IMG_EXT and p.is_file() and p.resolve() not in out: out.append(p.resolve())
    return out

def mentioned_images(text):
    out = []
    for m in IMG_RE.findall(text):
        p = Path(m).expanduser()
        if p.is_file() and p.resolve() not in out: out.append(p.resolve())
    return out

def encode_image(p):
    from PIL import Image
    im = Image.open(p); im.thumbnail((1024, 1024)); im = im.convert("RGB")
    b = io.BytesIO(); im.save(b, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()

IMAGES = True
def image_widget(p):
    if not IMAGES: return Static(f"[image: {p}]", classes="sys", markup=False)
    from textual_image.widget import Image
    return Image(str(p), classes="img")
