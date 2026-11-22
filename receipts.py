"""Receipt image decoding, compact JPEG archiving and Tesseract OCR."""
import base64
from contextlib import closing
import binascii
import io
import math
import os
import subprocess
import tempfile
import storage
import threading
import warnings
from pathlib import Path

import pypdfium2 as pdfium

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

register_heif_opener()
Image.MAX_IMAGE_PIXELS = 25_000_000
OCR_SLOT = threading.BoundedSemaphore(1)
ARCHIVE_SLOT = threading.BoundedSemaphore(1)


PDF_LOCK = threading.Lock()  # PDFium must not be entered from concurrent threads.
MAX_PDF_PAGES = 5


def pdf_pages(raw):
    """Render every page, rejecting oversize documents before allocating images."""
    images = []
    try:
        with PDF_LOCK, closing(pdfium.PdfDocument(raw)) as document:
            if not 1 <= len(document) <= MAX_PDF_PAGES:
                raise ValueError('PDF muss 1 bis 5 Seiten enthalten.')
            sizes = []
            for index in range(len(document)):
                with closing(document[index]) as page:
                    width, height = page.get_size()
                    if not all(math.isfinite(v) and v > 0 for v in (width, height)):
                        raise ValueError('Ungültige PDF-Seitengröße.')
                    rendered_height = math.ceil(height * 1600 / width)
                    if rendered_height > 5000 or rendered_height < 1:
                        raise ValueError('PDF-Seitenformat ist zu lang oder ungültig.')
                    sizes.append((width, rendered_height))
            if 1600 * (sum(h for _, h in sizes) + 16 * (len(sizes)-1)) > 25_000_000:
                raise ValueError('PDF ist zu groß. Bitte weniger Seiten auswählen.')
            for index, (width, _) in enumerate(sizes):
                with closing(document[index]) as page:
                    bitmap = page.render(scale=1600 / width)
                    try:
                        images.append(bitmap.to_pil().convert('RGB'))
                    finally:
                        bitmap.close()
        return images
    except Exception as error:
        for image in images:
            image.close()
        if isinstance(error, ValueError):
            raise
        raise ValueError('PDF nicht lesbar oder passwortgeschützt. Bitte eine ungeschützte PDF verwenden.') from None


def pdf_image(raw):
    pages = pdf_pages(raw)
    try:
        image = Image.new('RGB', (max(p.width for p in pages), sum(p.height for p in pages) + 16*(len(pages)-1)), 'white')
        top = 0
        for page in pages:
            image.paste(page, (0, top))
            top += page.height + 16
        return image
    finally:
        for page in pages:
            page.close()


def prepare_jpeg(encoded):
    """Keep the full photo, orient it correctly, and strip camera metadata."""
    if not isinstance(encoded, str):
        raise ValueError('Bitte eine Bilddatei auswählen.')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('Ungültige Bilddatei.') from None
    if not raw or len(raw) > 12_000_000:
        raise ValueError('Bild ist leer oder zu groß (maximal 12 MB).')
    if not ARCHIVE_SLOT.acquire(blocking=False):
        raise OCRBusy('Die Bildverarbeitung ist gerade belegt. Bitte kurz warten und erneut speichern.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with (pdf_image(raw) if raw.startswith(b'%PDF-') else Image.open(io.BytesIO(raw))) as source:
                if source.width * source.height > Image.MAX_IMAGE_PIXELS:
                    raise ValueError('Bildauflösung ist zu hoch (maximal 25 Megapixel).')
                oriented = ImageOps.exif_transpose(source)
                if oriented.mode in ('RGBA', 'LA') or 'transparency' in oriented.info:
                    rgba = oriented.convert('RGBA')
                    image = Image.new('RGB', rgba.size, 'white')
                    image.paste(rgba, mask=rgba.getchannel('A'))
                else:
                    image = oriented.convert('RGB')
                if not raw.startswith(b'%PDF-'):
                    image.thumbnail((3200, 3200), Image.Resampling.LANCZOS)
                # Copy pixels without EXIF, GPS, comments or embedded thumbnails.
                clean = Image.new('RGB', image.size)
                clean.paste(image)
                out = io.BytesIO()
                clean.save(out, format='JPEG', quality=85, optimize=True, progressive=True, subsampling=0)
                if raw.startswith(b'%PDF-') and out.tell() > 4_000_000:
                    for quality in (75, 65):
                        out = io.BytesIO()
                        clean.save(out, format='JPEG', quality=quality, optimize=True, progressive=True)
                        if out.tell() <= 4_000_000:
                            break
                    if out.tell() > 4_000_000:
                        raise ValueError('PDF ist nach Kompression zu groß. Bitte weniger Seiten auswählen.')
                return out.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('Bild nicht lesbar. Bitte JPEG, PNG, WebP oder HEIC verwenden.') from None
    finally:
        ARCHIVE_SLOT.release()


def recognize_text(encoded):
    if not isinstance(encoded, str):
        raise ValueError('Bitte eine Bilddatei auswählen.')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('Ungültige Bilddatei.') from None
    if not raw or len(raw) > 12_000_000:
        raise ValueError('Bild ist leer oder zu groß (maximal 12 MB).')
    if raw.startswith(b'%PDF-'):
        pages = pdf_pages(raw)
        try:
            texts = []
            for page in pages:
                encoded_page = io.BytesIO()
                page.save(encoded_page, format='JPEG', quality=90)
                texts.append(recognize_text(base64.b64encode(encoded_page.getvalue()).decode('ascii')))
            return '\n\n'.join(texts)
        finally:
            for page in pages:
                page.close()
    if not OCR_SLOT.acquire(blocking=False):
        raise OCRBusy('Die Texterkennung ist gerade belegt. Bitte kurz warten und erneut versuchen.')
    try:
        with tempfile.TemporaryDirectory(prefix='kassensturz-', dir=storage.temporary_directory()) as folder:
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
