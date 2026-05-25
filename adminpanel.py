import os
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

load_dotenv()

ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

admin_captcha = {}

async def show_admin_panel(client, callback_query):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 ریست کامل دیتابیس", callback_data="reset_db")],
        [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_start")]
    ])
    await callback_query.message.edit_text("⚙️ **پنل مدیریت ادمین**", reply_markup=keyboard)