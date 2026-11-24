"""Read a single grocery image inside the local PickLoop server."""
from io import BytesIO
from threading import Lock

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from . import grocery_catalogue


MAX_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 24_000_000
FORMATS = ("JPEG", "PNG", "WEBP")


def read_upload(data, require_gtin, produce):
    try:
        with Image.open(BytesIO(data), formats=FORMATS) as image:
            if image.width * image.height > MAX_PIXELS:
                raise HTTPException(413, "사진을 2,400만 픽셀 이하로 줄여 주세요.")
            rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"))
    except Image.DecompressionBombError as error:
        raise HTTPException(413, "사진을 2,400만 픽셀 이하로 줄여 주세요.") from error
    except (OSError, ValueError, UnidentifiedImageError) as error:
        raise HTTPException(400, "열 수 있는 JPEG, PNG, WebP 사진을 선택해 주세요.") from error
    try:
        return grocery_catalogue.recognize_rgb(rgb, require_gtin=require_gtin, produce=produce)
    except (ImportError, RuntimeError, OSError) as error:
        raise HTTPException(503, "사진 인식 모델을 열 수 없습니다. catalogue 패키지 설치와 모델 다운로드 연결을 확인해 주세요.") from error


def add_photo_route(app):
    busy = Lock()

    @app.post("/api/recognize")
    async def recognize(request: Request, require_gtin: bool = False, produce: bool = False):
        if request.headers.get("content-type", "").split(";")[0] not in ("image/jpeg", "image/png", "image/webp"):
            raise HTTPException(415, "JPEG, PNG, WebP 사진을 선택해 주세요.")
        if not busy.acquire(blocking=False):
            raise HTTPException(429, "이전 사진을 판별 중입니다. 잠시 후 다시 시도해 주세요.")
        try:
            data = bytearray()
            async for chunk in request.stream():
                if len(data) + len(chunk) > MAX_BYTES:
                    raise HTTPException(413, "사진을 12 MiB 이하로 줄여 주세요.")
                data.extend(chunk)
            return await run_in_threadpool(read_upload, data, require_gtin, produce)
        finally:
            busy.release()
