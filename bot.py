from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pathlib import Path
import os
import requests
import asyncio
from asyncio import Lock
import py7zr
import secrets
import time
import random
import base64
import pymysql
import threading
from datetime import datetime, timedelta, date
from dotenv import load_dotenv

load_dotenv()

# ====================== تنظیمات ======================
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BALE_TOKEN = os.getenv("BALE_TOKEN", "")
BALE_BOT_USERNAME = os.getenv("BALE_BOT_USERNAME", "")
BALE_USER_ID = int(os.getenv("BALE_USER_ID", 0))
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
BASE_URL = os.getenv("BASE_URL", "https://tapi.bale.ai/bot")
SAVE_PATH = Path(os.getenv("SAVE_PATH", "/home/ceqzpcjs/public_html/Downbale"))
SAVE_PATH.mkdir(exist_ok=True)

DAILY_LIMIT = 1024 * 1024 * 1024
DANGEROUS_EXT = {'.php', '.phtml', '.html', '.htm', '.js', '.exe', '.bat', '.sh', '.py', '.pl', '.cgi', '.jsp', '.asp'}

# ====================== MySQL ======================
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", ""),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", ""),
}

# ====================== GitHub ======================
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_OWNER = os.getenv("GITHUB_OWNER", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")
GITHUB_API = "https://api.github.com"

from adminpanel import admin_captcha, show_admin_panel

upload_lock = Lock()
app = Client("large_file_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ====================== تابع get_db ======================
def get_db():
    return pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)

# ====================== ابتدایی‌سازی دیتابس ======================
def init_database():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS connections (
                    telegram_id BIGINT PRIMARY KEY,
                    bale_id BIGINT,
                    connected BOOLEAN DEFAULT FALSE,
                    daily_uploaded BIGINT DEFAULT 0,
                    total_uploaded BIGINT DEFAULT 0,
                    file_count BIGINT DEFAULT 0,
                    last_reset_date DATE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("SHOW COLUMNS FROM connections")
            existing = {row['Field'] for row in cur.fetchall()}

            columns = {
                'bale_id': 'BIGINT',
                'connected': 'BOOLEAN DEFAULT FALSE',
                'daily_uploaded': 'BIGINT DEFAULT 0',
                'total_uploaded': 'BIGINT DEFAULT 0',
                'file_count': 'BIGINT DEFAULT 0',
                'last_reset_date': 'DATE'
            }

            for col, definition in columns.items():
                if col not in existing:
                    cur.execute(f"ALTER TABLE connections ADD COLUMN {col} {definition}")
                    print(f"✅ ستون {col} اضافه شد.")

            conn.commit()
    print("✅ دیتابیس با موفقیت ابتدایی‌سازی شد.")

init_database()

# ====================== تابع get_expiration_minutes ======================
def get_expiration_minutes(size_mb: float) -> int:
    if size_mb < 100:   return 10
    elif size_mb < 300: return 20
    elif size_mb < 500: return 30
    elif size_mb < 700: return 40
    else:               return int(size_mb / 1000) * 60 + 60

# ====================== Polling بله ======================
def bale_polling():
    offset = 0
    while True:
        try:
            url = f"{BASE_URL}{BALE_TOKEN}/getUpdates?offset={offset}&timeout=30"
            resp = requests.get(url, timeout=40).json()
            if resp.get("ok"):
                for update in resp.get("result", []):
                    offset = update["update_id"] + 1
                    if "message" in update and "text" in update["message"]:
                        text = update["message"]["text"]
                        bale_chat_id = update["message"]["chat"]["id"]
                        if text.startswith("connect:Bale:"):
                            parts = text.split(":")
                            if len(parts) == 4:
                                tg_id = int(parts[2])
                                with get_db() as conn:
                                    with conn.cursor() as cur:
                                        cur.execute(
                                            "INSERT INTO connections (telegram_id, bale_id, connected) "
                                            "VALUES (%s, %s, TRUE) ON DUPLICATE KEY UPDATE bale_id=%s, connected=TRUE",
                                            (tg_id, bale_chat_id, bale_chat_id)
                                        )
                                        conn.commit()
                                requests.post(f"{BASE_URL}{BALE_TOKEN}/sendMessage", json={"chat_id": bale_chat_id, "text": "✅ اتصال با موفقیت انجام شد!"})
                                try:
                                    app.send_message(tg_id, "✅ اتصال به بله با موفقیت انجام شد!")
                                except:
                                    pass
        except:
            time.sleep(5)

# ====================== منوی اصلی ======================
async def get_user_status(tg_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM connections WHERE telegram_id=%s", (tg_id,))
            return cur.fetchone()

async def build_main_menu_text(row):
    if not row:
        status = "❌ متصل نیست"
        daily_mb = 0
        total_mb = 0
    else:
        status = "✅ متصل" if row.get("connected") else "❌ متصل نیست"
        daily_mb = (row.get("daily_uploaded") or 0) / (1024 * 1024)
        total_mb = (row.get("total_uploaded") or 0) / (1024 * 1024)

    remaining_mb = max(0, 1024 - daily_mb)
    percent = min(100, int((daily_mb / 1024) * 100))
    filled = int(percent / 10)
    bar = "█" * filled + "░" * (10 - filled)

    return (
        f"━━━ 🤖 👋 منوی اصلی ━━━\n\n"
        f"📤 فایل یا لینک خود را ارسال کنید.\n"
        f"🔒 فایل‌ها با رمز یکبار مصرف قوی رمزگذاری می‌شوند.\n\n"
        f"━━━━━━━ 📊 وضعیت حساب ━━━━━━━\n"
        f"🏷 پلن: رایگان\n"
        f"محدودیت روزانه : 1024 MB\n"
        f"وضعیت اتصال به بله : {status}\n"
        f"📅 مصرف امروز: [{bar}] {percent}%\n"
        f"   {daily_mb:.1f} MB از 1024 MB — باقی: {remaining_mb:.2f} MB\n"
        f"⏳ اعتبار لینک: 1 ساعت (1GB=1 H)\n\n"
        f"📜 قوانین: محتوای غیرقانونی ممنوع | مسئولیت فایل‌ها با کاربر است.\n\n"
        f"👇 فایل خود را ارسال کنید:"
    )

@app.on_message(filters.command("start"))
async def start_handler(client: Client, message: Message):
    tg_id = message.from_user.id
    row = await get_user_status(tg_id)
    text = await build_main_menu_text(row)

    buttons = []
    if row and row.get("connected"):
        buttons.append([InlineKeyboardButton("🔌 قطع اتصال به بله", callback_data="disconnect")])
    else:
        buttons.append([InlineKeyboardButton("🔗 اتصال به بله", callback_data="connect")])

    if tg_id == ADMIN_ID:
        buttons.append([InlineKeyboardButton("⚙️ پنل مدیریت", callback_data="admin_panel")])

    keyboard = InlineKeyboardMarkup(buttons)
    await message.reply_text(text, reply_markup=keyboard)

# ====================== Callback Query ======================
@app.on_callback_query()
async def callback_handler(client, callback_query):
    data = callback_query.data
    tg_id = callback_query.from_user.id
    msg = callback_query.message

    if data == "connect":
        random_code = secrets.token_hex(8).upper()
        code = f"connect:Bale:{tg_id}:{random_code}"
        await msg.edit_text(f"🔗 کد اتصال شما:\n\n`{code}`\n\nاین کد را برای @{BALE_BOT_USERNAME} بفرستید.")

    elif data == "disconnect":
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE connections SET connected=FALSE WHERE telegram_id=%s", (tg_id,))
                conn.commit()
        row = await get_user_status(tg_id)
        text = await build_main_menu_text(row)
        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 اتصال به بله", callback_data="connect")]
        ]))

    elif data == "admin_panel" and tg_id == ADMIN_ID:
        await show_admin_panel(client, callback_query)

    elif data == "reset_db" and tg_id == ADMIN_ID:
        a = random.randint(10, 30)
        b = random.randint(5, 20)
        admin_captcha[tg_id] = a + b
        await msg.edit_text(f"⚠️ **هشدار خطرناک!**\n\nریست کامل دیتابیس باعث حذف تمام اطلاعات می‌شود.\n\nبرای تأیید جواب این سوال را بنویس:\n\n`{a} + {b} = ?`")

    elif data == "back_to_start":
        row = await get_user_status(tg_id)
        text = await build_main_menu_text(row)
        buttons = []
        if row and row.get("connected"):
            buttons.append([InlineKeyboardButton("🔌 قطع اتصال به بله", callback_data="disconnect")])
        else:
            buttons.append([InlineKeyboardButton("🔗 اتصال به بله", callback_data="connect")])
        if tg_id == ADMIN_ID:
            buttons.append([InlineKeyboardButton("⚙️ پنل مدیریت", callback_data="admin_panel")])
        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("cancel:"):
        try:
            await msg.edit_text("❌ آپلود کنسل شد.\nفایل جزئی حذف شد.")
        except:
            pass

