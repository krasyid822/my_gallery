# 📸 MediaScan TUI - Disk Media Scanner & Explorer

Aplikasi TUI (Terminal User Interface) modern, responsif, dan interaktif untuk memindai, menganalisis, memfilter, melihat preview visual, dan menjelajahi seluruh file **gambar** dan **video** di penyimpanan disk Anda (**Strictly Read-Only & Native Executable Support**).

---

## ✨ Fitur Utama

- ⚡ **Kompilasi ke Bahasa Asli Mesin (Native ELF Binary)**: Dapat di-compile menjadi binary mandiri berkecepatan tinggi tanpa perlu Python interpreter terpasang (`./compile.sh`).
- 📱 **Desain TUI Responsif**: Tata letak otomatis menyesuaikan ukuran terminal tanpa terpotong (*no clipping*).
- 🔍 **Pencarian Cepat & Kontras Tinggi**:
  - Masuk ke pencarian dengan **`/`**, keluar dengan **`Escape`**, **`Enter`**, atau tombol panah **`↓`**.
- 🔒 **Strictly Read-Only & Aman**: Murni inspeksi dan eksplorasi data tanpa operasi penghapusan/modifikasi.
- 📅 **Pengelompokan Tanggal Bersih (Date Grouping)**:
  - **`Bulan` (`YYYY-MM`)** *(Default)*: Dikelompokkan rapi per bulan & tahun.
  - **`Hari` (`YYYY-MM-DD`)**: Dikelompokkan per tanggal spesifik.
  - **`Tahun` (`YYYY`)**: Dikelompokkan per tahun.
  - **`Off`**: Tampilan flat list standar.
  - Collapse & Expand: **`Spasi`** (grup terpilih), **`c`** (Tutup Semua), **`x`** (Buka Semua).
- 📋 **Salin Path File (Copy to Clipboard)**:
  - Salin path lengkap file yang sedang disorot langsung ke clipboard sistem (Wayland / X11) dengan menekan **`y`** atau klik tombol **`[📋 Salin Path]`**.
- 🎨 **Truecolor ANSI Half-Block Thumbnail Preview**: Menampilkan render preview gambar berwarna 24-bit langsung di dalam terminal menggunakan karakter Unicode half-block (`▀` / `▄`).
- 🎬 **Dukungan Format Lengkap**:
  - **Gambar**: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.bmp`, `.svg`, `.tiff`, `.ico`, `.heic`, `.avif`, `.raw`, dll.
  - **Video**: `.mp4`, `.mkv`, `.avi`, `.mov`, `.wmv`, `.flv`, `.webm`, `.m4v`, `.3gp`, `.mts`, `.m2ts`, dll.
- 📊 **Dashboard & Insights**: Menampilkan total kapasitas media, rasio gambar vs video, dan daftar 10 file media terbesar di disk.
- 🚀 **Integrasi Sistem Operasi**: Buka file langsung di aplikasi media player default (`o`) atau buka folder di file manager (`f`).
- 📥 **Ekspor Laporan**: Ekspor seluruh daftar temuan media lengkap dengan kolom tanggal ke format CSV (`e`).

---

## 🛠️ Kompilasi ke Binary Bahasa Asli Mesin (Native Executable)

Untuk meng-compile seluruh source code ke dalam bahasa mesin asli (standalone ELF 64-bit binary) menggunakan **Nuitka** dan **GCC**:

```bash
# Jalankan skrip kompilasi
./compile.sh
```

Setelah proses kompilasi selesai, binary mandiri `./mediascan` akan siap digunakan langsung:

```bash
# Menjalankan binary hasil kompilasi
./mediascan

# Atau tentukan path spesifik
./mediascan /home/rasyidk/Pictures
```

---

## 🚀 Cara Menjalankan Versi Script

```bash
# Jalankan pemindaian pada direktori Home (default)
./run.sh

# Atau tentukan path spesifik yang ingin dipindai
./run.sh /home/rasyidk/Pictures
```

---

## ⌨️ Pintasan Keyboard (Keybindings)

| Tombol | Fungsi |
|---|---|
| `/` | **Fokus / Masuk ke Kotak Pencarian (Search)** |
| `Escape` / `Enter` / `↓` | **Keluar dari Pencarian (Kembali ke Tabel Media)** |
| `y` | **Salin Path Lengkap (Copy to Clipboard)** |
| `Spasi` | **Toggle Buka / Tutup** grup tanggal terpilih |
| `c` | **Tutup Semua Grup (Collapse All)** |
| `x` | **Buka Semua Grup (Expand All)** |
| `g` | Ganti mode pengelompokan (**Bulan** → **Tahun** → **Hari** → **Off**) |
| `t` | Ganti urutan tanggal (**⬇️ Terbaru** ⟷ **⬆️ Terlama**) |
| `↑` / `↓` | Navigasi baris tabel media / header grup |
| `o` | Buka file di aplikasi default sistem (`xdg-open`) |
| `f` | Buka folder lokasi file di file manager |
| `s` | Pilih path direktori baru untuk dipindai |
| `r` | Pindai ulang (Rescan) direktori saat ini |
| `e` | Ekspor daftar media ke file `media_scan_report.csv` |
| `q` | Keluar dari aplikasi |
