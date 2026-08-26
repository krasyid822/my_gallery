#!/usr/bin/env python3
"""
app.py - Main TUI Application for Disk Media Scanner & Explorer.
Built with Textual, Rich, and Pillow. Read-only inspection & exploration.
"""

import base64
from collections import defaultdict
import csv
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from typing import Dict, List, Optional, Set, Tuple, Union

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Static,
    TabbedContent,
    TabPane,
)
from textual.reactive import reactive

from scanner import MediaItem, MediaScanner, ScanStats
from preview import get_media_preview_rich, get_image_dimensions, get_video_dimensions_and_duration


def copy_text_to_clipboard(text: str) -> bool:
    """Copies text to the system clipboard across Wayland, X11, or terminal OSC 52."""
    if shutil.which("wl-copy"):
        try:
            p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
            p.communicate(text.encode("utf-8"))
            if p.returncode == 0:
                return True
        except Exception:
            pass

    if shutil.which("xclip"):
        try:
            p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
            p.communicate(text.encode("utf-8"))
            if p.returncode == 0:
                return True
        except Exception:
            pass

    if shutil.which("xsel"):
        try:
            p = subprocess.Popen(["xsel", "--clipboard", "--input"], stdin=subprocess.PIPE)
            p.communicate(text.encode("utf-8"))
            if p.returncode == 0:
                return True
        except Exception:
            pass

    # Terminal OSC 52 escape code fallback
    try:
        b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
        sys.stdout.write(f"\033]52;c;{b64}\a")
        sys.stdout.flush()
        return True
    except Exception:
        return False


class SearchInput(Input):
    """Custom input widget with explicit contrast and instant Escape/Down/Enter navigation."""

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            try:
                self.screen.query_one("#media-table", DataTable).focus()
                self.app.notify("Keluar dari pencarian (fokus ke tabel media)")
            except Exception:
                pass
            event.stop()
        elif event.key == "down":
            try:
                self.screen.query_one("#media-table", DataTable).focus()
            except Exception:
                pass
            event.stop()


class PathPromptModal(ModalScreen[Optional[str]]):
    """Modal dialog for selecting a custom scan path."""

    DEFAULT_CSS = """
    PathPromptModal {
        align: center middle;
    }
    #dialog {
        padding: 1 2;
        width: 65;
        height: auto;
        border: thick $accent;
        background: $surface;
    }
    #dialog-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    #path-input {
        margin-bottom: 1;
        background: #1e293b;
        color: #ffffff;
    }
    #buttons {
        align: right middle;
    }
    """

    def __init__(self, current_path: str):
        super().__init__()
        self.current_path = current_path

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("📁 Pilih Direktori Pemindaian Disk", id="dialog-title")
            yield Label("Masukkan path folder yang ingin dipindai:")
            yield Input(value=self.current_path, id="path-input", placeholder="/home/user...")
            with Horizontal(id="buttons"):
                yield Button("Batal", variant="default", id="btn-cancel")
                yield Button("Mulai Pindai", variant="primary", id="btn-start")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-start":
            input_widget = self.query_one("#path-input", Input)
            val = input_widget.value.strip()
            if val and os.path.exists(os.path.expanduser(val)):
                self.dismiss(os.path.abspath(os.path.expanduser(val)))
            else:
                self.notify("Path tidak valid atau tidak ditemukan!", severity="error")
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        val = event.value.strip()
        if val and os.path.exists(os.path.expanduser(val)):
            self.dismiss(os.path.abspath(os.path.expanduser(val)))
        else:
            self.notify("Path tidak valid atau tidak ditemukan!", severity="error")


