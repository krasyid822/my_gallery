"""
preview.py - High-fidelity in-terminal image rendering using Rich TrueColor half-blocks,
plus video frame extraction and metadata inspection.
"""

import os
import shutil
import subprocess
import tempfile
from typing import Optional, Tuple, Union
from PIL import Image, ImageOps
from rich.text import Text
from rich.style import Style
from rich.color import Color


def get_image_dimensions(image_path: str) -> Optional[Tuple[int, int]]:
    """Returns (width, height) of an image without loading the full bitmap into memory."""
    try:
        with Image.open(image_path) as img:
            return img.size
    except Exception:
        return None


def get_video_dimensions_and_duration(video_path: str) -> Tuple[Optional[str], Optional[str]]:
    """Tries to extract resolution and duration of a video using ffprobe if available."""
    if not shutil.which("ffprobe"):
        return None, None
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration",
            "-of", "csv=s=x:p=0",
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split("x")
            if len(parts) >= 2:
                w, h = parts[0], parts[1]
                duration_str = f"{float(parts[2]):.1f}s" if len(parts) > 2 and parts[2] else None
                return f"{w}x{h}", duration_str
    except Exception:
        pass
    return None, None


def extract_video_thumbnail(video_path: str, output_path: str) -> bool:
    """Extracts a single frame from the video at 1.0s or 0.0s using ffmpeg."""
    if not shutil.which("ffmpeg"):
        return False
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-ss", "00:00:01",
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=3)
        return result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception:
        return False


def render_image_to_rich(
    image_path: str,
    max_width: int = 38,
    max_height: int = 16
) -> Text:
    """
    Renders an image into a Rich `Text` object using 24-bit TrueColor half-blocks ('▀').
    Each character cell represents 2 vertical pixels (top pixel: foreground, bottom pixel: background).
    """
    try:
        with Image.open(image_path) as img:
            # Handle orientation from EXIF if present
            try:
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass

            img = img.convert("RGB")
            orig_w, orig_h = img.size

            if orig_w == 0 or orig_h == 0:
                return Text("[Error: Gambar kosong]", style="bold red")

            # Target pixel height is twice the character height
            target_pixel_h = max(2, max_height * 2)
            target_pixel_w = max(2, max_width)

            # Preserve aspect ratio (terminal character cell aspect ratio is ~1:2)
            aspect = (orig_w / orig_h) * 2.0

            if (target_pixel_w / target_pixel_h) > aspect:
                calc_w = int(target_pixel_h * aspect)
                calc_h = target_pixel_h
            else:
                calc_w = target_pixel_w
                calc_h = int(target_pixel_w / aspect)

            calc_w = max(2, min(calc_w, target_pixel_w))
            calc_h = max(2, min(calc_h, target_pixel_h))
            if calc_h % 2 != 0:
                calc_h += 1

            img = img.resize((calc_w, calc_h), Image.Resampling.BILINEAR)
            pixels = img.load()

            rich_text = Text()

            for y in range(0, calc_h, 2):
                for x in range(calc_w):
                    r_top, g_top, b_top = pixels[x, y]
                    if y + 1 < calc_h:
                        r_bot, g_bot, b_bot = pixels[x, y + 1]
                    else:
                        r_bot, g_bot, b_bot = 0, 0, 0

                    style = Style(
                        color=Color.from_rgb(r_top, g_top, b_top),
                        bgcolor=Color.from_rgb(r_bot, g_bot, b_bot)
                    )
                    rich_text.append("▀", style=style)
                
                if y + 2 < calc_h:
                    rich_text.append("\n")

            return rich_text

    except Exception as e:
        return Text(f"[Gagal memuat preview: {e}]", style="dim red")


def get_media_preview_rich(
    item_path: str,
    media_type: str,
    max_width: int = 38,
    max_height: int = 16
) -> Text:
    """Generates Rich Text preview for an image or video."""
    if media_type == "image":
        return render_image_to_rich(item_path, max_width, max_height)
    
    elif media_type == "video":
        # Check if ffmpeg can extract a frame
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            if extract_video_thumbnail(item_path, tmp_path):
                rendered = render_image_to_rich(tmp_path, max_width, max_height)
                return rendered
            else:
                # Fallback banner for video
                filename = os.path.basename(item_path)
                if len(filename) > 32:
                    filename = filename[:29] + "..."
                
                banner = Text()
                banner.append("\n🎬 ══════════════════════════════════════ 🎬\n", style="bold cyan")
                banner.append("               [ FILE VIDEO ]               \n", style="bold yellow")
                banner.append(f"     {filename:^34}\n", style="bold white")
                banner.append("  ══════════════════════════════════════════  \n", style="bold cyan")
                banner.append("  Tekan [Enter] atau 'o' untuk memutar video \n", style="dim green")
                banner.append("  di pemutar media default sistem.           \n", style="dim green")
                return banner
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    return Text("[Format media tidak didukung]", style="italic red")
