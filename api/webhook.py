from http.server import BaseHTTPRequestHandler
import json
import os
import requests
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from PIL import Image
from io import BytesIO

# --- CONFIGURATION ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
ALLOWED_USERS = json.loads(os.environ.get("ALLOWED_USERS", "[]"))

# --- SETUP CLIENTS ---
# 1. Configure AI (Using the model your project actually has)
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash') 

# 2. Configure Sheets
try:
    creds_dict = json.loads(os.environ.get("GOOGLE_JSON_KEY"))
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    gc = gspread.authorize(creds)
except Exception as e:
    print(f"Auth Error: {e}")

SYSTEM_PROMPT = """
Current Date: {date}
Categories: Groceries 🛒, Food Takeout 🍕, Travel ✈️, Subscription 📺, Investment 💰, Household 🏠, Transport 🚌.
Task: Parse input (text or image) into JSON: {{"amount": float, "category": str, "merchant": str, "note": str}}.
Rules: 
1. If no currency, assume EUR.
2. If category is ambiguous, use "Other".
3. Auto-fix merchant names.
4. Output JSON only.
"""

def send_telegram(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def get_telegram_file(file_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
    resp = requests.get(url).json()
    file_path = resp['result']['file_path']
    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
    file_data = requests.get(download_url).content
    return Image.open(BytesIO(file_data))

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data)
        except:
            self.send_response(200); self.end_headers(); return

        if 'message' not in data:
            self.send_response(200); self.end_headers(); return

        msg = data['message']
        chat_id = msg['chat']['id']
        user_id = msg.get('from', {}).get('id')
        
        # Security Check
        if user_id not in ALLOWED_USERS:
            self.send_response(200); self.end_headers(); return

        # Commands
        if 'text' in msg and msg['text'].startswith('/'):
            if msg['text'] == '/start':
                send_telegram(chat_id, "🤖 **Bot is Ready!**\nType `15 Lunch` or send a receipt.")
            self.send_response(200); self.end_headers(); return

        # Processing
        try:
            prompt = SYSTEM_PROMPT.format(date=datetime.now().strftime("%Y-%m-%d"))
            content = [prompt]

            if 'photo' in msg:
                send_telegram(chat_id, "👀 Scanning receipt...")
                image = get_telegram_file(msg['photo'][-1]['file_id'])
                content.append(image)
                content.append("Analyze this image.")
            elif 'text' in msg:
                content.append(f"Input: {msg['text']}")
            else:
                self.send_response(200); self.end_headers(); return

            # AI Call
            response = model.generate_content(content)
            clean_json = response.text.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(clean_json)
            
            amount = float(parsed.get('amount', 0))
            if amount > 0:
                sh = gc.open_by_key(SHEET_ID).sheet1
                sh.append_row([
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                    amount,
                    parsed.get('category', 'Other'),
                    parsed.get('merchant', 'Unknown'),
                    parsed.get('note', ''),
                    msg.get('from', {}).get('first_name', 'User')
                ])
                send_telegram(chat_id, f"✅ Saved *€{amount}* to *{parsed.get('category')}*")
            else:
                send_telegram(chat_id, "⚠️ I couldn't find an amount.")

        except Exception as e:
            print(f"Error: {e}")
            send_telegram(chat_id, "⚠️ Error. Try '15 Lunch'")

        self.send_response(200)
        self.end_headers()