class PreviewPane(VerticalScroll):
    """Panel displaying the media thumbnail preview, metadata details, and vertically stacked action buttons."""

    def __init__(self):
        super().__init__(id="preview-pane")
        self.current_item: Optional[MediaItem] = None

    def compose(self) -> ComposeResult:
        yield Label("📷 PREVIEW & INFO", id="preview-heading")
        yield Static("Pilih file dari tabel untuk melihat preview...", id="preview-art")
        yield Static("", id="preview-details")
        with Vertical(id="preview-actions"):
            yield Button("▶ Buka File (o)", id="btn-open-file", variant="success")
            yield Button("📋 Salin Path (y)", id="btn-copy-path", variant="primary")
            yield Button("📂 Buka Folder (f)", id="btn-open-folder", variant="default")

    def update_item(self, item: Optional[MediaItem]):
        self.current_item = item
        art_widget = self.query_one("#preview-art", Static)
        details_widget = self.query_one("#preview-details", Static)

        if not item:
            art_widget.update("Pilih file media untuk melihat preview...")
            details_widget.update("")
            return

        # Render preview using Rich TrueColor Text object
        preview_text = get_media_preview_rich(item.path, item.media_type, max_width=30, max_height=12)
        art_widget.update(preview_text)

        # Retrieve resolution if not yet cached
        if not item.width:
            if item.media_type == "image":
                dims = get_image_dimensions(item.path)
                if dims:
                    item.width, item.height = dims
            elif item.media_type == "video":
                res, _ = get_video_dimensions_and_duration(item.path)
                if res and "x" in res:
                    parts = res.split("x")
                    try:
                        item.width, item.height = int(parts[0]), int(parts[1])
                    except Exception:
                        pass

        # Build metadata display
        details_text = (
            f"[bold cyan]Nama:[/bold cyan] {item.filename}\n"
            f"[bold cyan]Tipe:[/bold cyan] {'📸 Gambar' if item.media_type == 'image' else '🎥 Video'} ({item.extension})\n"
            f"[bold cyan]Ukuran:[/bold cyan] {item.formatted_size}\n"
            f"[bold cyan]Resolusi:[/bold cyan] {item.resolution_str}\n"
            f"[bold cyan]Tanggal:[/bold cyan] {item.formatted_date}\n"
            f"[bold cyan]Lokasi:[/bold cyan] [dim]{item.path}[/dim]"
        )
        details_widget.update(details_text)

    def show_header_info(self, group_key: str, count: int, size_str: str, is_collapsed: bool):
        art_widget = self.query_one("#preview-art", Static)
        details_widget = self.query_one("#preview-details", Static)
        status_str = "Tertutup (Collapsed)" if is_collapsed else "Terbuka (Expanded)"
        
        banner = Text()
        banner.append("\n📁 ══════════════════════════════════ 📁\n", style="bold yellow")
        banner.append("         [ KELOMPOK TANGGAL ]          \n", style="bold cyan")
        banner.append(f"   📅 {group_key:^26}   \n", style="bold white")
        banner.append("  ════════════════════════════════════  \n", style="bold yellow")
        banner.append("  Tekan [Spasi] untuk toggle grup.     \n", style="dim green")
        banner.append("  Tekan [c] Tutup / [x] Buka Semua.    \n", style="dim green")
        
        art_widget.update(banner)
        details_text = (
            f"[bold yellow]Periode:[/bold yellow] 📅 {group_key}\n"
            f"[bold yellow]Status:[/bold yellow] {status_str}\n"
            f"[bold yellow]Total Media:[/bold yellow] {count} file\n"
            f"[bold yellow]Total Ukuran:[/bold yellow] {size_str}\n\n"
            f"[dim]Pintasan:\n"
            f"• [bold]Spasi[/bold] : Buka / Tutup grup ini\n"
            f"• [bold]y[/bold] : Salin path (saat memilih file)\n"
            f"• [bold]c[/bold] : Tutup Semua (Collapse All)\n"
            f"• [bold]x[/bold] : Buka Semua (Expand All)[/dim]"
        )
        details_widget.update(details_text)


