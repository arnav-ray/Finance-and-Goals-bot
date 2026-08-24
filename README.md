# Family Finance and Goals Bot

A serverless Telegram bot for family finance tracking and goal management. Send a text message or a photo of a receipt — the bot parses it with an LLM, appends it to Google Sheets, and renders interactive dashboards in the chat.

## Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Google Sheets Schema](#google-sheets-schema)
- [Setup and Deployment](#setup-and-deployment)
- [Environment Variables](#environment-variables)
- [Command Reference](#command-reference)
- [Behaviour Worth Knowing](#behaviour-worth-knowing)
- [Security Model](#security-model)
- [Dependencies](#dependencies)
- [Known Limitations](#known-limitations)
- [License](#license)

---

## Overview

Family members text expenses naturally (`15 Rewe`, `12,50 pizza`) or upload a receipt photo. The bot sends the input to a Groq-hosted vision model, validates the parsed result, and appends a row to a shared Google Sheet. Inline-keyboard dashboards show spending by category, user, and merchant with drill-down buttons.

Goals work the same way: `/goal Trip to Japan 5000 by December` — the model parses the type, amount, and deadline, and the bot saves it to a Goals sheet with a short unique ID.

The entire application is a single file, `api/webhook.py` (~1,890 lines), deployed as one Vercel Python function.

---

## Features

- **Natural language expense logging** — type an amount and where you spent it
- **Receipt scanning** — send a photo; the vision model reads total and merchant
- **Expense dashboard** — overview, by category, by user, by merchant, recent history (always scoped to the **current calendar month**, see [Behaviour Worth Knowing](#behaviour-worth-knowing))
- **User drill-down** — tap a family member for their category breakdown
- **Goal tracking** — financial goals, tasks, and to-dos with deadlines
- **Goal editing** — amount, date, note, or status via the `/editgoal` command
- **Undo** — remove your most recent expense or goal
- **Shared family access** — multiple Telegram users via an allowlist
- **Concurrency guards on two paths** — goal completion and `/undo` re-read the sheet before writing (see [Known Limitations](#known-limitations) for what is *not* guarded)

---

## Architecture

```
Telegram  ──webhook POST──▶  Vercel Python function  (api/webhook.py)
                                  │
                                  ├─ secret-token check     ─▶ 403 on mismatch
                                  ├─ allowlist + rate limit ─▶ silent 200 on reject
                                  │
                                  ├─ Text / image  ──▶  Groq Cloud API (vision model)
                                  │                      └─ JSON mode, reasoning hidden
                                  ├─ Validation    ──▶  amount + category / goal type
                                  └─ Google Sheets ──▶  gspread append / update
```

| Layer | Technology |
|---|---|
| Runtime | Python on Vercel (version not pinned — see below) |
| Handler | `BaseHTTPRequestHandler` subclass named `handler` (lowercase; Vercel resolves this exact name) |
| AI | Groq Cloud — `qwen/qwen3.6-27b` by default, override with `GROQ_MODEL` |
| Database | Google Sheets via `gspread` |
| UI | Telegram Bot API, inline keyboards |

There is **no `vercel.json`** in this repository. The deployment works through Vercel's zero-config detection of `api/*.py` plus `requirements.txt`. Function memory, region, and `maxDuration` are therefore all plan defaults, and no Python version is pinned anywhere (no `vercel.json`, `Pipfile`, `.python-version`, or `runtime.txt`).

---

## Google Sheets Schema

Both tabs and **both header rows must be created by hand before first use** — the bot never creates a tab or writes a header row. An `Expenses` tab with no header row will silently consume your first logged expense as its header, and that row can never be undone.

### `Expenses`

Written by `save_expense`, in this exact column order:

| # | Column | Type | Notes |
|---|---|---|---|
| A | `Date` | text | `YYYY-MM-DD HH:MM`, naive **server time (UTC on Vercel)** — no timezone handling anywhere |
| B | `Amount` | number | written numeric; see the formatting warning below |
| C | `Category` | text | one of the eight categories below |
| D | `Merchant` | text | model-supplied, unvalidated content |
| E | `Note` | text | model-supplied, unvalidated content |
| F | `User` | text | Telegram **display name**, not an ID |

Header matching is inconsistent in the current code: `Date` and `Amount` are matched case-insensitively against `date|timestamp|time` and `amount|price|cost|value`, but **`Category`, `Merchant`, and `User` must match exactly as capitalised** or the dashboard raises `KeyError` and the request returns HTTP 500. Column *order* is separately load-bearing for `save_expense` and `/undo` regardless of what the headers say. Do not add columns to the right, and do not leave trailing whitespace in a header.

### `Goals`

Written by `GoalsManager.add_goal`, 10 columns:

| # | Column | Type | Notes |
|---|---|---|---|
| A | `Created_Date` | text | `YYYY-MM-DD` |
| B | `Type` | text | one of the seven goal types below |
| C | `Goal_Name` | text | model-supplied |
| D | `Target_Amount` | number | |
| E | `Target_Date` | text | `YYYY-MM-DD`, or empty, or the literal string `null` when the model returns none |
| F | `Status` | text | `Pending` \| `Done` \| `In Progress` |
| G | `Created_By` | text | `str(telegram_user_id)`, falling back to display name if the ID is unavailable |
| H | `Goal_ID` | text | first 8 hex characters of a UUID4 (32 bits, no uniqueness check) |
| I | `Completed_Date` | text | written only by the ✅ button, not by `/editgoal ... status Done` |
| J | `Notes` | text | never populated at creation; only `/editgoal note` writes it |

The `Goals` tab has a dual contract: **reads bind by header name** while **writes bind by hard-coded column index**. Renaming or reordering a `Goals` header degrades reads to silent defaults while writes keep hitting the original physical columns.

### Taxonomies

**Categories** (`ALLOWED_CATEGORIES`): `Groceries`, `Food Takeout`, `Travel`, `Subscription`, `Investment`, `Household`, `Transport`, `Other`

**Goal types** (`ALLOWED_GOAL_TYPES`): `Financial`, `Vacation`, `Item`, `Activity`, `Skill`, `Task`, `Other`

### Cell-formatting warning

`Amount` and `Target_Amount` are written as numeric cells and read back as locale-formatted strings. Applying currency or thousands-separator formatting to those columns breaks `/goals` with a `ValueError`, and silently converts affected expenses to €0.00 in every dashboard total.

---

## Setup and Deployment

1. **Create the Google Sheet** with `Expenses` and `Goals` tabs and the exact header rows above.
2. **Create a Google Cloud service account**, enable the Sheets API, download the JSON key, and share the spreadsheet with the service-account email as an Editor.
3. **Create the bot** with [@BotFather](https://t.me/botfather) and keep the token.
4. **Deploy to Vercel** — import the repository; no build configuration is needed.
5. **Set all environment variables** in the Vercel dashboard (Settings → Environment Variables).
6. **Register the webhook**, including the secret token:

   ```
   https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<your-app>.vercel.app/api/webhook&secret_token=<WEBHOOK_SECRET_TOKEN>
   ```

7. **Register the command menu** with BotFather via `/setcommands`:

   ```
   start - Show help and the main menu
   help - Show help and the main menu
   summary - Expense dashboard for this month
   goal - Add a goal, e.g. /goal Japan 5000 by December
   goals - List pending goals
   editgoal - Edit a goal: /editgoal <id> <field> <value>
   undogoal - Delete your most recent goal
   undo - Delete your most recent expense
   share - Invite a family member
   ```

Find a Telegram user ID by messaging [@userinfobot](https://t.me/userinfobot).

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_TOKEN` | **yes** — fail-fast | Bot token from @BotFather |
| `GROQ_API_KEY` | **yes** — fail-fast | Groq Cloud API key |
| `GOOGLE_SHEET_ID` | **yes** — fail-fast | Sheets document ID from the URL |
| `GOOGLE_JSON_KEY` | **yes** — fail-fast | Full service-account JSON as an escaped single-line string |
| `WEBHOOK_SECRET_TOKEN` | **yes** — fail-fast | Random secret registered with `setWebhook` |
| `ALLOWED_USERS` | in practice yes | JSON array of permitted Telegram user IDs, e.g. `[123456, 789012]` |
| `BOT_USERNAME` | no | Bot username without `@`. Defaults to `""` |
| `GROQ_MODEL` | no | Groq model ID. Defaults to `qwen/qwen3.6-27b` |

Three traps worth stating explicitly:

- **`ALLOWED_USERS` does not fail fast.** If it is empty the bot logs a warning and starts normally, then silently rejects every user with HTTP 200. IDs must be JSON **numbers** — quoting them (`["123456"]`) parses fine but never matches Telegram's integer `user_id`, producing a silent total lockout.
- **`GROQ_MODEL` must be *unset*, not blank.** The default applies only when the key is absent; setting it to an empty string yields `model=""` and fails every LLM call as a generic "AI processing error".
- **`BOT_USERNAME` unset is not an error.** The bot boots and `/share` emits a dead link.

The model must be **vision-capable and support JSON mode** — the receipt path sends an image and every call requests `response_format={"type": "json_object"}`. Because the chosen default is a reasoning model, both call sites also pass `reasoning_format="hidden"`, which Groq requires when JSON mode is enabled.

---

## Command Reference

| Command | Description |
|---------|-------------|
| `/start` | Help text and the main menu |
| `/help` | Alias for `/start` |
| `/summary` | Expense dashboard for the current month |
| `/goal <text>` | Add a goal — note the **required space** after `/goal` |
| `/goals` | List pending goals with tap-to-open buttons |
| `/editgoal <id> <field> <value>` | Edit a goal (see fields below) |
| `/undogoal` | Delete your most recent goal |
| `/undo` | Delete the last expense row, if it is yours |
| `/share` | Invite text with your bot link |
| *(bare text)* | Logged as an expense |
| *(photo)* | Scanned as a receipt |

### `/editgoal` fields

| Field | Effect |
|---|---|
| `amount` | Updates `Target_Amount` |
| `date` | Updates `Target_Date`, future dates only |
| `note` / `notes` | Updates `Notes` |
| `status` | `Pending`, `Done`, or `In Progress` only |

Setting `status` to `In Progress` **removes the goal from `/goals` permanently** — every list view filters on `Status == 'Pending'`, so the goal becomes unreachable except by an ID that is no longer displayed. Setting `status Done` via the command does **not** populate `Completed_Date`; only the ✅ button does that.

---

## Behaviour Worth Knowing

These are real behaviours of the current code that read as bugs if you are watching logs.

- **Every dashboard view is hard-scoped to the current calendar month.** The `last_month`, `year`, and all-time branches exist but are unreachable — no keyboard passes a period. Combined with the naive UTC clock, European users see an empty dashboard for the first hours of each month.
- **Dashboards are cached for 120 seconds per lambda instance.** The 🔄 Refresh button does not force a re-read. A just-logged expense can be missing from a dashboard served by a different warm instance.
- **`/undo` only ever examines the final row of the sheet.** If a family member logs an expense after yours, yours becomes permanently un-undoable. `/undogoal`, by contrast, genuinely scans back for your most recent goal — the two commands are documented alike but behave differently.
- **Unrecognised slash commands are silently dropped** with HTTP 200 and no reply. So are photo captions, and every non-`message` update type (edited messages, channel posts, inline queries).
- **`/summary` sends two messages** — a loading placeholder, then the dashboard.
- **Bare `/goal` with no text produces no reply**, because routing requires the literal prefix `/goal ` including the trailing space.
- **The in-chat help text omits `/editgoal`**, which is discoverable only by tapping a goal or typing the command with too few arguments.
- **Display names longer than 20 characters break their own drill-down** — the button truncates the name but the drill view requires an exact match, so those users always get "Invalid selection."

---

## Security Model

See [SECURITY.md](SECURITY.md) for the full control list, verified against the code, along with the weaknesses that are known and not yet fixed.

In brief: every request must carry the correct `X-Telegram-Bot-Api-Secret-Token`, and every sender must appear in `ALLOWED_USERS`. Rejections after the secret check return a silent HTTP 200. Amounts and categories are validated against fixed bounds and allowlists before anything is written.

---

## Dependencies

| Package | Used for |
|---|---|
| `groq` | LLM client for both text and vision parsing |
| `gspread` | Google Sheets read/write |
| `google-auth` | Service-account credentials |
| `google-auth-oauthlib` | Pulled in transitively by `gspread`; not imported by this code |
| `requests` | Telegram Bot API calls |
| `pandas` | Dashboard aggregation |

**Every requirement is an unbounded `>=`, so builds are not reproducible.** Two specific hazards: `groq>=0.9.0` permits an install whose `create()` has no `reasoning_format` parameter, which this code passes on both call sites; and `pandas>=2.0.0` now resolves to pandas 3.x, a major version this code has never been validated against.

---

## Known Limitations

- **Ownership checks accept a display name as proof.** All four goal gates accept a match on either the stored ID *or* the sender's Telegram first name, which is a self-service field. `/undo`'s ownership check is name-only — no user ID is stored on expense rows at all. See SECURITY.md.
- **Race protection covers two paths, not all writes.** Only goal completion and `/undo` re-read before writing, and both compare a coarse timestamp. `delete_goal`, `/editgoal`, and `/undogoal` mutate a row by an index from a stale read with no check.
- **The rate limiter and both caches are per-instance.** On a serverless platform the effective rate ceiling scales with the number of warm instances.
- **A blank `Created_By` disables the ownership check entirely**, letting any allowlisted user mutate that goal.
- **Every allowlisted user can read every other member's complete financial history** through the dashboards. This is a deliberate design for a family bot, but it is not a privacy boundary.
- **Sheet reads are unbounded** — every operation pulls the full sheet into memory, and `/undo` and goal edits do two full reads per command.
- **`Goal_ID` is 32 bits with no uniqueness check**, and all lookups take the first matching row.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