# ====================== دانلود فایل ======================
@app.on_message(
    (filters.document | filters.video | filters.audio | filters.voice | filters.photo) & filters.private
)
async def download_handler(client: Client, message: Message):
    tg_id = message.from_user.id

    file_name = getattr(message.document, "file_name", "") if message.document else ""
    ext = os.path.splitext(file_name)[1].lower()
    if ext in DANGEROUS_EXT:
        await message.reply_text("❌ این فرمت فایل به دلایل امنیتی مجاز نیست.")
        return

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT daily_uploaded, last_reset_date FROM connections WHERE telegram_id=%s", (tg_id,))
            row = cur.fetchone()
            today = date.today()
            if not row or row["last_reset_date"] != today:
                cur.execute("UPDATE connections SET daily_uploaded=0, last_reset_date=%s WHERE telegram_id=%s", (today, tg_id))
                conn.commit()
                daily_used = 0
            else:
                daily_used = row["daily_uploaded"] or 0

    if daily_used >= DAILY_LIMIT:
        await message.reply_text("❌ محدودیت روزانه شما (۱ گیگ) تمام شده است.")
        return

    await message.reply_text("📥 فایل دریافت شد، در حال پردازش...")

    if message.photo:
        if isinstance(message.photo, list):
            file_attr = message.photo[-1]
        else:
            file_attr = message.photo
    else:
        file_attr = message.document or message.video or message.audio or message.voice

    if not file_attr: 
        await message.reply_text("❌ فایل پشتیبانی نمی‌شود.")
        return

    file_name = getattr(file_attr, "file_name", f"file_{message.id}.jpg")
    destination = SAVE_PATH / file_name

    status = await message.reply_text(
        f"🚀 در حال دانلود `{file_name}`...",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ کنسل", callback_data=f"cancel:{message.id}")]])
    )

    status.start_time = time.time()
    status.prev_bytes = 0
    status.prev_time = time.time()

    try:
        await client.download_media(
            message=message,
            file_name=str(destination),
            progress=progress_callback,
            progress_args=(status, file_name, getattr(file_attr, "file_size", 0))
        )

        file_size = destination.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        await status.edit_text(f"✅ دانلود کامل شد ({file_size_mb:.1f} MB).")

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE connections 
                    SET daily_uploaded = daily_uploaded + %s,
                        total_uploaded = total_uploaded + %s,
                        file_count = file_count + 1
                    WHERE telegram_id=%s
                """, (file_size, file_size, tg_id))
                conn.commit()

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT bale_id, connected FROM connections WHERE telegram_id=%s", (tg_id,))
                row = cur.fetchone()

        bale_id = row["bale_id"] if row and row.get("connected") else None

        async with upload_lock:
            if file_size_mb <= 20 and bale_id:
                await upload_direct_to_bale(destination, file_name, status, client, message.chat.id, bale_id)
            else:
                await upload_to_github_codeload(destination, file_name, status, client, message.chat.id, tg_id)

    except Exception as e:
        await status.edit_text(f"❌ خطا: {str(e)}")

# ====================== پیصرفت دانلود ======================
async def progress_callback(current, total, status_msg, file_name, file_size):
    if total == 0: return
    percent = (current / total) * 100
    filled = int(percent / 10)
    bar = "█" * filled + "░" * (10 - filled)

    now = time.time()
    speed = (current - status_msg.prev_bytes) / (now - status_msg.prev_time + 0.001)
    status_msg.prev_bytes = current
    status_msg.prev_time = now

    speed_mb = speed / (1024 * 1024)
    eta = "—" if speed <= 0 else (f"{int((total-current)/speed)} ثانیه" if (total-current)/speed < 60 else f"{(total-current)/speed/60:.1f} دقیقه")

    try:
        await status_msg.edit_text(
            f"📥 **دریافت فایل از تلگرام**\n\n"
            f"[{bar}] {percent:.1f}%\n"
            f"📦 {current / (1024*1024):.1f} MB از {total / (1024*1024):.1f} MB\n"
            f"⚡ سرعت: {speed_mb:.2f} MB/s\n"
            f"⏱ زمان باقی‌مانده: {eta}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ کنسل", callback_data=f"cancel:{status_msg.id}")]])
        )
    except:
        pass

# ====================== آپلود به GitHub ======================
async def upload_to_github_codeload(file_path: Path, file_name: str, status_msg: Message, client, chat_id, user_id):
    try:
        password = secrets.token_urlsafe(64)
        zip_path = file_path.with_suffix(".7z")
        random_num = random.randint(100000, 999999)
        branch_name = f"user_{user_id}_{random_num}"

        await status_msg.edit_text("🗜 در حال فشرده‌سازی...")

        with py7zr.SevenZipFile(zip_path, mode='w', password=password) as z:
            z.write(file_path, arcname=file_path.name)

        await status_msg.edit_text("☁️ در حال آپلود به GitHub...")

        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

        repo_info = requests.get(f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}", headers=headers).json()
        default_branch = repo_info.get("default_branch", "main")

        ref = requests.get(f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/git/ref/heads/{default_branch}", headers=headers).json()
        base_sha = ref["object"]["sha"]

        requests.post(f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/git/refs", json={"ref": f"refs/heads/{branch_name}", "sha": base_sha}, headers=headers)

        with open(zip_path, "rb") as f:
            content = f.read()
        content_b64 = base64.b64encode(content).decode()

        blob_resp = requests.post(f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/git/blobs", json={"content": content_b64, "encoding": "base64"}, headers=headers)
        blob_sha = blob_resp.json()["sha"]

        tree_data = {"base_tree": base_sha, "tree": [{"path": zip_path.name, "mode": "100644", "type": "blob", "sha": blob_sha}]}
        tree_resp = requests.post(f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/git/trees", json=tree_data, headers=headers)
        tree_sha = tree_resp.json()["sha"]

        commit_data = {"message": f"Upload {file_name}", "tree": tree_sha, "parents": [base_sha]}
        commit_resp = requests.post(f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/git/commits", json=commit_data, headers=headers)
        commit_sha = commit_resp.json()["sha"]

        requests.patch(f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/git/refs/heads/{branch_name}", json={"sha": commit_sha}, headers=headers)

        download_link = f"https://codeload.github.com/{GITHUB_OWNER}/{GITHUB_REPO}/zip/refs/heads/{branch_name}"

        size_mb = file_path.stat().st_size / (1024 * 1024)
        minutes = get_expiration_minutes(size_mb)
        expire_time = datetime.now() + timedelta(minutes=minutes)
        expire_str = expire_time.strftime("%Y/%m/%d — %H:%M")

        telegram_text = f"━━━ 🟢 🟢 آپلود موفق! 🎉 ━━━\n\nفایل `{file_name}` با موفقیت آپلود شد.\n\n🔗 لینک: {download_link}\n\n🔑 رمز: `{password}`\n\n📦 حجم: {size_mb:.1f} MB\n⏳ اعتبار تا: {expire_str}"

        bale_text = f"✅ آپلود موفق\n\nفایل: {file_name}\n\nلینک: {download_link}\n\nرمز: {password}\n\nحجم: {size_mb:.1f} MB\nاعتبار: {expire_str}"

        await send_to_bale(bale_text)
        await client.send_message(chat_id, telegram_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="back_to_start")]]))
        await status_msg.edit_text("✅ پیام به تلگرام و بله ارسال شد.")

        if file_path.exists(): os.remove(file_path)
        if zip_path.exists(): os.remove(zip_path)

        asyncio.create_task(delete_branch_after_delay(branch_name, minutes * 60, client, chat_id))

    except Exception as e:
        await status_msg.edit_text(f"❌ خطا: {str(e)}")

async def upload_direct_to_bale(file_path: Path, file_name: str, status_msg: Message, client, chat_id, bale_id):
    try:
        url = f"{BASE_URL}{BALE_TOKEN}/sendDocument"
        with open(file_path, "rb") as f:
            files = {"document": (file_name, f)}
            data = {"chat_id": bale_id, "caption": f"📤 {file_name}"}
            response = requests.post(url, data=data, files=files, timeout=300)

        if response.status_code == 200:
            await status_msg.edit_text("✅ فایل به بله ارسال شد.")
            await client.send_message(chat_id, f"✅ فایل `{file_name}` مستقیم به بله شما ارسال شد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="back_to_start")]]))
        else:
            await status_msg.edit_text("❌ خطا در ارسال به بله")
    finally:
        if file_path.exists():
            os.remove(file_path)

async def send_to_bale(text: str):
    requests.post(f"{BASE_URL}{BALE_TOKEN}/sendMessage", json={"chat_id": BALE_USER_ID, "text": text})

async def delete_branch_after_delay(branch_name: str, delay_seconds: int, client, chat_id):
    await asyncio.sleep(delay_seconds)
    try:
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        requests.delete(f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/git/refs/heads/{branch_name}", headers=headers)
        report = f"✅ فایل با موفقیت از GitHub حذف شد.\nBranch: `{branch_name}`"
        await send_to_bale(report)
        await client.send_message(chat_id, report)
    except:
        pass

# ====================== شروع ربات ======================
print("✅ ربات کامل و نهایی در حال اجرا...")
threading.Thread(target=bale_polling, daemon=True).start()
app.run()