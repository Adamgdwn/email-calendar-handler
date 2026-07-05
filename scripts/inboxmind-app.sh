#!/usr/bin/env bash
# InboxMind launcher — a clickable "frame" for the CLI.
#
# Opens a small menu to run connect / sync / brief / review, or run one
# directly:  scripts/inboxmind-app.sh connect
#
# It deliberately ignores any ambient master-env SUPABASE_* variables so it
# always targets InboxMind's OWN Supabase project (the one in .env), never a
# stray project inherited from the shell.
#
# Rollback: delete this file and ~/.local/share/applications/inboxmind.desktop.
set -uo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

# When launched without a terminal (e.g. double-clicking the desktop icon on
# COSMIC, which does not honour Terminal=true), reopen inside a terminal window
# so the interactive menu has a TTY. cosmic-term needs `--` before the command.
if [ "${1:-}" != "--in-term" ] && [ ! -t 0 ]; then
  if command -v cosmic-term >/dev/null 2>&1; then exec cosmic-term -- "$SELF" --in-term "$@"; fi
  if command -v x-terminal-emulator >/dev/null 2>&1; then exec x-terminal-emulator -e "$SELF" --in-term "$@"; fi
fi
[ "${1:-}" = "--in-term" ] && shift

# Force the project's own .env config to win over ambient master-env creds.
unset -v SUPABASE_URL SUPABASE_SERVICE_ROLE_KEY SUPABASE_ANON_KEY \
         SUPABASE_PROJECT_REF SUPABASE_ACCESS_TOKEN 2>/dev/null || true

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || { echo "Cannot locate the InboxMind project directory."; exit 1; }
UV="$(command -v uv 2>/dev/null || echo "$HOME/.local/bin/uv")"

run() {
  echo
  echo "  > inboxmind $*"
  echo "  ────────────────────────────────────────────"
  "$UV" run inboxmind "$@"
  local rc=$?
  echo "  ────────────────────────────────────────────"
  echo "  (inboxmind $1 finished, exit $rc)"
  return "$rc"
}

# Direct mode: `inboxmind-app.sh <command> [args]` runs it and exits.
if [ "$#" -gt 0 ]; then
  run "$@"
  exit "$?"
fi

# Interactive menu mode.
while true; do
  cat <<'MENU'

  ┌────────────────────────────────────────────────┐
  │                  InboxMind                      │
  ├────────────────────────────────────────────────┤
  │  1) connect  — sign in to a mailbox (one-time)  │
  │  2) sync     — pull new mail + calendar         │
  │  3) brief    — today's Morning Brief            │
  │  4) review   — accept / modify / reject         │
  │  5) open the latest brief file                  │
  │  q) quit                                         │
  └────────────────────────────────────────────────┘
MENU
  read -rp "  choose: " choice
  case "$choice" in
    1) run connect || true ;;
    2) run sync || true ;;
    3) run brief || true ;;
    4) run review || true ;;
    5)
      brief_file="$(ls -1t brief-*.md 2>/dev/null | head -1)"
      if [ -n "$brief_file" ]; then xdg-open "$brief_file" >/dev/null 2>&1 &
      else echo "  No brief file yet — run 'brief' first."; fi
      ;;
    q|Q) exit 0 ;;
    *) echo "  Unrecognized choice." ;;
  esac
  echo
  read -rp "  press enter to return to the menu… " _
done
