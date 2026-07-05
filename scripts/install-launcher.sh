#!/usr/bin/env bash
# Install (or refresh) the InboxMind desktop launcher + icon for the current
# user. Idempotent — safe to re-run, e.g. after moving the repo.
#
# Installs:
#   ~/.local/share/applications/inboxmind.desktop   -> scripts/inboxmind-app.sh
#   ~/.local/share/icons/hicolor/**/apps/inboxmind.* <- assets/inboxmind.svg
#
# Uninstall:  scripts/install-launcher.sh --uninstall
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APPS="$HOME/.local/share/applications"
ICONROOT="$HOME/.local/share/icons/hicolor"
DESKTOP="$APPS/inboxmind.desktop"

refresh() {
  command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -f -t "$ICONROOT" 2>/dev/null || true
  command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true
}

if [ "${1:-}" = "--uninstall" ]; then
  rm -f "$DESKTOP"
  find "$ICONROOT" -name 'inboxmind.*' -delete 2>/dev/null || true
  refresh
  echo "InboxMind launcher and icon removed."
  exit 0
fi

# --- icon ---
mkdir -p "$ICONROOT/scalable/apps"
cp "$REPO/assets/inboxmind.svg" "$ICONROOT/scalable/apps/inboxmind.svg"
if command -v rsvg-convert >/dev/null; then
  for s in 32 48 64 128 256 512; do
    mkdir -p "$ICONROOT/${s}x${s}/apps"
    rsvg-convert -w "$s" -h "$s" "$REPO/assets/inboxmind.svg" -o "$ICONROOT/${s}x${s}/apps/inboxmind.png"
  done
fi

# --- launcher (.desktop with paths resolved to this repo) ---
mkdir -p "$APPS"
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=InboxMind
GenericName=Email & Calendar Intelligence
Comment=Connect a mailbox, sync, and open today's Morning Brief
Exec="$REPO/scripts/inboxmind-app.sh"
Path=$REPO
Terminal=true
Icon=inboxmind
Categories=Office;Email;
Keywords=inbox;email;calendar;brief;outlook;
EOF
chmod +x "$REPO/scripts/inboxmind-app.sh"
refresh

echo "InboxMind launcher installed:"
echo "  desktop : $DESKTOP"
echo "  icon    : $ICONROOT/scalable/apps/inboxmind.svg (+ raster sizes)"
echo "Search 'InboxMind' in your app launcher, or run: $REPO/scripts/inboxmind-app.sh"
