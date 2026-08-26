#!/usr/bin/env bash
# compile.sh - Meng-compile kode Python MediaScan ke instruksi bahasa asli mesin (Native ELF Binary) menggunakan Nuitka & GCC

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "⚡ MEMULAI KOMPILASI KODE KE NATIVE MACHINE CODE (ELF BINARY)"
echo "============================================================"

# 1. Periksa Virtual Environment
if [ ! -d ".venv" ]; then
    echo "📦 Membuat Virtual Environment..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

# 2. Pastikan Nuitka terpasang
if ! .venv/bin/python -c "import nuitka" 2>/dev/null; then
    echo "📦 Menginstal Nuitka C-Compiler & Zstandard..."
    .venv/bin/pip install nuitka zstandard
fi

echo "⚙️ Memeriksa GCC Compiler..."
if ! command -v gcc &> /dev/null; then
    echo "❌ Error: GCC compiler tidak ditemukan. Pastikan 'gcc' terpasang di sistem."
    exit 1
fi
echo "✅ Compiler GCC terdeteksi: $(gcc --version | head -n 1)"

OUTPUT_NAME="mediascan"

echo "🔨 Meng-compile app.py, scanner.py, preview.py ke Native Binary ($OUTPUT_NAME)..."
echo "   (Proses ini menerjemahkan Python -> Kode C -> Binary Mesin Asli)"

# 3. Jalankan Nuitka Compiler
.venv/bin/python -m nuitka \
    --onefile \
    --assume-yes-for-downloads \
    --include-module=scanner \
    --include-module=preview \
    --include-package=textual \
    --include-package=rich \
    --include-package=PIL \
    --output-filename="$OUTPUT_NAME" \
    --remove-output \
    app.py

chmod +x "$OUTPUT_NAME"

echo ""
echo "============================================================"
echo "🎉 KOMPILASI SELESAI DENGAN SUKSES!"
echo "============================================================"
echo "Executable native binary telah dibuat: ./$OUTPUT_NAME"
echo ""
echo "File binary tersebut adalah binary mesin asli (ELF 64-bit executable)"
echo "yang dapat langsung dijalankan tanpa interpreter Python:"
echo ""
echo "   ./$OUTPUT_NAME"
echo "   ./$OUTPUT_NAME /home/rasyidk/Pictures"
echo "============================================================"
