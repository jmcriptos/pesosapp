"""Generate iOS PWA startup images (splash screens).

iOS only honors `apple-touch-startup-image` <link> tags whose `media`
query matches the device's exact dimensions and pixel ratio. So we
need one PNG per supported iPhone resolution.

Run with:

    /tmp/pesos_venv/bin/python3 scripts/generate_ios_splash.py

Outputs PNGs to static/icons/splash/ and prints the matching <link>
tags for base.html.
"""

from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE_ICON = ROOT / "static" / "icons" / "icon-512.png"
OUT_DIR = ROOT / "static" / "icons" / "splash"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Background color must match manifest.background_color so the splash
# blends with the loading overlay's dark theme.
BG = (15, 23, 42)  # #0f172a

# Each entry: (portrait_width, portrait_height, css_device_width,
# css_device_height, device_pixel_ratio, label)
# CSS dimensions = physical pixels / device-pixel-ratio.
DEVICES = [
    # iPhone 16 Pro Max
    (1320, 2868, 440, 956, 3, "iphone-16-pro-max"),
    # iPhone 14 Pro Max / 15 Plus / 15 Pro Max / 16 Plus
    (1290, 2796, 430, 932, 3, "iphone-14-pro-max"),
    # iPhone 14 Pro / 15 / 15 Pro / 16 / 16 Pro
    (1179, 2556, 393, 852, 3, "iphone-14-pro"),
    # iPhone 12 Pro Max / 13 Pro Max / 14 Plus
    (1284, 2778, 428, 926, 3, "iphone-12-pro-max"),
    # iPhone 12 / 12 Pro / 13 / 13 Pro / 14
    (1170, 2532, 390, 844, 3, "iphone-12"),
    # iPhone XS Max / 11 Pro Max
    (1242, 2688, 414, 896, 3, "iphone-xs-max"),
    # iPhone X / XS / 11 Pro / 12 mini / 13 mini
    (1125, 2436, 375, 812, 3, "iphone-x"),
    # iPhone XR / 11
    (828, 1792, 414, 896, 2, "iphone-xr"),
    # iPhone 6 Plus / 7 Plus / 8 Plus
    (1242, 2208, 414, 736, 3, "iphone-plus"),
    # iPhone 6 / 7 / 8 / SE 2nd & 3rd
    (750, 1334, 375, 667, 2, "iphone-8"),
    # iPhone 5 / SE 1st gen
    (640, 1136, 320, 568, 2, "iphone-se"),
]


def render_splash(width: int, height: int, label: str) -> Path:
    canvas = Image.new("RGB", (width, height), BG)
    icon = Image.open(SOURCE_ICON).convert("RGBA")

    # Icon target = 28% of the smallest dimension.
    icon_size = int(min(width, height) * 0.28)
    icon = icon.resize((icon_size, icon_size), Image.LANCZOS)

    x = (width - icon_size) // 2
    y = (height - icon_size) // 2
    canvas.paste(icon, (x, y), icon)

    out = OUT_DIR / f"splash-{label}-{width}x{height}.png"
    canvas.save(out, "PNG", optimize=True)
    return out


def render_link_tags() -> str:
    lines = []
    for w, h, css_w, css_h, dpr, label in DEVICES:
        href = f"/static/icons/splash/splash-{label}-{w}x{h}.png"
        media = (
            f"(device-width: {css_w}px) and (device-height: {css_h}px) "
            f"and (-webkit-device-pixel-ratio: {dpr}) and (orientation: portrait)"
        )
        lines.append(
            f'<link rel="apple-touch-startup-image" href="{href}" media="{media}">'
        )
    return "\n".join(lines)


if __name__ == "__main__":
    for w, h, _cw, _ch, _dpr, label in DEVICES:
        path = render_splash(w, h, label)
        print(f"  wrote {path.relative_to(ROOT)}")
    print()
    print("Paste these into base.html <head>:")
    print()
    print(render_link_tags())
