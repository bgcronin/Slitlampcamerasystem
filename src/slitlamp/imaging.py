from __future__ import annotations

import io
import math
import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from .models import uid

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".cr2", ".cr3"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}


def ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def process_options() -> dict:
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def load_image(path: Path) -> Image.Image:
    with Image.open(path) as source:
        source.load()
        image = ImageOps.exif_transpose(source)
        icc = source.info.get("icc_profile")
        if icc:
            from PIL import ImageCms

            try:
                image = ImageCms.profileToProfile(
                    image,
                    ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                    ImageCms.createProfile("sRGB"),
                    outputMode="RGB",
                )
            except (ImageCms.PyCMSError, OSError, ValueError):
                raise ValueError("The embedded colour profile could not be read; original retained.")
        return image.convert("RGB").copy()


def probe(path: Path, kind: str) -> dict:
    if kind == "image":
        if path.suffix.lower() in {".cr2", ".cr3"}:
            return {
                "width": 0,
                "height": 0,
                "metadata": {"raw": True, "preview": "Set camera to JPEG or RAW+JPEG for image editing."},
            }
        image = load_image(path)
        return {"width": image.width, "height": image.height}
    import imageio_ffmpeg

    reader = imageio_ffmpeg.read_frames(str(path), pix_fmt="rgb24")
    try:
        metadata = next(reader)
        next(reader)  # A playable frame must exist before the recording is marked saved.
        return {
            "width": metadata["size"][0],
            "height": metadata["size"][1],
            "duration": metadata.get("duration", 0),
            "metadata": {"fps": metadata.get("fps", 0)},
        }
    finally:
        reader.close()


def video_frame(path: Path, seconds=0.0) -> Image.Image:
    result = subprocess.run(
        [
            ffmpeg(),
            "-v",
            "error",
            "-ss",
            str(max(0, seconds)),
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "-",
        ],
        capture_output=True,
        timeout=30,
        **process_options(),
    )
    if result.returncode or not result.stdout:
        raise ValueError("Could not extract a frame from this recording.")
    return Image.open(io.BytesIO(result.stdout)).convert("RGB")


def font(size: int):
    for name in (
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def adjustments(image: Image.Image, edits: dict) -> Image.Image:
    image = image.copy()
    image = ImageEnhance.Brightness(image).enhance(float(edits.get("brightness", 1)))
    image = ImageEnhance.Contrast(image).enhance(float(edits.get("contrast", 1)))
    warmth = float(edits.get("warmth", 0))
    if warmth:
        r, g, b = image.split()
        r = r.point([max(0, min(255, int(i * (1 + warmth * 0.15)))) for i in range(256)])
        b = b.point([max(0, min(255, int(i * (1 - warmth * 0.15)))) for i in range(256)])
        image = Image.merge("RGB", (r, g, b))
    sharpness = float(edits.get("sharpness", 0))
    if sharpness:
        image = image.filter(ImageFilter.UnsharpMask(radius=1.0, percent=int(sharpness * 80), threshold=3))
    return image


def draw_annotations(image: Image.Image, annotations: list[dict]) -> Image.Image:
    image = image.copy()
    draw = ImageDraw.Draw(image)
    for item in annotations:
        points = [(float(p[0]) * image.width, float(p[1]) * image.height) for p in item["points"]]
        if not points:
            continue
        colour = item.get("color", "#facc15")
        width = max(1, round(float(item.get("width", 0.003)) * image.width))
        kind = item["kind"]
        if kind == "text":
            draw.text(
                points[0],
                item.get("text", ""),
                font=font(max(8, int(item.get("size", 0.025) * image.width))),
                fill=colour,
            )
        elif len(points) >= 2:
            a, b = points[0], points[-1]
            bounds = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
            if kind == "ellipse":
                draw.ellipse(bounds, outline=colour, width=width)
            elif kind == "rectangle":
                draw.rectangle(bounds, outline=colour, width=width)
            else:
                draw.line(points, fill=colour, width=width, joint="curve")
                if kind == "arrow":
                    angle = math.atan2(b[1] - a[1], b[0] - a[0])
                    length = max(width * 5, image.width * 0.015)
                    tip1 = (b[0] - length * math.cos(angle - 0.45), b[1] - length * math.sin(angle - 0.45))
                    tip2 = (b[0] - length * math.cos(angle + 0.45), b[1] - length * math.sin(angle + 0.45))
                    draw.polygon([b, tip1, tip2], fill=colour)
    return image


def render(path: Path, edits=None, annotations=None) -> Image.Image:
    edits = edits or {}
    image = adjustments(load_image(path), edits)
    if annotations:
        image = draw_annotations(image, annotations)
    crop = edits.get("crop")
    if crop:
        left, top, right, bottom = crop
        if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
            raise ValueError("Invalid crop rectangle.")
        image = image.crop(
            (
                round(left * image.width),
                round(top * image.height),
                round(right * image.width),
                round(bottom * image.height),
            )
        )
    angle = float(edits.get("rotation", 0)) + float(edits.get("straighten", 0))
    if angle:
        image = image.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True)
    return image


def prepare_export(catalog, mid: str, mode: str = "original", fmt="JPEG") -> Path:
    if mode not in ("original", "edited", "annotated"):
        raise ValueError("Unknown export mode.")
    with catalog.lock:
        item = catalog.media(mid)
        if item["status"] != "ready" or item["deleted_at"]:
            raise ValueError("Only saved, non-deleted items can be exported.")
        if item["eye"] not in ("R", "L"):
            raise ValueError("Confirm the eye before exporting.")
        source = catalog.path(item["path"])
        folder = catalog.root / ".exports" / uid()
        folder.mkdir()
        suffix = (
            source.suffix
            if mode == "original" or item["kind"] == "video"
            else {"JPEG": ".jpg", "PNG": ".png", "TIFF": ".tif"}[fmt]
        )
        dest = folder / f"{item['created'][:10]}_{item['eye']}_{item['id'][:12]}_{mode}{suffix}"
        if mode == "original" or item["kind"] == "video":
            shutil.copy2(source, dest)
        else:
            image = render(source, item["edits"], item["annotations"] if mode == "annotated" else [])
            from PIL import ImageCms

            options = {"icc_profile": ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()}
            if fmt == "JPEG":
                options.update(quality=95, subsampling=0)
            image.save(dest, format=fmt, **options)
        with catalog.transaction():
            catalog.audit("export.prepared", mid, {"mode": mode, "file": str(dest.relative_to(catalog.root))})
        return dest


def copy_export(source: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    dest = destination / source.name
    if dest.exists():
        dest = dest.with_name(f"{dest.stem}_{uid()[:8]}{dest.suffix}")
    with source.open("rb") as src, dest.open("xb") as out:
        shutil.copyfileobj(src, out)
    return dest
