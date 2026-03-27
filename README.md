# Family Finance and Goals Bot

A serverless Telegram bot for family finance tracking and goal management. Send a text message or photo of a receipt — the bot parses it with an LLM, saves it to Google Sheets, and gives you interactive dashboards.

## Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Google Sheets Schema](#google-sheets-schema)
- [Setup and Deployment](#setup-and-deployment)
- [Environment Variables](#environment-variables)
- [Command Reference](#command-reference)
- [Security Model](#security-model)
- [Dependencies](#dependencies)
- [License](#license)

---

## Overview

Family members text expenses naturally (`15 Rewe`, `12,50 pizza`) or upload a receipt photo. The bot uses Groq's Llama 4 Vision to parse the input, validates the result, and appends a row to a shared Google Sheet. Interactive Telegram dashboards show spending by category, user, and merchant with drill-down buttons.

Goals work the same way: `/goal Trip to Japan 5000 by December` — the AI parses the type, amount, and deadline, and saves it to a Goals sheet with a unique ID.

---

## Features

- **Natural language expense logging** — just type the amount and where you spent it
- **Receipt scanning** — send a photo, the bot reads the total and merchant via vision LLM
- **Expense dashboard** — overview, by category, by user, by merchant, recent history
- **User drill-down** — tap a family member to see their category breakdown
- **Goal tracking** — financial goals, tasks, and to-dos with deadlines
- **Goal editing** — update amount, date, notes, or status inline
- **Undo** — delete your last expense or goal
- **Shared family access** — multiple Telegram users via allowlist
- **Race condition protection** — safe concurrent edits to shared sheets

---

## Architecture

```
Telegram user
    │  message / photo
    ▼
Vercel serverless function  (api/webhook.py)
    │
    ├─ Auth: X-Telegram-Bot-Api-Secret-Token header
    ├─ Auth: ALLOWED_USERS allowlist
    ├─ Rate limit: 15 req / 60s per user (in-process)
    │
    ├─ Text/image → Groq Cloud API (Llama 4 Vision)
    │               structured JSON response
    │
    ├─ Validate → sanitize → append row
    ▼
Google Sheets  (Expenses tab + Goals tab)
```

**Stack:**

| Component | Technology |
|-----------|-----------|
| Runtime | Python 3.9+ |
| Hosting | Vercel Serverless |
| AI | Groq Cloud — `meta-llama/llama-4-scout-17b-16e-instruct` |
| Database | Google Sheets (via gspread) |
| Interface | Telegram Bot API (webhook mode) |

---

## Google Sheets Schema

Create two tabs in your Google Sheet with these exact headers.

**Tab: `Expenses`**

| Date | Amount | Category | Merchant | Note | User |
|------|--------|----------|----------|------|------|
| YYYY-MM-DD HH:MM | float | string | string | string | string |

**Tab: `Goals`**

| Created_Date | Type | Goal_Name | Target_Amount | Target_Date | Status | Created_By | Goal_ID | Completed_Date | Notes |
|---|---|---|---|---|---|---|---|---|---|
| YYYY-MM-DD | string | string | float | YYYY-MM-DD | Pending | string | uuid8 | YYYY-MM-DD | string |

---

## Setup and Deployment

### 1. Create the Telegram bot

Message [@BotFather](https://t.me/BotFather) and use `/newbot`. Copy the token.

Set commands via `/setcommands`:
```
start - Show help and main menu
goal - Add a new goal
goals - View and manage all goals
summary - View expense dashboard
undo - Delete your last expense
undogoal - Delete your last goal
editgoal - Edit goal details
share - Invite family members
```

### 2. Create the Google Sheet

1. Create a new Google Sheet with two tabs: `Expenses` and `Goals`
2. Add the column headers from the schema above
3. Create a Google Cloud service account, download the JSON key
4. Share the sheet with the service account email address (Editor access)

### 3. Set up Groq

Create an account at [console.groq.com](https://console.groq.com) and generate an API key.

### 4. Deploy to Vercel

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
vercel --prod
```

Set all environment variables in the Vercel dashboard (Settings → Environment Variables).

### 5. Register the webhook

Generate a random secret (e.g. `openssl rand -hex 32`) and register it with Telegram:

```bash
curl "https://api.telegram.org/bot<TOKEN>/setWebhook\
?url=https://<YOUR_VERCEL_URL>/api/webhook\
&secret_token=<YOUR_SECRET>"
```

Verify it worked:
```bash
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

---

## Environment Variables

All variables are required unless noted.

| Variable | Description |
|----------|-------------|
| `TELEGRAM_TOKEN` | Bot token from @BotFather |
| `GROQ_API_KEY` | Groq Cloud API key |
| `GOOGLE_SHEET_ID` | Google Sheets document ID (from the URL) |
| `GOOGLE_JSON_KEY` | Full service account JSON as an escaped single-line string |
| `ALLOWED_USERS` | JSON array of permitted Telegram user IDs, e.g. `[123456, 789012]` |
| `WEBHOOK_SECRET_TOKEN` | Random secret registered with Telegram `setWebhook` — **required** |
| `BOT_USERNAME` | Bot username without `@`, e.g. `FamilyFinanceBot` |

Find your Telegram user ID by messaging [@userinfobot](https://t.me/userinfobot).

---

## Command Reference

| Command | Description |
|---------|-------------|
| `[text]` | Log an expense: `15 Rewe`, `12,50 pizza`, `655 ETF investment` |
| `[photo]` | Send a receipt photo — bot reads total and merchant |
| `/summary` | Open expense analytics dashboard |
| `/undo` | Delete your last expense |
| `/goal [text]` | Add a goal: `/goal Trip to Italy 2000 by June` |
| `/goals` | View and manage all goals |
| `/editgoal [id] [field] [value]` | Edit a goal field: `/editgoal a3f2b8c1 amount 3000` |
| `/undogoal` | Delete your last goal |
| `/share` | Get the bot invite link |
| `/start` | Show help and main menu |

### Expense examples

```
45 Rewe
12,50 pizza
655 ETF investment
24 Dominos
```

### Goal examples

```
/goal Emergency fund 10000
/goal Trip to Japan 5000 by December 2026
/goal Learn Spanish by summer
/goal Renew car insurance next month
/goal Buy new sofa 1500 by March 2027
```

### editgoal fields

| Field | Example |
|-------|---------|
| `amount` | `/editgoal a3f2b8c1 amount 3000` |
| `date` | `/editgoal a3f2b8c1 date 2027-06-30` |
| `note` | `/editgoal a3f2b8c1 note Booked flights!` |
| `status` | `/editgoal a3f2b8c1 status Done` |

---

## Security Model

### Authentication

- Every webhook POST is validated against `X-Telegram-Bot-Api-Secret-Token` before the body is read. The function raises a startup error if `WEBHOOK_SECRET_TOKEN` is not set.
- Both `message` and `callback_query` events check the sender's user ID against `ALLOWED_USERS`. Unauthorised requests return HTTP 200 silently to avoid leaking bot existence.

### Input handling

- User text is capped at 500 characters before being sent to the LLM.
- LLM input is wrapped in delimiters (`"""`) with an instruction to treat it as raw data, not instructions.
- All string fields written to Google Sheets are passed through `sanitize_cell()` to prevent formula injection (`=`, `+`, `-`, `@`, tab, carriage return prefixed with `'`).
- Expense amounts are validated as floats within `[0, 10000]`; goal amounts within `[0, 100000]`.
- Categories and goal types are validated against strict allowlists.
- Receipt images are checked for size (≤ 5 MB) before download.
- POST body is read up to 1 MB, capped using `Content-Length` with safe int parsing.

### Authorisation

- Goal ownership is enforced by storing the creator's Telegram user ID in the `Created_By` column. Only the creator can complete, delete, or edit their own goals.
- A best-effort per-user rate limiter (15 requests / 60 seconds, in-process) protects against abuse.

### Privacy

- Financial transaction data and AI responses are logged at `DEBUG` level only — not visible in production logs.
- Log messages use numeric Telegram user IDs, not display names.
- Google API scopes are restricted to `spreadsheets` and `drive.file` — no broad Drive access.

### Known limitations

- The rate limiter is in-process; Vercel may run multiple instances, so the effective limit is per-instance, not global.
- `ALLOWED_USERS` is parsed at cold start; adding or revoking a user requires a redeployment.
- Receipt images are transmitted to Groq's cloud API for parsing. Sensitive receipt content (names, addresses) leaves your infrastructure.

---

## Dependencies

```
groq>=0.9.0
gspread>=6.0.0
google-auth>=2.28.0
google-auth-oauthlib>=1.2.0
requests>=2.31.0
pandas>=2.0.0
```

Install with:
```bash
pip install -r requirements.txt
```

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).
