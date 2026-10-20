# -*- coding: utf-8 -*-
"""Windows.Media.Ocr backend, for languages RapidOCR's bundled zh/en models cannot read (ko, ja, ...).

Offline like RapidOCR — the recognizer ships with the OS language pack, nothing leaves the machine —
and on a 760x1280 KakaoTalk window it is ~30x faster (60ms vs 2.0s).

Same call shape as RapidOCR so app/ocr.py can swap one for the other:
    engine(img, use_cls=False) -> ([[box, text, score], ...], None)
where box is 4 clockwise (x, y) points. Windows returns words, not bubbles, so words on one line are
glued into runs and split where the horizontal gap opens up (bubble edge, right-aligned own message).
"""
from __future__ import annotations

import asyncio

import numpy as np
from winsdk.windows.globalization import Language
from winsdk.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
from winsdk.windows.media.ocr import OcrEngine
from winsdk.windows.security.cryptography import CryptographicBuffer

GAP = 0.8    # split a line into runs where the gap between words exceeds this * word height
SCALE = 2    # nearest-neighbour upscale before recognition: on a 760px-wide KakaoTalk window it
             # drops the stray one-character fragments ("I", "口(") for +30ms; 3x brings them back


class WindowsOcr:
    """One engine per process; the event loop is kept alive because a frame arrives every 50ms."""

    def __init__(self, lang: str | None = None):
        self._engine = (OcrEngine.try_create_from_language(Language(lang)) if lang
                        else OcrEngine.try_create_from_user_profile_languages())
        if self._engine is None:
            raise RuntimeError(
                f"Windows OCR 缺少 {lang or '当前用户语言'} 的识别组件，请在系统语言设置中安装后重新开启采集。")
        self._loop = asyncio.new_event_loop()

    @property
    def language(self) -> str:
        return self._engine.recognizer_language.language_tag

    def __call__(self, img: np.ndarray, use_cls: bool = False):
        if not img.size:
            return [], None
        h, w = img.shape[:2]
        limit = OcrEngine.max_image_dimension
        scale = min(float(SCALE), limit / max(h, w))
        if scale != 1:
            height, width = max(1, int(h * scale)), max(1, int(w * scale))
            rows = np.minimum((np.arange(height) / scale).astype(int), h - 1)
            columns = np.minimum((np.arange(width) / scale).astype(int), w - 1)
            img = np.ascontiguousarray(img[rows[:, None], columns])
        h, w = img.shape[:2]
        bgra = np.dstack([img[:, :, ::-1], np.full((h, w, 1), 255, np.uint8)])
        buf = CryptographicBuffer.create_from_byte_array(bgra.tobytes())
        bitmap = SoftwareBitmap.create_copy_from_buffer(buf, BitmapPixelFormat.BGRA8, w, h,
                                                        BitmapAlphaMode.PREMULTIPLIED)
        try:
            result = self._loop.run_until_complete(_recognize(self._engine, bitmap))
        finally:
            bitmap.close()
        # boxes go back in source pixels: app/ocr.py indexes the original frame with them
        return [run for line in result.lines for run in _runs(line, scale)], None

    def close(self):
        self._loop.close()


async def _recognize(engine, bitmap):
    return await engine.recognize_async(bitmap)


def _runs(line, scale: int = 1):
    """Words of one OCR line -> [[box, text, score]] per run, split on wide horizontal gaps."""
    words = [(w.bounding_rect, w.text) for w in line.words]
    out, cur = [], []
    for rect, text in words:
        if cur and rect.x - (cur[-1][0].x + cur[-1][0].width) > GAP * rect.height:
            out.append(_box(cur, scale))
            cur = []
        cur.append((rect, text))
    if cur:
        out.append(_box(cur, scale))
    return out


def _box(run, scale: int = 1):
    x0 = min(r.x for r, _ in run) / scale
    y0 = min(r.y for r, _ in run) / scale
    x1 = max(r.x + r.width for r, _ in run) / scale
    y1 = max(r.y + r.height for r, _ in run) / scale
    text = " ".join(t for _, t in run)
    # Windows OCR reports no per-word confidence; 1.0 keeps the RapidOCR tuple shape usable.
    return [[[x0, y0], [x1, y0], [x1, y1], [x0, y1]], text, 1.0]
