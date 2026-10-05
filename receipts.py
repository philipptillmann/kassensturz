"""Image decoding and Tesseract OCR; receipt images never persist in the data volume."""
import base64
import binascii
import io
import os
import subprocess
import tempfile
import threading
import warnings
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

register_heif_opener()
Image.MAX_IMAGE_PIXELS = 25_000_000
OCR_SLOT = threading.BoundedSemaphore(1)


def recognize_text(encoded):
    if not isinstance(encoded, str):
        raise ValueError('Bitte eine Bilddatei auswählen.')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('Ungültige Bilddatei.') from None
    if not raw or len(raw) > 12_000_000:
        raise ValueError('Bild ist leer oder zu groß (maximal 12 MB).')
    if not OCR_SLOT.acquire(blocking=False):
        raise OCRBusy('Die Texterkennung ist gerade belegt. Bitte kurz warten und erneut versuchen.')
    try:
        with tempfile.TemporaryDirectory(prefix='kassensturz-') as folder:
            path = Path(folder) / 'receipt.png'
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('error', Image.DecompressionBombWarning)
                    with Image.open(io.BytesIO(raw)) as source:
                        if source.width * source.height > Image.MAX_IMAGE_PIXELS:
                            raise ValueError('Bildauflösung ist zu hoch (maximal 25 Megapixel).')
                        image = ImageOps.exif_transpose(source).convert('RGB')
                        image.thumbnail((4000, 4000))
                        image.save(path, format='PNG')
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
                raise ValueError('Bild nicht lesbar. Bitte JPEG, PNG, WebP oder HEIC verwenden.') from None
            try:
                result = subprocess.run(
                    ['tesseract', str(path), 'stdout', '-l', 'deu+eng', '--psm', '6'],
                    capture_output=True, text=True, timeout=60,
                    env={**os.environ, 'OMP_THREAD_LIMIT': '1'},
                )
            except FileNotFoundError:
                raise ValueError('Tesseract ist nicht installiert. Bitte das Docker-Image verwenden.') from None
            except subprocess.TimeoutExpired:
                raise ValueError('Texterkennung hat zu lange gedauert. Bitte ein kleineres Bild auswählen.') from None
            if result.returncode:
                raise ValueError('Texterkennung fehlgeschlagen. Bitte ein schärferes Foto verwenden.')
            return result.stdout
    finally:
        OCR_SLOT.release()


class OCRBusy(Exception):
    pass
