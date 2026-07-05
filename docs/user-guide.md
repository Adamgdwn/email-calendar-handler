# InboxMind User Guide

Last Updated: 2026-07-05

InboxMind reads your email and calendar, classifies what matters, proposes how
to file things, and eventually drafts replies — all locally, all under your
review before anything changes. Nothing is sent, moved, or modified without
your explicit approval.

---

## What InboxMind does (and does not do)

**Does:**
- Pull your inbox and calendar from Microsoft 365 / Outlook
- Generate a daily Morning Brief: agenda, triaged threads, filing proposals
- Learn your filing preferences from your accept/reject decisions
- Draft reply suggestions for your review (coming soon)

**Does not:**
- Send email
- Move or label messages in your mailbox
- Access your email body beyond a short excerpt for classification
- Act autonomously — every consequential output requires your review

---

## Opening InboxMind

**Desktop launcher (easiest):** Open the InboxMind app from your application
menu or the Desktop shortcut. It presents a numbered menu.

**Terminal:** `uv run inboxmind <command>` from the project directory, or just
`inboxmind <command>` if the project is on your PATH.

---

## First-time setup: connecting your account

Run this once to sign in:

```
inboxmind connect
```

InboxMind will:
1. Show you the exact read-only permissions it is requesting (Mail.Read,
   Calendars.Read, User.Read — no write access)
2. Ask `y/N` to confirm you want to proceed
3. Print a short device code and a URL: `microsoft.com/devicelogin`
4. Open that URL in any browser, enter the code, and sign in as
   `adamgoodwin@guidedailabs.com` (or whatever account you're connecting)
5. Grant consent when prompted

Once complete, your token is encrypted and cached locally. You will not need to
sign in again unless the token expires or you explicitly reconnect.

---

## Daily workflow

After the first connect, the typical morning routine is three commands:

### 1. Sync — pull new mail and calendar

```
inboxmind sync
```

Fetches messages and calendar events from Microsoft Graph into the local
database. The first run pulls everything; subsequent runs are incremental
(only what changed since last sync). Takes a few seconds once the cache is
warm.

To widen the calendar window:

```
inboxmind sync --calendar-days 7
```

### 2. Brief — read your morning summary

```
inboxmind brief
```

Prints your Morning Brief to the terminal and saves a copy to
`~/.inboxmind/briefs/brief-YYYY-MM-DD.md`.

The brief contains:
- **Today's agenda** — calendar events for today, with times, all-day flags,
  and join links
- **Mail triage** — threads from the last 24 hours, grouped by urgency:
  *Critical → High → Normal → Low*
- **Filing proposals** — where InboxMind thinks each thread belongs, with a
  stable ID for review
- **Footer** — your cumulative acceptance rate and whether write access is
  unlocked

Mail from people who appear in today's meetings is bumped one urgency band
(shown with a reason) so meeting-related threads surface first.

To look back further than 24 hours:

```
inboxmind brief --hours 48
```

**First run only:** add `--profile` to select your persona:

```
inboxmind brief --profile consulting
```

Available profiles: `city_council`, `consulting`, `habitat`, `prime_boilers`.
This is saved to your account and is not needed on subsequent runs.

### 3. Review — accept or reject filing proposals

```
inboxmind review
```

Steps through each filing proposal from your brief, one at a time:

| Key | Action |
|-----|--------|
| `a` | Accept the proposed folder path |
| `m` | Modify — type a different path (slash-separated, e.g. `Clients/Acme`) |
| `r` | Reject — this proposal was wrong |
| `s` | Skip — decide later |

No mailbox changes happen. Your decisions are recorded locally. After you
finish, InboxMind's learning system folds your choices into filing rules:

- **3 consecutive accepts** of the same path → rule confirmed
- **1 reject** → rule retired
- **Modify or broken streak** → rule stays provisional

Confirmed rules still require explicit write-scope approval before InboxMind
would ever act on them automatically — which is not possible until the
acceptance rate reaches 70% and write scope is manually enabled.

---

## Understanding urgency bands

InboxMind classifies threads using metadata and a short excerpt — it never
reads your full email body. Classification is guided by your persona's urgency
keywords.

| Band | Meaning |
|------|---------|
| Critical | Requires action today |
| High | Important, time-sensitive |
| Normal | Standard inbox traffic |
| Low | FYI, newsletters, receipts |

Meeting-boosted threads show a note like `↑ boosted — Acme call attendee` so
you know why something ranked higher than usual.

---

## Where files are stored

All InboxMind state lives in `~/.inboxmind/` by default.

| Path | Contents |
|------|---------|
| `~/.inboxmind/graph_token_cache.enc` | Encrypted OAuth token |
| `~/.inboxmind/consent_log.jsonl` | Audit log of consent events |
| `~/.inboxmind/briefs/` | Saved Morning Brief files |

Email bodies in the database are stored as Fernet ciphertext — they are never
stored in plain text.

---

## Troubleshooting

**"No token cache found" or authentication error**
Run `inboxmind connect` again. Your token may have expired.

**Brief shows no mail**
Run `inboxmind sync` first, then retry. Check that sync completed without errors.

**Wrong Supabase project loading**
If you run InboxMind from a terminal where a `SUPABASE_*` environment variable
is set (e.g. from a master-env profile), it can override the project's `.env`.
Use the desktop launcher or the menu wrapper (`scripts/inboxmind-app.sh`) —
both clear the ambient variable automatically.

**Calendar not appearing in brief**
The `Calendars.Read` permission may not be in your token cache. Run
`inboxmind connect` to refresh the token with the full scope set.

---

## Supported accounts (current)

InboxMind currently supports **one Microsoft 365 / Outlook account** at a time.

Connecting a client's O365 account is possible if their tenant allows user
consent (most do). Additional providers — Gmail, Rogers/Shaw IMAP — are on the
roadmap but not yet built.

---

## Coming soon

**`inboxmind draft`** (Chunk 12): Persona-toned reply suggestions, local only,
presented for your review before any action. Tone adapts per account:
Guided AI Labs = leadership voice, Red Deer = professional, Shaw = relaxed.

**Polished daily-briefing UI**: A web-like interface to replace the terminal
menu — agenda and triage in a newsfeed format, every item accept/reject-able
inline.

**Multi-account expansion**: Read all your inboxes in one brief, with tone and
urgency calibrated per account.
