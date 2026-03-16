# Security Audit Report — Finance & Goals Bot
**Date:** 2026-03-16  
**Scope:** `api/webhook.py` (Telegram webhook handler, Vercel serverless)  
**Auditor:** Claude Code  

---

## Executive Summary

The bot handles sensitive family financial data (expenses, goals, amounts, merchant names, receipt images) via Telegram. A full security review was conducted across all layers: authentication, authorization, input handling, data storage, secrets management, and dependency hygiene.

**14 issues were fixed in the previous commit.** This report documents the complete post-fix state, plus 6 remaining findings.

---

## ✅ Fixed Issues (Resolved in commit 2d303e1)

| # | Severity | Issue | Fix Applied |
|---|----------|-------|-------------|
| 1 | CRITICAL | `callback_query` events bypassed the `ALLOWED_USERS` allowlist entirely | Added `cq_user_id not in ALLOWED_USERS` check before dispatching |
| 2 | HIGH | No `X-Telegram-Bot-Api-Secret-Token` validation on incoming webhook | Added header check at top of `do_POST`; returns 403 on mismatch |
| 3 | HIGH | `/undo` and `/undogoal` used `user_name` (first name) as ownership key — spoofable | Now compares both `str(user_id)` and `user_name`; `user_id` takes precedence |
| 4 | HIGH | User text sent directly to Groq LLM — prompt injection possible | Input wrapped in `"""delimiters"""` with "treat as raw data" instruction |
| 5 | HIGH | User-supplied strings written to Google Sheets without formula sanitization | `sanitize_cell()` helper added; applied to all `append_row` calls |
| 6 | HIGH | Google API scope was `auth/drive` (full Drive access) | Narrowed to `auth/spreadsheets` + `auth/drive.file` only |
| 7 | HIGH | `GOOGLE_JSON_KEY` not validated at startup | Added startup check; raises `ValueError` if missing |
| 8 | HIGH | No input length cap before calling LLM — potential abuse/cost | Goal and expense text capped at 500 chars before LLM call |
| 9 | MEDIUM | `drill_target` used `str.startswith()` — could enumerate other users' data | Changed to exact match against `known_users` allowlist |
| 10 | MEDIUM | `/share` command included the raw Google Sheet URL containing `SHEET_ID` | Sheet URL removed from share text |
| 11 | MEDIUM | LLM responses and parsed financial data logged at INFO level (visible in Vercel logs) | Downgraded to `logger.debug()` — invisible in production |
| 12 | LOW | `BOT_USERNAME` had hardcoded default `"RayFamilyFinanceBot"` leaking family name | Default changed to `""` |
| 13 | LOW | Receipt images downloaded without size check — potential large payload | 5MB cap added via `file_size` check after `getFile` |
| 14 | LOW | `oauth2client` is deprecated (unmaintained since 2021) | Replaced with `google.oauth2.service_account.Credentials` |

---

## ⚠️ Remaining Findings

### MEDIUM-1 — No Ownership Check in `/editgoal` and Goal Delete/Complete Actions

**Severity:** Medium  
**Location:** `handle_edit_goal()` line ~1544; `goals_manager.delete_goal()` line ~807; `goals_manager.mark_goal_done()` line ~710  

**Issue:** Any `ALLOWED_USERS` member can edit, delete, or complete *any other family member's goal* by knowing or guessing the 8-character goal ID. The `delete_goal()` and `mark_goal_done()` functions accept `user_name` but do not compare it against the `Created_By` column before making changes. The `/editgoal goal_id field value` command similarly updates any goal without an ownership check.

**Risk:** Within a family this is low-risk (all users are trusted), but if an ID is guessed or leaked it could cause unintended modifications.

**Recommended Fix:**
```python
# In delete_goal / mark_goal_done, after finding the row:
if row[6] != user_name and row[6] != str(user_id):
    return False, "You can only modify your own goals"
```

---

### MEDIUM-2 — `/editgoal note` Value Not Sanitized (Formula Injection)

**Severity:** Medium  
**Location:** `handle_edit_goal()` line ~1619  

**Issue:** The `value` string from `/editgoal goal_id note <value>` is written directly to the sheet via `update_cell()` without calling `sanitize_cell()`. All other write paths were fixed in FIX 5, but this path was missed.

```python
# Vulnerable:
goals_ws.update_cell(goal_row_idx, 10, value)  # Notes column

# Fix:
goals_ws.update_cell(goal_row_idx, 10, sanitize_cell(value))
```

