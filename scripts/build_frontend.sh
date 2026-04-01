#!/usr/bin/env bash
# Build the Next.js standalone output and copy it into synapse/_frontend/
# Run this before publishing the Python package (hatch build / pip install).
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR/.."
FRONTEND_DIR="$ROOT/frontend"
DEST="$ROOT/synapse/_frontend"

echo "Installing frontend dependencies..."
cd "$FRONTEND_DIR"
npm ci

echo "Building Next.js standalone..."
npm run build

STANDALONE="$FRONTEND_DIR/.next/standalone"
if [ ! -d "$STANDALONE" ]; then
  echo "Error: .next/standalone not found after build."
  echo "Make sure frontend/next.config.ts has output: 'standalone'"
  exit 1
fi

echo "Copying to synapse/_frontend/..."
rm -rf "$DEST"
mkdir -p "$DEST"
cp -r "$STANDALONE/." "$DEST/"
mkdir -p "$DEST/.next"
cp -r "$FRONTEND_DIR/.next/static" "$DEST/.next/static"
[ -d "$FRONTEND_DIR/public" ] && cp -r "$FRONTEND_DIR/public" "$DEST/public"

echo "Done. Frontend bundled into synapse/_frontend/"
