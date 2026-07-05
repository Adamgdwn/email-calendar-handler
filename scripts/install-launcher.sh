#!/usr/bin/env bash
# Install (or refresh) the InboxMind launcher for the current user. Idempotent —
# safe to re-run, e.g. after moving the repo.
#
# Installs a clickable entry in BOTH places:
#   ~/Desktop/InboxMind.desktop                      (desktop icon)
#   ~/.local/share/applications/inboxmind.desktop    (app-menu entry)
#   ~/.local/share/icons/hicolor/**/apps/inboxmind.* (themed icon)
# Both use Terminal=true so COSMIC opens cosmic-term running the menu.
#
# Uninstall:  scripts/install-launcher.sh --uninstall
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APPS="$HOME/.local/share/applications"
ICONROOT="$HOME/.local/share/icons/hicolor"
DESKTOP_DIR="${XDG_DESKTOP_DIR:-$HOME/Desktop}"
WRAPPER="$REPO/scripts/inboxmind-app.sh"
PNG="$REPO/assets/inboxmind.png"

refresh() {
  command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -f -t "$ICONROOT" 2>/dev/null || true
  command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true
}

write_entry() {  # $1 = destination path, $2 = Icon value
  cat > "$1" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=InboxMind
GenericName=Email & Calendar Intelligence
Comment=Connect a mailbox, sync, and open today's Morning Brief
Exec="$WRAPPER"
Path=$REPO
Terminal=true
Icon=$2
Categories=Office;Email;
Keywords=inbox;email;calendar;brief;outlook;
StartupNotify=true
EOF
  chmod +x "$1"
  command -v gio >/dev/null && gio set "$1" metadata::trusted true 2>/dev/null || true
}

if [ "${1:-}" = "--uninstall" ]; then
  rm -f "$DESKTOP_DIR/InboxMind.desktop" "$APPS/inboxmind.desktop"
  find "$ICONROOT" -name 'inboxmind.*' -delete 2>/dev/null || true
  refresh
  echo "InboxMind launcher, desktop icon, and themed icon removed."
  exit 0
fi

# themed icon (svg + raster sizes) for the app menu / general lookup
mkdir -p "$ICONROOT/scalable/apps"
cp "$REPO/assets/inboxmind.svg" "$ICONROOT/scalable/apps/inboxmind.svg"
if command -v rsvg-convert >/dev/null; then
  for s in 32 48 64 128 256 512; do
    mkdir -p "$ICONROOT/${s}x${s}/apps"
    rsvg-convert -w "$s" -h "$s" "$REPO/assets/inboxmind.svg" -o "$ICONROOT/${s}x${s}/apps/inboxmind.png"
  done
fi

mkdir -p "$APPS" "$DESKTOP_DIR"
write_entry "$APPS/inboxmind.desktop" "inboxmind"   # app menu: themed name
write_entry "$DESKTOP_DIR/InboxMind.desktop" "$PNG" # desktop: absolute PNG path
refresh

echo "InboxMind launcher installed:"
echo "  desktop icon : $DESKTOP_DIR/InboxMind.desktop"
echo "  app menu     : $APPS/inboxmind.desktop"
echo "  icon         : $ICONROOT/scalable/apps/inboxmind.svg (+ raster sizes)"
echo "Double-click InboxMind on your desktop, or search 'InboxMind' in the app launcher."
