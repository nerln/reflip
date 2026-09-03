#!/bin/zsh
# Builds Resources/Reflip.icns from the mark.
#
# Generated rather than committed as a binary, for the reason the rest of this repository
# is text: Tools/make-icon.swift can be read and reviewed, an .icns cannot. Run it when
# the mark changes.
set -euo pipefail

cd "$(dirname "$0")"
WORK="$(mktemp -d)"
ICONSET="$WORK/Reflip.iconset"
mkdir -p Resources

echo "==> drawing the tiles"
swiftc -O -parse-as-library Tools/make-icon.swift -o "$WORK/make-icon"
"$WORK/make-icon" "$ICONSET"

echo "==> packing"
iconutil -c icns "$ICONSET" -o Resources/Reflip.icns
echo "==> Resources/Reflip.icns ($(du -h Resources/Reflip.icns | cut -f1))"
