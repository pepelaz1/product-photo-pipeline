"""Batch preparation of catalogue photos from a CSV file."""

from __future__ import annotations

import argparse
import csv
import ftplib
import io
import os
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from PIL import Image, ImageChops, ImageFilter


def load_image(source: str, base_dir: Path) -> Image.Image:
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        request = Request(source, headers={"User-Agent": "CatalogPhotoPipeline/1.0"})
        with urlopen(request, timeout=20) as response:
            data = response.read(20_000_001)
        if len(data) > 20_000_000:
            raise ValueError("Image exceeds the 20 MB limit")
        return Image.open(io.BytesIO(data)).convert("RGB")
    if parsed.scheme:
        raise ValueError("Only HTTP(S) URLs or local paths are supported")
    return Image.open(base_dir / source).convert("RGB")


def prepare(image: Image.Image, size: int = 900) -> tuple[Image.Image | None, str, str]:
    """Remove a nearly uniform edge background and return (image, decision, reason)."""
    image.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
    w, h = image.size
    if w < 40 or h < 40:
        return None, "review", "Image is too small"

    # The border is expected to contain background, including light gray.
    border = [image.getpixel((x, y)) for x in range(0, w, max(1, w // 60)) for y in (0, h - 1)]
    border += [image.getpixel((x, y)) for y in range(0, h, max(1, h // 60)) for x in (0, w - 1)]
    centers = tuple(sorted(pixel[c] for pixel in border)[len(border) // 2] for c in range(3))
    distances = sorted(max(abs(pixel[c] - centers[c]) for c in range(3)) for pixel in border)
    if distances[int(len(distances) * .9)] > 28:
        return None, "review", "Border background is not uniform"

    # A conservative color threshold keeps anti-aliased product edges intact.
    background = Image.new("RGB", image.size, centers)
    diff = ImageChops.difference(image, background).convert("L")
    mask = diff.point(lambda value: 255 if value >= 42 else 0)
    bounds = mask.getbbox()
    if bounds is None:
        return None, "review", "No foreground detected"
    left, top, right, bottom = bounds
    area = (right - left) * (bottom - top) / (w * h)
    if area < .03 or area > .85 or left == 0 or top == 0 or right == w or bottom == h:
        return None, "review", "Foreground touches border or occupies an unusual area"

    padding = max(8, int(max(right - left, bottom - top) * .08))
    box = (max(0, left - padding), max(0, top - padding), min(w, right + padding), min(h, bottom + padding))
    cropped = image.crop(box)
    alpha = mask.crop(box).filter(ImageFilter.GaussianBlur(.7))
    white = Image.new("RGB", cropped.size, "white")
    white.paste(cropped, (0, 0), alpha)
    white.thumbnail((size - 80, size - 80), Image.Resampling.LANCZOS)
    result = Image.new("RGB", (size, size), "white")
    result.paste(white, ((size - white.width) // 2, (size - white.height) // 2))
    return result, "ready", "Uniform background removed"


def upload_ftp(path: Path, name: str, args: argparse.Namespace) -> str:
    username = os.environ.get(args.ftp_user_env)
    password = os.environ.get(args.ftp_password_env)
    if not username or not password:
        raise ValueError("FTP credentials are missing from environment variables")
    with ftplib.FTP(args.ftp_host, timeout=30) as ftp:
        ftp.login(username, password)
        if args.ftp_dir:
            ftp.cwd(args.ftp_dir)
        with path.open("rb") as stream:
            ftp.storbinary(f"STOR {name}", stream)
    return f"{args.public_base_url.rstrip('/')}/{quote(name)}"


def run(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    with args.input.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or "image_url" not in reader.fieldnames:
            raise ValueError("CSV must have an image_url column")
        fields = list(reader.fieldnames) + ["processed_url", "status", "note"]
        for number, row in enumerate(reader, 1):
            source = (row.get("image_url") or "").strip()
            name = f"photo_{number:04d}.jpg"
            try:
                image = load_image(source, args.input.parent)
                processed, status, note = prepare(image, args.size)
                url = ""
                if processed is not None:
                    destination = output / name
                    processed.save(destination, "JPEG", quality=92, optimize=True)
                    url = str(destination)
                    if args.upload:
                        url = upload_ftp(destination, name, args)
                row.update(processed_url=url, status=status, note=note)
            except Exception as exc:
                row.update(processed_url="", status="error", note=str(exc))
            rows.append(row)
            print(f"{number}: {row['status']} — {source} ({row['note']})")

    with (output / "result.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Report: {output / 'result.csv'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare product photos and add a second URL column to CSV")
    parser.add_argument("input", type=Path, help="CSV with image_url column")
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--size", type=int, default=900)
    parser.add_argument("--upload", action="store_true", help="Explicitly enable FTP upload")
    parser.add_argument("--ftp-host")
    parser.add_argument("--ftp-dir", default="")
    parser.add_argument("--ftp-user-env", default="PHOTO_FTP_USER")
    parser.add_argument("--ftp-password-env", default="PHOTO_FTP_PASSWORD")
    parser.add_argument("--public-base-url")
    args = parser.parse_args()
    if args.size < 200 or args.size > 3000:
        parser.error("--size must be between 200 and 3000")
    if args.upload and (not args.ftp_host or not args.public_base_url):
        parser.error("--upload requires --ftp-host and --public-base-url")
    run(args)


if __name__ == "__main__":
    main()
