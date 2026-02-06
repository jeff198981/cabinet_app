from __future__ import annotations

from typing import Optional

from PyQt5 import QtCore, QtGui


def qimage_from_raw_fp(raw: bytes) -> Optional[QtGui.QImage]:
    """Best-effort decode for fingerprint preview.

    The FL727 SDK's FL_UpImage sometimes returns:
    - an encoded bitmap (BMP/PNG/JPEG bytes), OR
    - a raw grayscale buffer without header.

    We try decoding as a normal image first; if that fails, we try common
    grayscale sensor sizes.
    """
    if not raw:
        return None

    # 1) Try encoded image bytes (BMP/PNG/JPEG/etc.)
    try:
        img = QtGui.QImage.fromData(raw)
        if not img.isNull():
            return img
    except Exception:
        pass

    # 2) Try raw grayscale buffers with common sizes
    # The SDK may return:
    # - pure grayscale pixels (len == w*h), OR
    # - an 8-bit BMP-like payload (header + palette + pixels).
    # We should NOT blindly strip 1078 bytes because some sensors output
    # raw pixels with length > 1078 (e.g. 160x190 = 30400 bytes).
    n = len(raw)

    candidates: list[bytes] = [raw]

    # BMP-like: 54-byte header + 1024 palette = 1078 bytes, then pixels.
    bmp_like_offset = 1078
    if n > bmp_like_offset:
        # If it looks like BMP ('BM') or if stripping yields a plausible pixel buffer,
        # we will try it as an additional candidate.
        if raw[:2] == b'BM':
            candidates.append(raw[bmp_like_offset:])
        else:
            # Heuristic: only add stripped buffer if its length looks like w*h for
            # a reasonable grayscale image.
            stripped = raw[bmp_like_offset:]
            if len(stripped) % 8 == 0 and 10_000 <= len(stripped) <= 400_000:
                candidates.append(stripped)

    common_pairs = [
        (152, 200),
        (200, 152),
        (160, 160),
        (160, 190),
        (190, 160),
        (208, 288),
        (288, 208),
        (256, 288),
        (288, 256),
        (256, 360),
        (360, 256),
        (320, 480),
        (480, 320),
    ]

    for pixel_payload in candidates:
        n_pixels = len(pixel_payload)

        for w, h in common_pairs:
            if n_pixels == w * h:
                # Prefer portrait orientation for preview
                if h < w:
                    w, h = h, w
                img = QtGui.QImage(pixel_payload, w, h, w, QtGui.QImage.Format_Grayscale8)
                if not img.isNull():
                    return img.copy()  # make it own the bytes

        # 3) Heuristic: try a few likely widths
        for w in (152, 160, 190, 200, 208, 240, 256, 288, 304, 320, 360, 384, 400, 480):
            if w > 0 and n_pixels % w == 0:
                h = n_pixels // w
                if 120 <= h <= 1000:
                    ww, hh = (w, h) if h >= w else (h, w)
                    img = QtGui.QImage(pixel_payload, ww, hh, ww, QtGui.QImage.Format_Grayscale8)
                    if not img.isNull():
                        return img.copy()

    return None


def fpimage_to_png_bytes(raw: bytes) -> Optional[bytes]:
    """Convert captured FP image bytes to PNG bytes for stable DB storage."""
    img = qimage_from_raw_fp(raw)
    if not img or img.isNull():
        return None
    ba = QtCore.QByteArray()
    buf = QtCore.QBuffer(ba)
    buf.open(QtCore.QIODevice.WriteOnly)
    ok = img.save(buf, 'PNG')
    buf.close()
    return bytes(ba) if ok else None
