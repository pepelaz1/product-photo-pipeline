"""Create original synthetic product images for the public demo."""

import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


root = Path(__file__).parent
folder = root / "demo"
folder.mkdir(exist_ok=True)

for name, background in [("gray", "#d5d5d5"), ("white", "#ffffff"), ("busy", "#d9e7ee")]:
    image = Image.new("RGB", (700, 520), background)
    draw = ImageDraw.Draw(image)
    if name == "busy":
        for x in range(0, 700, 45):
            draw.rectangle((x, 0, x + 22, 520), fill="#b8cdda")
    draw.ellipse((225, 90, 475, 340), fill="#2e394b", outline="#111827", width=8)
    draw.rectangle((320, 330, 380, 440), fill="#536278", outline="#111827", width=7)
    draw.rectangle((277, 150, 423, 195), fill="#8796ab")
    image.save(folder / f"product_{name}.jpg", quality=95)

with (folder / "catalog.csv").open("w", newline="", encoding="utf-8-sig") as stream:
    writer = csv.writer(stream)
    writer.writerow(["sku", "image_url"])
    for name in ("gray", "white", "busy"):
        writer.writerow([f"DEMO-{name.upper()}", f"product_{name}.jpg"])

# A simple visual sample that renders directly on GitHub.
preview = Image.new("RGB", (1200, 560), "#f5f7fa")
draw = ImageDraw.Draw(preview)
for index, name in enumerate(("gray", "white", "busy")):
    image = Image.open(folder / f"product_{name}.jpg")
    image.thumbnail((360, 360))
    x = 25 + index * 395
    preview.paste(image, (x, 75))
    draw.text((x, 25), f"Input: {name}", fill="#1b2a3a")
    draw.text((x, 455), "auto" if name != "busy" else "manual review", fill="#1b2a3a")
preview.save(root / "preview.jpg", quality=90)
