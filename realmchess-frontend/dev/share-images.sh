#!/bin/sh
# Redraw the link preview and home-screen icons in public/ from dev/share-images.html.
# Needs Google Chrome. Run from realmchess-frontend: sh dev/share-images.sh
set -e
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
PAGE="file://$(pwd)/dev/share-images.html"
shot() { # image width height output
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
    --allow-file-access-from-files --window-size="$2,$3" --screenshot="$4" "$PAGE?image=$1" 2>/dev/null
}
shot preview 1200 630 public/preview.png
shot icon 512 512 public/icon-512.png
# Chrome will not open a window this small, so the small icons are scaled from the large one
# (sips comes with macOS)
sips -z 192 192 public/icon-512.png --out public/icon-192.png >/dev/null
sips -z 180 180 public/icon-512.png --out public/apple-touch-icon.png >/dev/null
