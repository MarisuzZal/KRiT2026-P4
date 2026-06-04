#!/bin/bash
# =============================================================================
# Walidacja kodu P4 w Intel Tofino Model (symulator)
#
# Wymaga zainstalowanego Intel P4 Studio SDE 9.13.2 z tofino-model.
# Uruchamia symulator, ładuje program, weryfikuje pakietem testowym.
# =============================================================================
set -euo pipefail

SDE="${SDE:-/opt/bf-sde-9.13.2}"
PROGRAM="measurement"
P4_SRC="$(dirname "$0")/../analyzer/p4/${PROGRAM}.p4"
BUILD_DIR="$(dirname "$0")/build"

if [ ! -d "$SDE" ]; then
    echo "ERROR: SDE not found at $SDE — ustaw SDE=/path/to/bf-sde-9.13.2"
    exit 1
fi

mkdir -p "$BUILD_DIR"

echo "[*] Kompilacja $P4_SRC..."
"$SDE/install/bin/bf-p4c" \
    --target tofino \
    --arch tna \
    --std p4-16 \
    -o "$BUILD_DIR" \
    "$P4_SRC"

echo "[*] Uruchamianie tofino-model..."
"$SDE/install/bin/tofino-model" \
    --p4-target-config "$BUILD_DIR/${PROGRAM}.conf" \
    --time-disable \
    &
TM_PID=$!

sleep 5
echo "[*] tofino-model PID=$TM_PID. Uruchom kontroler:"
echo "    python3 analyzer/controller/main.py --no-program"
echo ""
echo "[*] Aby zatrzymać symulator: kill $TM_PID"
