"""Generate the app icon (multi-size .ico) for the desktop client.

Draws a rounded blue tile with the character 交 centered; no network or
third-party assets required beyond Pillow, which is already installed.
"""
import os
from PIL import Image, ImageDraw, ImageFont

OUT = r"E:\sjtu-client\app.ico"
BASE = 256
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
]


def load_font(size):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


img = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Tile with a subtle vertical gradient so it does not look flat at large sizes.
for y in range(8, BASE - 8):
    t = (y - 8) / (BASE - 16)
    r = int(58 + (32 - 58) * t)
    g = int(116 + (78 - 116) * t)
    b = int(214 + (168 - 214) * t)
    draw.line([(8, y), (BASE - 8, y)], fill=(r, g, b, 255))

# Re-apply the rounded corners by masking the gradient square.
mask = Image.new("L", (BASE, BASE), 0)
ImageDraw.Draw(mask).rounded_rectangle([8, 8, BASE - 8, BASE - 8], radius=54, fill=255)
img.putalpha(mask)

font = load_font(150)
text = "交"
bbox = draw.textbbox((0, 0), text, font=font)
w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
draw.text(((BASE - w) / 2 - bbox[0], (BASE - h) / 2 - bbox[1] - 6),
          text, font=font, fill=(255, 255, 255, 255))

img.save(OUT, format="ICO", sizes=SIZES)
print("saved", OUT, os.path.getsize(OUT), "bytes")
