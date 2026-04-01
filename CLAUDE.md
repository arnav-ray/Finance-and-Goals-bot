# CLAUDE.md — Finance and Goals Bot

## Project Overview

A serverless Telegram bot for family finance tracking and goal management. Deployed on Vercel. Uses Groq (Llama 4 Vision) for LLM parsing, Google Sheets as the database, and the Telegram Bot API as the UI.

## Architecture

- **Entry point:** `api/webhook.py` — single-file serverless handler
- **Hosting:** Vercel (function at `/api/webhook`)
- **AI:** Groq Cloud API with `meta-llama/llama-4-scout-17b-16e-instruct`
- **Database:** Google Sheets (two tabs: `Expenses`, `Goals`)
- **Interface:** Telegram Bot API (webhook mode)

## Key Classes and Functions

| Component | Location | Purpose |
|-----------|----------|---------|
| `DashboardEngine` | webhook.py | Expense analytics using pandas |
| `GoalsManager` | webhook.py | CRUD operations for goals sheet |
| `handle_expense_message` | webhook.py | Parses text/image → calls Groq → saves to Sheets |
| `handle_add_goal` | webhook.py | Parses goal text → calls Groq → saves to Sheets |
| `handle_callback_query` | webhook.py | Handles Telegram inline button presses |
| `do_POST` | webhook.py (Handler class) | Main webhook entry point |
| `sanitize_cell` | webhook.py | Prevents Google Sheets formula injection |
| `get_sheets_client` | webhook.py | Lazy-initializes gspread client |

## Google Sheets Schema

**Tab: Expenses**
| Date | Amount | Category | Merchant | Note | User |
|------|--------|----------|----------|------|------|

**Tab: Goals**
| Created_Date | Type | Goal_Name | Target_Amount | Target_Date | Status | Created_By | Goal_ID | Completed_Date | Notes |
|---|---|---|---|---|---|---|---|---|---|

## Required Environment Variables

```
TELEGRAM_TOKEN          Bot token from @BotFather
GROQ_API_KEY            Groq Cloud API key
GOOGLE_SHEET_ID         Google Sheets document ID
GOOGLE_JSON_KEY         Full service account JSON (as escaped string)
ALLOWED_USERS           JSON array of permitted Telegram user IDs e.g. [123456, 789012]
WEBHOOK_SECRET_TOKEN    Random secret registered with Telegram setWebhook
BOT_USERNAME            Telegram bot username (without @)
```

## Security Model

- All requests validated via `X-Telegram-Bot-Api-Secret-Token` header
- Both `message` and `callback_query` events check `ALLOWED_USERS`
- User-supplied strings sanitized with `sanitize_cell()` before writing to Sheets
- LLM inputs wrapped in delimiters to prevent prompt injection
- Google API scopes restricted to `spreadsheets` + `drive.file` only
- Financial data logged at DEBUG level only (not visible in production logs)
- Receipt images capped at 5MB before download
- Goal/expense input capped at 500 characters before LLM call

## Dependencies

```
groq
gspread
google-auth
google-auth-oauthlib
requests
pandas
```

## Deployment

1. Push to GitHub (connected to Vercel)
2. Set all environment variables in Vercel dashboard
3. Register webhook with secret token:
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=<VERCEL_URL>/api/webhook&secret_token=<WEBHOOK_SECRET_TOKEN>"
   ```
4. Verify webhook: `curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"`

## Known Limitations / Future Work

- In-process rate limiter is per-instance (Vercel can run multiple instances); effective limit is not global
- `ALLOWED_USERS` is parsed at cold start; adding or revoking a user requires a redeployment
- No external/global rate limiting beyond the in-process limiter
- Git history contains a receipt image (`IMG_20260128_175804.jpg`) that was removed from tracking; a full purge requires `git filter-branch` / BFG Repo Cleaner + force-push to main
