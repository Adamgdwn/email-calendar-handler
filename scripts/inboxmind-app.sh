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

  _inboxmind_home="${INBOXMIND_HOME:-$HOME/.inboxmind}"

  printf "\n"
  printf "  ┌────────────────────────────────────────────────┐\n"
  printf "  │                  InboxMind                      │\n"
  printf "  ├────────────────────────────────────────────────┤\n"
  printf "  │  Accounts                                      │\n"
  _any_accts=0
  for _f in "$_inboxmind_home"/account_*.email; do
    [ -f "$_f" ] || continue
    _al=$(basename "$_f" .email | sed 's/^account_//')
    _em=$(< "$_f"); _em="${_em%%$'\n'*}"
    printf "  │  [+] %-14s  %-26s│\n" "${_al:0:14}" "${_em:0:26}"
    _any_accts=1
  done
  for _al in $(grep '^INBOXMIND_ACCOUNTS=' "$REPO/.env" 2>/dev/null \
               | cut -d= -f2- | tr ',' '\n' | tr -d ' '); do
    [ -z "$_al" ] && continue
    [ -f "$_inboxmind_home/account_${_al}.email" ] && continue
    printf "  │  [-] %-14s  %-26s│\n" "${_al:0:14}" "(not connected)"
    _any_accts=1
  done
  if [ "$_any_accts" -eq 0 ]; then
    printf "  │  (none)  Press A to add your first account     │\n"
  fi
  printf "  ├────────────────────────────────────────────────┤\n"
  printf "  │  A  add / reconnect a mailbox                  │\n"
  printf "  ├────────────────────────────────────────────────┤\n"
  printf "  │  0  morning routine  sync + brief + review     │\n"
  printf "  │  2  sync             pull new mail + calendar  │\n"
  printf "  │  3  brief            today's Morning Brief     │\n"
  printf "  │  4  review           accept / skip / reject    │\n"
  printf "  │  5  open latest brief                          │\n"
  printf "  │  6  audit            propose folder structure  │\n"
  printf "  │  7  hourly check     [%-8s]                │\n" "$check_status"
  printf "  │  q  quit                                       │\n"
  printf "  └────────────────────────────────────────────────┘\n"

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
    A|a|1)
      echo
      echo "  Sign-in opens a URL in your browser — no password is typed here."
      echo "  Once connected, the account appears in the menu permanently."
      echo
      _env_accts=$(grep '^INBOXMIND_ACCOUNTS=' "$REPO/.env" 2>/dev/null | cut -d= -f2- | tr ',' ' ')
      [ -n "$_env_accts" ] && echo "  Existing aliases: $_env_accts"
      echo
      read -rp "  Email address to connect (e.g. user@hotmail.com): " _new_email
      if [ -n "$_new_email" ]; then
        # Derive alias from email domain (user@hotmail.com -> hotmail)
        _domain="${_new_email#*@}"
        _new_alias="${_domain%%.*}"
        _new_alias=$(printf '%s' "$_new_alias" | tr '[:upper:]' '[:lower:]' \
                     | tr -cs 'a-z0-9' '_' | sed 's/_*$//')
        read -rp "  Internal alias '$_new_alias' — press enter to confirm, or type a different one: " _confirm_alias
        [ -n "$_confirm_alias" ] && _new_alias="$_confirm_alias"
        _current_accts=$(grep '^INBOXMIND_ACCOUNTS=' "$REPO/.env" 2>/dev/null | cut -d= -f2-)
        if ! echo "$_current_accts" | grep -qw "$_new_alias"; then
          if grep -q '^INBOXMIND_ACCOUNTS=' "$REPO/.env" 2>/dev/null; then
            sed -i "s/^INBOXMIND_ACCOUNTS=.*/INBOXMIND_ACCOUNTS=${_current_accts:+$_current_accts,}$_new_alias/" "$REPO/.env"
          else
            echo "INBOXMIND_ACCOUNTS=$_new_alias" >> "$REPO/.env"
          fi
          echo "  Alias '$_new_alias' added."
        fi
        run connect --account "$_new_alias" || true
      else
        echo "  No email entered — nothing changed."
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
