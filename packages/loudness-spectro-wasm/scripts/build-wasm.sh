#!/usr/bin/env bash
# Build the asa-dsp-wasm crate to WebAssembly and generate JS bindings.
#
# Usage: scripts/build-wasm.sh [web|nodejs|bundler] [out-dir]
#   defaults: web pkg
#
# Requires:
#   * rustup target add wasm32-unknown-unknown
#   * wasm-bindgen-cli matching the wasm-bindgen crate version in Cargo.lock.
#     Install: cargo install wasm-bindgen-cli --version <ver>
#     or download the prebuilt binary from the wasm-bindgen releases.
#     Override the binary with WASM_BINDGEN=/path/to/wasm-bindgen.
#   * (optional) wasm-opt (binaryen) for -Oz size optimization; set WASM_OPT=1.
set -euo pipefail

TARGET_KIND="${1:-web}"
OUT="${2:-pkg}"
WASM_BINDGEN_BIN="${WASM_BINDGEN:-wasm-bindgen}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

cargo build -p asa-dsp-wasm --target wasm32-unknown-unknown --release
WASM="target/wasm32-unknown-unknown/release/asa_dsp_wasm.wasm"

rm -rf "$OUT"
"$WASM_BINDGEN_BIN" --target "$TARGET_KIND" --out-dir "$OUT" "$WASM"

if [ "${WASM_OPT:-0}" = "1" ] && command -v wasm-opt >/dev/null 2>&1; then
  for f in "$OUT"/*_bg.wasm; do
    wasm-opt -Oz "$f" -o "$f"
  done
fi

echo "Built $OUT ($TARGET_KIND):"
ls -la "$OUT"
