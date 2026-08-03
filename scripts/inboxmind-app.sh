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
  # Determine hourly-check status for the menu label.
  if systemctl --user is-active --quiet inboxmind-check.timer 2>/dev/null; then
    check_status="ENABLED"
  else
    check_status="disabled"
  fi

  _accts=$(grep '^INBOXMIND_ACCOUNTS=' "$REPO/.env" 2>/dev/null | cut -d= -f2- | tr ',' ' | ')
  [ -z "$_accts" ] && _accts="(none configured — check .env)"
  _accts_line=$(printf "  Accounts: %-36s" "${_accts:0:36}")

  cat <<MENU

  ┌────────────────────────────────────────────────┐
  │                  InboxMind                      │
  │${_accts_line}│
  ├────────────────────────────────────────────────┤
  │  0) morning routine  — sync + brief + review   │
  ├────────────────────────────────────────────────┤
  │  1) connect  — sign in to a mailbox (one-time) │
  │  2) sync     — pull new mail + calendar        │
  │  3) brief    — today's Morning Brief           │
  │  4) review   — accept / modify / reject        │
  │  5) open the latest brief file                 │
  │  6) audit  — propose a better folder structure │
  │  7) hourly check     [$check_status]           │
  │  q) quit                                       │
  └────────────────────────────────────────────────┘
MENU
  read -rp "  choose: " choice
  case "$choice" in
    0)
      # ROUTINE STUB: future versions will let each persona define its own morning
      # sequence here (e.g. consulting → sync+brief+draft+review; city_council →
      # sync+brief+calendar-prep+review). Routine configs will live in persona YAML.
      run sync || true
      run brief || true
      run review || true
      ;;
    1)
      echo
      echo "  Configured accounts: ${_accts:-"(none — check .env)"}"
      echo "  Existing aliases: $(ls "$REPO/src/personas/"*.yaml 2>/dev/null | xargs -I{} basename {} .yaml | tr '\n' ' ')"
      echo
      read -rp "  Account alias to connect (e.g. outlook_work, hotmail — blank = default): " _new_alias
      if [ -n "$_new_alias" ]; then
        _current_accts=$(grep '^INBOXMIND_ACCOUNTS=' "$REPO/.env" 2>/dev/null | cut -d= -f2-)
        if ! echo "$_current_accts" | grep -qw "$_new_alias"; then
          read -rp "  Add '$_new_alias' to INBOXMIND_ACCOUNTS in .env? [Y/n]: " _add_env
          if [[ ! "$_add_env" =~ ^[nN]$ ]]; then
            if grep -q '^INBOXMIND_ACCOUNTS=' "$REPO/.env" 2>/dev/null; then
              sed -i "s/^INBOXMIND_ACCOUNTS=.*/INBOXMIND_ACCOUNTS=${_current_accts:+$_current_accts,}$_new_alias/" "$REPO/.env"
            else
              echo "INBOXMIND_ACCOUNTS=$_new_alias" >> "$REPO/.env"
            fi
            echo "  Added '$_new_alias' to INBOXMIND_ACCOUNTS."
          fi
        fi
        run connect --account "$_new_alias" || true
      else
        run connect || true
      fi
      ;;
    2) run sync || true ;;
    3) run brief || true ;;
    4) run review || true ;;
    5)
      brief_file="$(ls -1t brief-*.md 2>/dev/null | head -1)"
      if [ -n "$brief_file" ]; then xdg-open "$brief_file" >/dev/null 2>&1 &
      else echo "  No brief file yet — run 'brief' first."; fi
      ;;
    6) run audit || true ;;
    7)
      if systemctl --user is-active --quiet inboxmind-check.timer 2>/dev/null; then
        read -rp "  Hourly check is ENABLED. Disable it? [y/N]: " confirm
        if [[ "$confirm" =~ ^[yY]$ ]]; then
          systemctl --user disable --now inboxmind-check.timer
          echo "  Hourly CRITICAL check disabled."
        fi
      else
        read -rp "  Hourly check is disabled. Enable it? [y/N]: " confirm
        if [[ "$confirm" =~ ^[yY]$ ]]; then
          if systemctl --user list-unit-files inboxmind-check.timer &>/dev/null 2>&1; then
            systemctl --user enable --now inboxmind-check.timer
            echo "  Hourly CRITICAL check enabled."
          else
            echo "  Timer not installed yet. Run: bash scripts/install-check-timer.sh"
          fi
        fi
      fi
      ;;
    q|Q) exit 0 ;;
    *) echo "  Unrecognized choice." ;;
  esac
  echo
  read -rp "  press enter to return to the menu… " _
done
