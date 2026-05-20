#!/usr/bin/env bash
# Fetch the official EBU Tech 3341/3342 loudness compliance signals into
# testsets/ebu/ (gitignored), then print how to run the optional conformance
# path against them.
#
# The download URL is NOT hardcoded on purpose: the canonical location is
# published on the EBU Tech 3341 page (https://tech.ebu.ch/publications/tech3341)
# and may change — guessing it would silently fetch the wrong thing. Provide it
# explicitly:
#
#   EBU_TESTSET_URL="<archive-or-file-url>" bash scripts/fetch-ebu-testset.sh
#
# Then enable the optional test path:
#
#   ASA_EBU_TESTSET_DIR=testsets/ebu cargo test --test ebu_conformance
#
# and add the filename -> expected-LUFS entries (from EBU Tech 3341 §2.1) to the
# EXPECTED table in crates/asa-dsp/tests/ebu_conformance.rs.
#
# NOTE: in a sandboxed/remote session the network policy may block this fetch
# regardless of the URL.
set -euo pipefail

if [ -z "${EBU_TESTSET_URL:-}" ]; then
  echo "ERROR: EBU_TESTSET_URL is not set." >&2
  echo "       Find the canonical archive on https://tech.ebu.ch/publications/tech3341" >&2
  echo "       then re-run: EBU_TESTSET_URL=<url> bash scripts/fetch-ebu-testset.sh" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/testsets/ebu"
mkdir -p "$DEST"

TMP="$(mktemp -t ebu-testset.XXXXXX)"
trap 'rm -f "$TMP"' EXIT

echo "Downloading $EBU_TESTSET_URL ..."
if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$EBU_TESTSET_URL" -o "$TMP"
elif command -v wget >/dev/null 2>&1; then
  wget -qO "$TMP" "$EBU_TESTSET_URL"
else
  echo "ERROR: need curl or wget to download." >&2
  exit 1
fi

case "$EBU_TESTSET_URL" in
  *.zip)
    command -v unzip >/dev/null 2>&1 || { echo "ERROR: need unzip for .zip archives." >&2; exit 1; }
    unzip -o "$TMP" -d "$DEST" ;;
  *.tar.gz|*.tgz)
    tar -xzf "$TMP" -C "$DEST" ;;
  *.tar)
    tar -xf "$TMP" -C "$DEST" ;;
  *)
    # Not an archive: treat the URL as a single file and keep its basename.
    cp "$TMP" "$DEST/$(basename "$EBU_TESTSET_URL")" ;;
esac

echo
echo "Fetched into: $DEST"
echo "WAVs present:"
find "$DEST" -name '*.wav' | sed 's/^/  /' || true
echo
echo "Run the optional official-set path:"
echo "  ASA_EBU_TESTSET_DIR=$DEST cargo test --test ebu_conformance"
echo "(add filename -> expected-LUFS rows to EXPECTED in crates/asa-dsp/tests/ebu_conformance.rs first)"