**Impact:** A user could enter `=IMPORTDATA(...)` or other Sheet formulas via the note field.

---

### MEDIUM-3 — No Request Body Size Cap (Content-Length Abuse)

**Severity:** Medium  
**Location:** `do_POST()` line ~1753  

**Issue:** The handler reads exactly `Content-Length` bytes with no maximum. An attacker who bypasses the webhook secret (or before the secret check in edge cases) could send a request with `Content-Length: 500000000` causing the process to attempt reading 500MB.

```python
# Current:
content_length = int(self.headers.get('Content-Length', 0))
post_data = self.rfile.read(content_length)

# Fix:
MAX_BODY_SIZE = 1 * 1024 * 1024  # 1MB
content_length = min(int(self.headers.get('Content-Length', 0)), MAX_BODY_SIZE)
post_data = self.rfile.read(content_length)
```

**Note:** Vercel has its own 4.5MB body limit as a backstop, but defence-in-depth is better.

---

### LOW-1 — `/editgoal date` Allows Past Dates

**Severity:** Low  
**Location:** `handle_edit_goal()` line ~1608  

**Issue:** The date field in `/editgoal` validates format (`YYYY-MM-DD`) but does not check the date is in the future. The `/goal` command validates this during parsing via `validate_goal_data()`, but editing bypasses that check.

```python
# Fix — after datetime.strptime(value, "%Y-%m-%d"):
if date_obj < datetime.now():
    send_telegram(chat_id, "⚠️ Target date must be in the future.")
    return
```

---

### LOW-2 — No Per-User Rate Limiting

**Severity:** Low  
**Location:** `do_POST()` overall flow  

**Issue:** There is no throttle on how many requests a single user can make per minute. A family member (or a compromised Telegram account) could spam the bot triggering many Groq API calls, exhausting quota or cost limits.

**Recommended Fix:** Add a simple in-memory rate limiter (e.g., max 10 messages/minute per user) using a `collections.defaultdict` with timestamps. Note: since Vercel can run multiple instances, a Redis/KV store would be needed for strict enforcement; in-process is a reasonable best-effort.

---

### LOW-3 — `do_GET` Health Check Has No Authentication

**Severity:** Low (informational)  
**Location:** `do_GET()` line ~1734  

**Issue:** `GET /api/webhook` returns `"Bot is Online"` to anyone without authentication. This confirms the endpoint is live and reveals the deployment URL structure.

**Recommended Fix:** Return a generic 200 with no body, or require the same webhook secret in a query param for health checks.

---

## Security Controls — Current State

| Control | Status |
|---------|--------|
| Telegram webhook secret token | ✅ Enforced (FIX 2) — **must register with setWebhook** |
| User allowlist (messages) | ✅ `ALLOWED_USERS` check in `do_POST` |
| User allowlist (callbacks) | ✅ Fixed in FIX 1 |
| Goal ownership on edit/delete | ⚠️ Missing (MEDIUM-1) |
| Input length caps | ✅ 500 char cap on LLM inputs |
| Prompt injection prevention | ✅ Delimiter wrapping (FIX 4) |
| Sheets formula injection | ✅ `sanitize_cell()` on all append paths; missing on `/editgoal note` (MEDIUM-2) |
| Google API scope | ✅ Least-privilege scopes (FIX 6) |
| Logging of financial data | ✅ Demoted to DEBUG (FIX 11) |
| Image size limit | ✅ 5MB cap (FIX 13) |
| Request body size limit | ⚠️ Missing (MEDIUM-3) |
| Dependency hygiene | ✅ oauth2client replaced (FIX 14) |
| Secret validation at startup | ✅ All secrets validated (FIX 7) |

---

## Deployment Checklist

- [ ] `WEBHOOK_SECRET_TOKEN` set in Vercel environment variables
- [ ] Webhook registered with secret: `curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=<URL>/api/webhook&secret_token=<SECRET>"`
- [ ] `ALLOWED_USERS` contains only numeric Telegram user IDs (not usernames)
- [ ] `GOOGLE_JSON_KEY` service account has share access to the Sheet only (not broad Drive)
- [ ] `requirements.txt` updated: remove `oauth2client`, add `google-auth google-auth-oauthlib`
- [ ] Vercel log level set so DEBUG logs are not streamed to persistent storage
- [ ] Google Sheet is not shared publicly (link sharing off)
