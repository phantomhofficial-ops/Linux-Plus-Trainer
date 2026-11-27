"""Generate PNG, ICO, and ICNS app icons from the Linux+ Trainer visual design."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


def render_icon_image(size: int = 256) -> Image.Image:
    """Render a crisp RGBA app icon at the requested square resolution."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size / 256.0

    # Rounded outer terminal frame
    pad = int(round(12 * s))
    radius = int(round(34 * s))
    stroke = max(2, int(round(6 * s)))
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=radius,
        fill=(9, 14, 26, 255),
        outline=(0, 240, 255, 255),
        width=stroke,
    )

    # Title bar
    bar_x0, bar_y0 = int(round(26 * s)), int(round(26 * s))
    bar_x1, bar_y1 = int(round(230 * s)), int(round(60 * s))
    draw.rounded_rectangle(
        [bar_x0, bar_y0, bar_x1, bar_y1],
        radius=max(3, int(round(10 * s))),
        fill=(17, 27, 49, 255),
        outline=(0, 140, 160, 255),
        width=max(1, int(round(2 * s))),
    )

    # Window dots
    for cx, color in (
        (46, (255, 42, 157, 255)),
        (66, (250, 204, 21, 255)),
        (86, (34, 197, 94, 255)),
    ):
        r = max(2, int(round(6 * s)))
        px, py = int(round(cx * s)), int(round(43 * s))
        draw.ellipse([px - r, py - r, px + r, py + r], fill=color)

    # Prompt chevron `>`
    chev_w = max(3, int(round(14 * s)))
    draw.line(
        [
            (int(round(54 * s)), int(round(108 * s))),
            (int(round(98 * s)), int(round(138 * s))),
            (int(round(54 * s)), int(round(168 * s))),
        ],
        fill=(0, 240, 255, 255),
        width=chev_w,
        joint="curve",
    )

    # Cursor underscore `_`
    draw.rounded_rectangle(
        [int(round(114 * s)), int(round(160 * s)), int(round(180 * s)), int(round(174 * s))],
        radius=max(1, int(round(4 * s))),
        fill=(250, 204, 21, 255),
    )

    # Bottom accent bar
    draw.rounded_rectangle(
        [int(round(44 * s)), int(round(202 * s)), int(round(212 * s)), int(round(212 * s))],
        radius=max(1, int(round(5 * s))),
        fill=(255, 0, 127, 255),
    )

    # XK0 label in header
    try:
        font = ImageFont.load_default()
        draw.text((int(round(174 * s)), int(round(36 * s))), "XK0", fill=(250, 204, 21, 255), font=font)
    except Exception:
        pass

    return img


def generate_all_icons(output_dir: Path = ASSETS_DIR) -> dict[str, Path]:
    """Write PNG, ICO, and ICNS files into output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    base_img = render_icon_image(512)

    png_path = output_dir / "linux-plus-trainer.png"
    base_img.resize((256, 256), Image.Resampling.LANCZOS).save(png_path, format="PNG")

    ico_path = output_dir / "linux-plus-trainer.ico"
    base_img.save(
        ico_path,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    icns_path = output_dir / "linux-plus-trainer.icns"
    iconutil = shutil.which("iconutil") if sys.platform == "darwin" else None
    if iconutil:
        with tempfile.TemporaryDirectory() as tmpdir:
            iconset = Path(tmpdir) / "linux-plus-trainer.iconset"
            iconset.mkdir()
            for sz in (16, 32, 64, 128, 256, 512):
                resized = base_img.resize((sz, sz), Image.Resampling.LANCZOS)
                resized.save(iconset / f"icon_{sz}x{sz}.png", format="PNG")
                if sz <= 256:
                    dbl = base_img.resize((sz * 2, sz * 2), Image.Resampling.LANCZOS)
                    dbl.save(iconset / f"icon_{sz}x{sz}@2x.png", format="PNG")
            subprocess.run(
                [iconutil, "-c", "icns", str(iconset), "-o", str(icns_path)],
                check=True,
            )
    else:
        base_img.save(icns_path, format="ICNS")

    return {"png": png_path, "ico": ico_path, "icns": icns_path}


if __name__ == "__main__":
    generated = generate_all_icons()
    for kind, path in generated.items():
        print(f"Generated {kind}: {path}")