class MediaScanApp(App):
    """Main Textual Application for Media Scanning."""

    TITLE = "MediaScan TUI"
    SUB_TITLE = "Disk Image & Video Explorer"

    CSS = """
    Screen {
        background: $surface-darken-1;
    }

    #controls-container {
        dock: top;
        height: auto;
        background: $surface;
        padding: 0 1;
        border-bottom: solid $accent;
    }

    #search-row {
        height: 3;
        align: left middle;
        margin-bottom: 0;
    }

    #search-box {
        width: 1fr;
        background: #0f172a;
        color: #38bdf8;
        border: solid #0284c7;
        margin-right: 1;
    }

    #search-box:focus {
        background: #020617;
        color: #ffffff;
        border: double #38bdf8;
    }

    #filter-row {
        height: auto;
        min-height: 3;
        align: left middle;
        padding-bottom: 0;
    }

    .btn-compact {
        min-width: 7;
        height: 3;
        margin-right: 1;
        margin-bottom: 0;
        padding: 0 1;
    }

    .bar-sep {
        color: $accent;
        margin: 0 1;
    }

    #main-container {
        height: 1fr;
    }

    #table-container {
        width: 1fr;
        min-width: 35;
        height: 100%;
        border-right: solid $accent;
    }

    #preview-pane {
        width: 36;
        min-width: 28;
        max-width: 40;
        height: 100%;
        padding: 0 1;
        background: $surface;
        overflow-x: hidden;
        overflow-y: auto;
    }

    #preview-heading {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
        border-bottom: solid $accent;
    }

    #preview-art {
        height: auto;
        min-height: 13;
        margin-bottom: 1;
        content-align: center middle;
    }

    #preview-details {
        margin-top: 1;
        margin-bottom: 1;
    }

    #preview-actions {
        height: auto;
        margin-top: 1;
        margin-bottom: 1;
    }

    #preview-actions Button {
        width: 100%;
        height: 3;
        margin-bottom: 1;
    }

    #status-bar {
        dock: bottom;
        height: 2;
        background: $surface-lighten-1;
        color: $text;
        padding: 0 1;
        align: left middle;
    }

    #stats-cards {
        height: auto;
        margin: 1 1;
    }

    .stat-card {
        border: solid $accent;
        padding: 1 2;
        width: 1fr;
        margin-right: 1;
        background: $surface;
    }

    .stat-card-title {
        color: $text-muted;
        text-style: bold;
    }

    .stat-card-value {
        color: $accent;
        text-style: bold;
    }

    #largest-files-table, #timeline-table {
        margin: 1 1;
        height: 14;
    }

    #settings-container {
        padding: 1 2;
        width: 80;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Keluar", show=True),
        Binding("y", "copy_selected_path", "Salin Path (y)", show=True),
        Binding("p", "copy_selected_path", "Salin Path", show=False),
        Binding("c", "collapse_all", "Collapse (c)", show=True),
        Binding("x", "expand_all", "Expand (x)", show=True),
        Binding("space", "toggle_current_group", "Toggle (Spasi)", show=True),
        Binding("g", "cycle_grouping", "Grup (g)", show=True),
        Binding("t", "toggle_sort_order", "Urutan (t)", show=True),
        Binding("o", "open_selected_media", "Buka (o)", show=True),
        Binding("enter", "handle_enter_press", "Buka / Toggle", show=False),
        Binding("f", "open_selected_folder", "Folder (f)", show=True),
        Binding("s", "prompt_scan_path", "Pindai Path", show=True),
        Binding("r", "rescan", "Pindai Ulang", show=True),
        Binding("e", "export_data", "Ekspor", show=True),
        Binding("slash", "focus_search", "Cari (/)", show=True),
        Binding("escape", "cancel_search_focus", "Escape", show=False),
    ]

    scan_path = reactive(os.path.expanduser("~"))
    active_filter = reactive("all")  # all, image, video, large
    group_by_date = reactive("month")  # none, day, month, year
    sort_newest_first = reactive(True)  # True = newest, False = oldest

    def __init__(self, initial_path: Optional[str] = None):
        super().__init__()
        if initial_path and os.path.exists(initial_path):
            self.scan_path = os.path.abspath(initial_path)
        self.all_items: List[MediaItem] = []
        self.row_data_map: List[Tuple[str, Union[MediaItem, Tuple[str, int, str, bool]]]] = []
        self.collapsed_groups: Set[str] = set()
        self.scanner: Optional[MediaScanner] = None
        self.current_stats: ScanStats = ScanStats()
        self.selected_item: Optional[MediaItem] = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="tab-explorer"):
            with TabPane("📁 Media Explorer", id="tab-explorer"):
                with Vertical(id="controls-container"):
                    with Horizontal(id="search-row"):
                        yield SearchInput(placeholder="🔍 Ketik nama, ekstensi, tgl, path... (Tekan Enter/Esc utk ke tabel)", id="search-box")
                        yield Button("⚡ Pindai", id="btn-scan", variant="warning", classes="btn-compact")
                        yield Button("⬇️ Urutkan", id="btn-sort-order", variant="default", classes="btn-compact")

                    with Horizontal(id="filter-row"):
                        yield Label("Tipe:", classes="bar-label")
                        yield Button("Semua", id="btn-filter-all", variant="primary", classes="btn-compact")
                        yield Button("📸 Foto", id="btn-filter-img", variant="default", classes="btn-compact")
                        yield Button("🎥 Video", id="btn-filter-vid", variant="default", classes="btn-compact")
                        yield Button("🐘 >50M", id="btn-filter-large", variant="default", classes="btn-compact")

                        yield Label("│", classes="bar-sep")
                        yield Label("Grup:", classes="bar-label")
                        yield Button("Off", id="btn-group-none", variant="default", classes="btn-compact")
                        yield Button("Hari", id="btn-group-day", variant="default", classes="btn-compact")
                        yield Button("Bulan", id="btn-group-month", variant="primary", classes="btn-compact")
                        yield Button("Tahun", id="btn-group-year", variant="default", classes="btn-compact")

                        yield Label("│", classes="bar-sep")
                        yield Button("▶ Tutup (c)", id="btn-collapse-all", variant="default", classes="btn-compact")
                        yield Button("▼ Buka (x)", id="btn-expand-all", variant="default", classes="btn-compact")

                with Horizontal(id="main-container"):
                    with Container(id="table-container"):
                        yield DataTable(id="media-table", cursor_type="row")
                    yield PreviewPane()

            with TabPane("📅 Timeline Tanggal", id="tab-timeline"):
                yield Label("\n[bold cyan]📅 Ringkasan Media Berdasarkan Periode Waktu:[/bold cyan] (Pilih baris untuk filter)", classes="ml-2")
                yield DataTable(id="timeline-table", cursor_type="row")

            with TabPane("📊 Statistik & Insights", id="tab-insights"):
                with Horizontal(id="stats-cards"):
                    with Vertical(classes="stat-card"):
                        yield Label("TOTAL MEDIA DITEMUKAN", classes="stat-card-title")
                        yield Label("0", id="stat-total-count", classes="stat-card-value")
                    with Vertical(classes="stat-card"):
                        yield Label("TOTAL UKURAN PENYIMPANAN", classes="stat-card-title")
                        yield Label("0 MB", id="stat-total-size", classes="stat-card-value")
                    with Vertical(classes="stat-card"):
                        yield Label("JUMLAH GAMBAR", classes="stat-card-title")
                        yield Label("0", id="stat-img-count", classes="stat-card-value")
                    with Vertical(classes="stat-card"):
                        yield Label("JUMLAH VIDEO", classes="stat-card-title")
                        yield Label("0", id="stat-vid-count", classes="stat-card-value")

                yield Label("\n[bold]🏆 10 File Media Terbesar di Disk:[/bold]")
                yield DataTable(id="largest-files-table", cursor_type="row")

            with TabPane("⚙️ Pengaturan & Path", id="tab-settings"):
                with Vertical(id="settings-container"):
                    yield Label("[bold]Direktori Pemindaian Saat Ini:[/bold]")
                    yield Label(self.scan_path, id="lbl-current-path")
                    yield Button("Ganti Direktori Pemindaian", id="btn-change-path", variant="primary")
                    yield Label("\n[dim]Tips: MediaScan secara otomatis mengabaikan file sistem, node_modules, cache, dan direktori virtual untuk menjaga kinerja tetap kencang.[/dim]")

        with Horizontal(id="status-bar"):
            yield Label("Siap memindai disk...", id="status-label")
        yield Footer()

    def on_mount(self) -> None:
        """Setup tables and trigger initial scan."""
        # Setup main media table
        table = self.query_one("#media-table", DataTable)
        table.add_column("Tipe / Status", width=14)
        table.add_column("Nama File / Periode", width=30)
        table.add_column("Ukuran", width=12)
        table.add_column("Dimensi", width=10)
        table.add_column("Tanggal Modifikasi", width=20)
        table.add_column("Path Lengkap")

        # Setup timeline table
        timeline_table = self.query_one("#timeline-table", DataTable)
        timeline_table.add_column("Periode Tanggal", width=20)
        timeline_table.add_column("Jumlah Total", width=14)
        timeline_table.add_column("📸 Gambar", width=12)
        timeline_table.add_column("🎥 Video", width=12)
        timeline_table.add_column("Total Ukuran", width=16)

        # Setup largest files table
        largest_table = self.query_one("#largest-files-table", DataTable)
        largest_table.add_column("No", width=5)
        largest_table.add_column("Nama File", width=30)
        largest_table.add_column("Tipe", width=10)
        largest_table.add_column("Ukuran", width=14)
        largest_table.add_column("Path Lengkap")

        # Start initial scan worker
        self.start_scan()

    @work(exclusive=True, thread=True)
    def start_scan(self) -> None:
        """Background scanning worker."""
        self.scanner = MediaScanner(root_path=self.scan_path)
        self.all_items.clear()
        self.call_from_thread(self._clear_ui_for_scan)

        last_update_time = time.time()

        def progress_cb(stats: ScanStats, item: Optional[MediaItem]):
            nonlocal last_update_time
            self.current_stats = stats

            if item:
                self.all_items.append(item)

            now = time.time()
            if (now - last_update_time >= 0.25):
                self.call_from_thread(self._update_status, stats)
                last_update_time = now

        # Run scanner generator
        for _ in self.scanner.scan(progress_callback=progress_cb):
            pass

        self.call_from_thread(self._finish_scan)

    def _clear_ui_for_scan(self) -> None:
        try:
            table = self.query_one("#media-table", DataTable)
            table.clear()
        except Exception:
            pass
        self.row_data_map.clear()
        try:
            status_lbl = self.query_one("#status-label", Label)
            status_lbl.update(f"Memindai direktori: [bold]{self.scan_path}[/bold]...")
        except Exception:
            pass

    def _update_status(self, stats: ScanStats) -> None:
        try:
            status_lbl = self.query_one("#status-label", Label)
            if stats.is_scanning:
                status_lbl.update(
                    f"⚡ Dipindai: [bold]{stats.total_files_scanned}[/bold] files | "
                    f"Media: [bold cyan]{stats.total_media_count}[/bold cyan] ({stats.formatted_total_size}) | "
                    f"Kecepatan: {stats.scan_speed} | "
                    f"[dim]{stats.current_directory[-40:]}[/dim]"
                )
            else:
                status_lbl.update(
                    f"✅ Pemindaian selesai! Total Media: [bold cyan]{stats.total_media_count}[/bold cyan] "
                    f"({stats.formatted_total_size}) dalam {stats.elapsed_seconds:.1f} detik."
                )
        except Exception:
            pass

    def _matches_filter(self, item: MediaItem) -> bool:
        search_query = ""
        try:
            search_query = self.query_one("#search-box", SearchInput).value.strip().lower()
        except Exception:
            pass

        if search_query:
            matched = (
                search_query in item.filename.lower()
                or search_query in item.path.lower()
                or search_query in item.extension.lower()
                or search_query in item.date_day.lower()
                or search_query in item.date_month.lower()
                or search_query in item.date_year.lower()
                or (search_query in ("gambar", "foto", "image") and item.media_type == "image")
                or (search_query in ("video", "vid", "film") and item.media_type == "video")
            )
            if not matched:
                return False

        if self.active_filter == "image" and item.media_type != "image":
            return False
        if self.active_filter == "video" and item.media_type != "video":
            return False
        if self.active_filter == "large" and item.size_bytes < (50 * 1024 * 1024):
            return False

        return True

    def _finish_scan(self) -> None:
        self._refresh_table()
        self._update_insights()
        self._update_timeline()

    def _refresh_table(self, restore_cursor: Optional[int] = None) -> None:
        try:
            table = self.query_one("#media-table", DataTable)
        except Exception:
            return
        table.clear()
        self.row_data_map.clear()

        # Filter items first
        matching_items = [item for item in self.all_items if self._matches_filter(item)]

        # Sort items by date
        matching_items.sort(
            key=lambda x: x.modified_time,
            reverse=self.sort_newest_first
        )

        if self.group_by_date == "none":
            for item in matching_items:
                self.row_data_map.append(("item", item))
                icon = "📸 Foto" if item.media_type == "image" else "🎥 Video"
                try:
                    table.add_row(
                        icon,
                        item.filename,
                        item.formatted_size,
                        item.resolution_str,
                        item.formatted_date,
                        item.path
                    )
                except Exception:
                    pass

        else:
            # Clean direct grouping by Day, Month, or Year
            grouped: Dict[str, List[MediaItem]] = defaultdict(list)
            for item in matching_items:
                if self.group_by_date == "day":
                    key = item.date_day
                elif self.group_by_date == "year":
                    key = item.date_year
                else:  # month
                    key = item.date_month
                grouped[key].append(item)

            for group_key, items in grouped.items():
                total_group_bytes = sum(i.size_bytes for i in items)
                size_str = self._format_bytes(total_group_bytes)
                is_collapsed = group_key in self.collapsed_groups

                if is_collapsed:
                    icon_status = "▶ [TUTUP]"
                    arrow = "▶"
                    hint = f"[dim yellow]({len(items)} media • {size_str}) [Spasi: Buka][/dim yellow]"
                else:
                    icon_status = "▼ [BUKA]"
                    arrow = "▼"
                    hint = f"[bold yellow]({len(items)} media • {size_str})[/bold yellow]"

                header_label = f"{arrow} 📅 {group_key}"
                self.row_data_map.append(("header", (group_key, len(items), size_str, is_collapsed)))

                try:
                    table.add_row(
                        f"[bold cyan]{icon_status}[/bold cyan]",
                        f"[bold yellow]{header_label}[/bold yellow]",
                        f"[bold yellow]{size_str}[/bold yellow]",
                        f"{len(items)} file",
                        f"[dim]{group_key}[/dim]",
                        hint
                    )
                except Exception:
                    pass

                if not is_collapsed:
                    for item in items:
                        self.row_data_map.append(("item", item))
                        icon = "  📸 Foto" if item.media_type == "image" else "  🎥 Video"
                        try:
                            table.add_row(
                                icon,
                                item.filename,
                                item.formatted_size,
                                item.resolution_str,
                                item.formatted_date,
                                item.path
                            )
                        except Exception:
                            pass

        if restore_cursor is not None and len(self.row_data_map) > 0:
            target_row = min(restore_cursor, len(self.row_data_map) - 1)
            try:
                table.move_cursor(row=target_row)
            except Exception:
                pass

    def _format_bytes(self, size_bytes: int) -> str:
        size = float(size_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0 or unit == "TB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024.0
        return f"{size:.1f} GB"

    def _update_insights(self) -> None:
        try:
            self.query_one("#stat-total-count", Label).update(str(len(self.all_items)))
            total_size = sum(item.size_bytes for item in self.all_items)
            self.query_one("#stat-total-size", Label).update(self._format_bytes(total_size))

            img_count = sum(1 for i in self.all_items if i.media_type == "image")
            vid_count = sum(1 for i in self.all_items if i.media_type == "video")
            self.query_one("#stat-img-count", Label).update(str(img_count))
            self.query_one("#stat-vid-count", Label).update(str(vid_count))

            largest_table = self.query_one("#largest-files-table", DataTable)
            largest_table.clear()
            sorted_by_size = sorted(self.all_items, key=lambda x: x.size_bytes, reverse=True)[:10]
            for idx, item in enumerate(sorted_by_size, 1):
                try:
                    largest_table.add_row(
                        str(idx),
                        item.filename,
                        item.media_type.capitalize(),
                        item.formatted_size,
                        item.path
                    )
                except Exception:
                    pass
        except Exception:
            pass

    def _update_timeline(self) -> None:
        try:
            timeline_table = self.query_one("#timeline-table", DataTable)
            timeline_table.clear()

            monthly_data: Dict[str, Dict[str, int]] = defaultdict(lambda: {"count": 0, "img": 0, "vid": 0, "size": 0})
            for item in self.all_items:
                m = item.date_month
                monthly_data[m]["count"] += 1
                if item.media_type == "image":
                    monthly_data[m]["img"] += 1
                else:
                    monthly_data[m]["vid"] += 1
                monthly_data[m]["size"] += item.size_bytes

            sorted_months = sorted(monthly_data.keys(), reverse=True)
            for m in sorted_months:
                d = monthly_data[m]
                timeline_table.add_row(
                    f"📅 {m}",
                    f"{d['count']} media",
                    f"{d['img']} foto",
                    f"{d['vid']} video",
                    self._format_bytes(d["size"])
                )
        except Exception:
            pass

    # Event handlers
    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "media-table":
            self.action_handle_enter_press()
        elif event.data_table.id == "timeline-table":
            row_data = event.data_table.get_row_at(event.cursor_row)
            if row_data and len(row_data) > 0:
                month_str = str(row_data[0]).replace("📅", "").strip()
                search_box = self.query_one("#search-box", SearchInput)
                search_box.value = month_str
                self.query_one(TabbedContent).active = "tab-explorer"

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "media-table":
            row_index = event.cursor_row
            if 0 <= row_index < len(self.row_data_map):
                row_type, data = self.row_data_map[row_index]
                if row_type == "item":
                    self.selected_item = data
                    self.query_one(PreviewPane).update_item(data)
                elif row_type == "header":
                    group_key, count, size_str, is_collapsed = data
                    self.query_one(PreviewPane).show_header_info(group_key, count, size_str, is_collapsed)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-box":
            self._refresh_table()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search-box":
            try:
                self.query_one("#media-table", DataTable).focus()
                self.notify("Pencarian diterapkan (fokus kembali ke tabel)")
            except Exception:
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-filter-all":
            self._set_active_filter("all")
        elif btn_id == "btn-filter-img":
            self._set_active_filter("image")
        elif btn_id == "btn-filter-vid":
            self._set_active_filter("video")
        elif btn_id == "btn-filter-large":
            self._set_active_filter("large")
        elif btn_id == "btn-group-none":
            self._set_group_by("none")
        elif btn_id == "btn-group-day":
            self._set_group_by("day")
        elif btn_id == "btn-group-month":
            self._set_group_by("month")
        elif btn_id == "btn-group-year":
            self._set_group_by("year")
        elif btn_id == "btn-collapse-all":
            self.action_collapse_all()
        elif btn_id == "btn-expand-all":
            self.action_expand_all()
        elif btn_id == "btn-sort-order":
            self.action_toggle_sort_order()
        elif btn_id in ("btn-scan", "btn-change-path"):
            self.action_prompt_scan_path()
        elif btn_id == "btn-open-file":
            self.action_open_selected_media()
        elif btn_id == "btn-copy-path":
            self.action_copy_selected_path()
        elif btn_id == "btn-open-folder":
            self.action_open_selected_folder()

    def _set_active_filter(self, filter_name: str) -> None:
        self.active_filter = filter_name
        self.query_one("#btn-filter-all", Button).variant = "primary" if filter_name == "all" else "default"
        self.query_one("#btn-filter-img", Button).variant = "primary" if filter_name == "image" else "default"
        self.query_one("#btn-filter-vid", Button).variant = "primary" if filter_name == "video" else "default"
        self.query_one("#btn-filter-large", Button).variant = "primary" if filter_name == "large" else "default"
        self._refresh_table()

    def _set_group_by(self, group_name: str) -> None:
        self.group_by_date = group_name
        self.query_one("#btn-group-none", Button).variant = "primary" if group_name == "none" else "default"
        self.query_one("#btn-group-day", Button).variant = "primary" if group_name == "day" else "default"
        self.query_one("#btn-group-month", Button).variant = "primary" if group_name == "month" else "default"
        self.query_one("#btn-group-year", Button).variant = "primary" if group_name == "year" else "default"
        self._refresh_table()

    # Actions
    def action_handle_enter_press(self) -> None:
        table = self.query_one("#media-table", DataTable)
        cursor_row = table.cursor_row
        if 0 <= cursor_row < len(self.row_data_map):
            row_type, data = self.row_data_map[cursor_row]
            if row_type == "header":
                self.action_toggle_current_group()
            elif row_type == "item":
                self.action_open_selected_media()

    def action_toggle_current_group(self) -> None:
        table = self.query_one("#media-table", DataTable)
        cursor_row = table.cursor_row
        if not (0 <= cursor_row < len(self.row_data_map)):
            return

        row_type, data = self.row_data_map[cursor_row]
        group_key_to_toggle = None

        if row_type == "header":
            group_key_to_toggle = data[0]
        elif row_type == "item":
            if self.group_by_date == "day":
                group_key_to_toggle = data.date_day
            elif self.group_by_date == "year":
                group_key_to_toggle = data.date_year
            elif self.group_by_date == "month":
                group_key_to_toggle = data.date_month

        if group_key_to_toggle:
            if group_key_to_toggle in self.collapsed_groups:
                self.collapsed_groups.remove(group_key_to_toggle)
                self.notify(f"Dibuka: 📅 {group_key_to_toggle}")
            else:
                self.collapsed_groups.add(group_key_to_toggle)
                self.notify(f"Ditutup: 📅 {group_key_to_toggle}")
            self._refresh_table(restore_cursor=cursor_row)

    def action_collapse_all(self) -> None:
        """Collapse all groups."""
        if self.group_by_date == "none":
            self.notify("Pengelompokan tanggal sedang Off!", severity="warning")
            return

        matching_items = [item for item in self.all_items if self._matches_filter(item)]
        all_groups = set()
        for item in matching_items:
            if self.group_by_date == "day":
                all_groups.add(item.date_day)
            elif self.group_by_date == "year":
                all_groups.add(item.date_year)
            else:
                all_groups.add(item.date_month)

        self.collapsed_groups.update(all_groups)
        self.notify(f"Semua {len(all_groups)} grup ditutup (Collapsed)")
        self._refresh_table()

    def action_expand_all(self) -> None:
        """Expand all groups."""
        if self.group_by_date == "none":
            self.notify("Pengelompokan tanggal sedang Off!", severity="warning")
            return

        self.collapsed_groups.clear()
        self.notify("Semua grup dibuka (Expanded)")
        self._refresh_table()

    def action_copy_selected_path(self) -> None:
        """Copies the full file path of the selected media item to clipboard."""
        table = self.query_one("#media-table", DataTable)
        cursor_row = table.cursor_row
        item_to_copy = None

        if 0 <= cursor_row < len(self.row_data_map):
            row_type, data = self.row_data_map[cursor_row]
            if row_type == "item":
                item_to_copy = data
            elif self.selected_item:
                item_to_copy = self.selected_item

        if not item_to_copy:
            self.notify("Pilih file media untuk menyalin path-nya!", severity="warning")
            return

        success = copy_text_to_clipboard(item_to_copy.path)
        if success:
            self.notify(f"📋 Path disalin:\n{item_to_copy.path}", severity="information", timeout=4)
        else:
            self.notify(f"Gagal menyalin path ke clipboard.", severity="error")

    def action_cycle_grouping(self) -> None:
        modes = ["none", "day", "month", "year"]
        current_idx = modes.index(self.group_by_date) if self.group_by_date in modes else 0
        next_mode = modes[(current_idx + 1) % len(modes)]
        self._set_group_by(next_mode)
        mode_labels = {"none": "Tanpa Grup", "day": "Per Hari", "month": "Per Bulan", "year": "Per Tahun"}
        self.notify(f"Pengelompokan Tanggal: {mode_labels[next_mode]}")

    def action_toggle_sort_order(self) -> None:
        self.sort_newest_first = not self.sort_newest_first
        btn = self.query_one("#btn-sort-order", Button)
        if self.sort_newest_first:
            btn.label = "⬇️ Terbaru"
            self.notify("Urutan: Terbaru dahulu")
        else:
            btn.label = "⬆️ Terlama"
            self.notify("Urutan: Terlama dahulu")
        self._refresh_table()

    def action_prompt_scan_path(self) -> None:
        def on_dismiss(selected_path: Optional[str]) -> None:
            if selected_path:
                self.scan_path = selected_path
                self.query_one("#lbl-current-path", Label).update(selected_path)
                self.start_scan()

        self.push_screen(PathPromptModal(self.scan_path), on_dismiss)

    def action_rescan(self) -> None:
        self.start_scan()

    def action_focus_search(self) -> None:
        self.query_one("#search-box", SearchInput).focus()

    def action_cancel_search_focus(self) -> None:
        self.query_one("#media-table", DataTable).focus()

    def action_open_selected_media(self) -> None:
        table = self.query_one("#media-table", DataTable)
        cursor_row = table.cursor_row
        if 0 <= cursor_row < len(self.row_data_map):
            row_type, data = self.row_data_map[cursor_row]
            if row_type == "item":
                self.selected_item = data

        if not self.selected_item or not os.path.exists(self.selected_item.path):
            self.notify("Pilih file media untuk dibuka!", severity="warning")
            return
        try:
            subprocess.Popen(["xdg-open", self.selected_item.path])
            self.notify(f"Membuka file: {self.selected_item.filename}")
        except Exception as e:
            self.notify(f"Gagal membuka file: {e}", severity="error")

    def action_open_selected_folder(self) -> None:
        table = self.query_one("#media-table", DataTable)
        cursor_row = table.cursor_row
        if 0 <= cursor_row < len(self.row_data_map):
            row_type, data = self.row_data_map[cursor_row]
            if row_type == "item":
                self.selected_item = data

        if not self.selected_item or not os.path.exists(self.selected_item.path):
            self.notify("Pilih file media untuk membuka lokasinya!", severity="warning")
            return
        folder = os.path.dirname(self.selected_item.path)
        try:
            subprocess.Popen(["xdg-open", folder])
            self.notify(f"Membuka direktori: {folder}")
        except Exception as e:
            self.notify(f"Gagal membuka direktori: {e}", severity="error")

    def action_export_data(self) -> None:
        if not self.all_items:
            self.notify("Tidak ada data untuk diekspor!", severity="warning")
            return

        export_path = os.path.join(os.getcwd(), "media_scan_report.csv")
        try:
            with open(export_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Filename", "Type", "Extension", "Size_Bytes", "Formatted_Size", "Date_Day", "Date_Month", "Date_Year", "Modified_Time", "Path"])
                for item in self.all_items:
                    writer.writerow([
                        item.filename,
                        item.media_type,
                        item.extension,
                        item.size_bytes,
                        item.formatted_size,
                        item.date_day,
                        item.date_month,
                        item.date_year,
                        item.formatted_date,
                        item.path
                    ])
            self.notify(f"Laporan berhasil diekspor ke:\n{export_path}", severity="information", timeout=5)
        except Exception as e:
            self.notify(f"Gagal mengekspor data: {e}", severity="error")


if __name__ == "__main__":
    target_path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~")
    app = MediaScanApp(initial_path=target_path)
    app.run()
