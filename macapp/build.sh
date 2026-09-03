#!/bin/zsh
# Builds Reflip.app.
#
# No .xcodeproj: SwiftPM produces the executable and the bundle is assembled around it
# here. Less elegant than a project file, and in exchange everything stays in git as text
# and it rebuilds from a terminal without opening Xcode.
set -euo pipefail

cd "$(dirname "$0")"
APP="Reflip.app"
CONF="${1:-release}"

echo "==> building ($CONF)"
swift build -c "$CONF" --disable-sandbox

BIN="$(swift build -c "$CONF" --show-bin-path)/Reflip"
[[ -x "$BIN" ]] || { echo "executable not found: $BIN"; exit 1 }

echo "==> assembling the bundle"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/Reflip"
cp Resources/Info.plist "$APP/Contents/Info.plist"
# The icon is generated rather than committed: a clone has the drawing and the code that
# renders it, not a binary nobody can review.
[[ -f Resources/Reflip.icns ]] || ./make-icon.sh >/dev/null
cp Resources/Reflip.icns "$APP/Contents/Resources/Reflip.icns"
printf 'APPL????' > "$APP/Contents/PkgInfo"

# Ad-hoc signature: enough to run locally. Without it, recent macOS refuses to launch an
# unsigned bundle even when you compiled it yourself. No entitlements, because the app
# asks the system for nothing: it runs `reflip` and draws what it answers.
codesign --force --deep --sign - "$APP" 2>/dev/null || \
    echo "   (signing failed: the app still starts if you right-click > Open the first time)"

echo "==> done: $(pwd)/$APP"
echo "    open it with:  open $APP"
