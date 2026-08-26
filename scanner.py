"""
scanner.py - Fast disk scanning and metadata extraction for images and videos.
"""

from dataclasses import dataclass, field
import os
from pathlib import Path
import time
from typing import Callable, Generator, List, Optional, Set, Tuple

# Supported media extensions
IMAGE_EXTENSIONS: Set[str] = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", 
    ".svg", ".tiff", ".tif", ".ico", ".heic", ".heif", 
    ".avif", ".raw", ".cr2", ".nef", ".arw", ".dng"
}

VIDEO_EXTENSIONS: Set[str] = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", 
    ".webm", ".m4v", ".3gp", ".mts", ".m2ts", 
    ".vob", ".ogv", ".rmvb"
}

# Directories to skip by default to prevent slowdowns and scanning binary/toolchain caches
DEFAULT_IGNORED_DIRS: Set[str] = {
    "node_modules", ".git", ".cache", ".venv", "venv", 
    "__pycache__", ".local", "proc", "sys", "dev", "run", 
    ".npm", ".cargo", ".rustup", "snap", ".idea", ".vscode", 
    "build", "dist", ".gradle", "AndroidSDK", "Android", 
    ".pub-cache", ".config", ".platformio", ".var", "flatpak"
}


@dataclass
class MediaItem:
    path: str
    filename: str
    extension: str
    media_type: str  # "image" or "video"
    size_bytes: int
    modified_time: float
    dimensions: Optional[Tuple[int, int]] = None
    width: Optional[int] = None
    height: Optional[int] = None

    @property
    def formatted_size(self) -> str:
        size = float(self.size_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0 or unit == "TB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024.0
        return f"{size:.1f} GB"

    @property
    def formatted_date(self) -> str:
        try:
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.modified_time))
        except Exception:
            return "Unknown"

    @property
    def date_day(self) -> str:
        try:
            return time.strftime("%Y-%m-%d", time.localtime(self.modified_time))
        except Exception:
            return "Unknown"

    @property
    def date_month(self) -> str:
        try:
            return time.strftime("%Y-%m", time.localtime(self.modified_time))
        except Exception:
            return "Unknown"

    @property
    def date_year(self) -> str:
        try:
            return time.strftime("%Y", time.localtime(self.modified_time))
        except Exception:
            return "Unknown"

    @property
    def resolution_str(self) -> str:
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return "N/A"


@dataclass
class ScanStats:
    total_files_scanned: int = 0
    total_media_count: int = 0
    image_count: int = 0
    video_count: int = 0
    total_size_bytes: int = 0
    image_size_bytes: int = 0
    video_size_bytes: int = 0
    start_time: float = 0.0
    elapsed_seconds: float = 0.0
    current_directory: str = ""
    is_scanning: bool = False
    is_cancelled: bool = False

    @property
    def formatted_total_size(self) -> str:
        size = float(self.total_size_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0 or unit == "TB":
                return f"{size:.2f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024.0
        return f"{size:.2f} GB"

    @property
    def scan_speed(self) -> str:
        if self.elapsed_seconds > 0:
            speed = self.total_files_scanned / self.elapsed_seconds
            return f"{speed:.0f} files/s"
        return "0 files/s"


class MediaScanner:
    def __init__(
        self,
        root_path: str = os.path.expanduser("~"),
        ignored_dirs: Optional[Set[str]] = None,
        custom_extensions: Optional[Set[str]] = None,
    ):
        self.root_path = os.path.abspath(root_path)
        self.ignored_dirs = ignored_dirs if ignored_dirs is not None else DEFAULT_IGNORED_DIRS
        self.custom_extensions = custom_extensions
        self.is_cancelled = False
        self.seen_realpaths: Set[str] = set()

    def cancel(self):
        self.is_cancelled = True

    def scan(
        self,
        progress_callback: Optional[Callable[[ScanStats, Optional[MediaItem]], None]] = None,
    ) -> Generator[MediaItem, None, ScanStats]:
        """
        Recursively scans root_path for images and videos, yielding found MediaItems.
        Periodically triggers progress_callback with updated statistics.
        """
        self.is_cancelled = False
        self.seen_realpaths.clear()
        stats = ScanStats(
            start_time=time.time(),
            is_scanning=True,
            current_directory=self.root_path
        )

        last_callback_time = time.time()

        for dirpath, dirnames, filenames in os.walk(self.root_path, topdown=True, followlinks=False):
            if self.is_cancelled:
                stats.is_cancelled = True
                break

            # Filter out ignored directories in-place
            dirnames[:] = [
                d for d in dirnames
                if d not in self.ignored_dirs 
                and not d.startswith(".")
                and not any(part in self.ignored_dirs for part in Path(os.path.join(dirpath, d)).parts)
            ]

            stats.current_directory = dirpath
            stats.elapsed_seconds = time.time() - stats.start_time

            for filename in filenames:
                if self.is_cancelled:
                    stats.is_cancelled = True
                    break

                if filename.startswith("."):
                    continue

                stats.total_files_scanned += 1
                _, ext = os.path.splitext(filename)
                ext_lower = ext.lower()

                media_type = None
                if ext_lower in IMAGE_EXTENSIONS:
                    media_type = "image"
                elif ext_lower in VIDEO_EXTENSIONS:
                    media_type = "video"

                if media_type:
                    file_path = os.path.join(dirpath, filename)
                    try:
                        # Avoid duplicates from symlinks / aliases
                        real_p = os.path.realpath(file_path)
                        if real_p in self.seen_realpaths:
                            continue
                        self.seen_realpaths.add(real_p)

                        file_stat = os.stat(file_path)
                        size_bytes = file_stat.st_size
                        modified_time = file_stat.st_mtime

                        item = MediaItem(
                            path=file_path,
                            filename=filename,
                            extension=ext_lower,
                            media_type=media_type,
                            size_bytes=size_bytes,
                            modified_time=modified_time,
                        )

                        stats.total_media_count += 1
                        stats.total_size_bytes += size_bytes
                        if media_type == "image":
                            stats.image_count += 1
                            stats.image_size_bytes += size_bytes
                        else:
                            stats.video_count += 1
                            stats.video_size_bytes += size_bytes

                        if progress_callback:
                            progress_callback(stats, item)

                        yield item

                    except (OSError, PermissionError):
                        continue

                # Periodic progress callback
                now = time.time()
                if progress_callback and (now - last_callback_time >= 0.1):
                    stats.elapsed_seconds = now - stats.start_time
                    progress_callback(stats, None)
                    last_callback_time = now

        stats.is_scanning = False
        stats.elapsed_seconds = time.time() - stats.start_time
        if progress_callback:
            progress_callback(stats, None)

        return stats
