#!/usr/bin/env bash
# Install (or refresh) the InboxMind hourly CRITICAL-check systemd user timer.
# Idempotent — safe to re-run after moving the repo.
#
# Installs:
#   ~/.config/systemd/user/inboxmind-check.service
#   ~/.config/systemd/user/inboxmind-check.timer
# Enables and starts the timer immediately.
#
# Uninstall:  scripts/install-check-timer.sh --uninstall
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEMD_USER="$HOME/.config/systemd/user"
SRC_SERVICE="$REPO/scripts/inboxmind-check.service"
SRC_TIMER="$REPO/scripts/inboxmind-check.timer"

if [ "${1:-}" = "--uninstall" ]; then
  systemctl --user disable --now inboxmind-check.timer 2>/dev/null || true
  rm -f "$SYSTEMD_USER/inboxmind-check.service" "$SYSTEMD_USER/inboxmind-check.timer"
  systemctl --user daemon-reload
  echo "InboxMind hourly check timer removed."
  exit 0
fi

mkdir -p "$SYSTEMD_USER"

# Substitute @REPO@ placeholder with the actual repo path.
sed "s|@REPO@|$REPO|g" "$SRC_SERVICE" > "$SYSTEMD_USER/inboxmind-check.service"
cp "$SRC_TIMER" "$SYSTEMD_USER/inboxmind-check.timer"

systemctl --user daemon-reload
systemctl --user enable --now inboxmind-check.timer

echo "InboxMind hourly check timer installed:"
echo "  service : $SYSTEMD_USER/inboxmind-check.service"
echo "  timer   : $SYSTEMD_USER/inboxmind-check.timer"
echo "  status  : $(systemctl --user is-active inboxmind-check.timer)"
echo "Run 'systemctl --user status inboxmind-check.timer' to verify."
