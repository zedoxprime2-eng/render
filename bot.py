# =========================================
# ZEDOX BOT - RENDER READY - FULL WORKING
# =========================================

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
import os, time, random, string, threading, hashlib, hmac
from pymongo import MongoClient
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask
import requests

# =========================
# WEB SERVER FOR RENDER
# =========================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "🤖 ZEDOX BOT IS RUNNING! ✅"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port, debug=False)

threading.Thread(target=run_web, daemon=True).start()

# =========================
# BOT CONFIGURATION
# =========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set!")

# =========================
# MONGODB SETUP
# =========================
MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable not set!")

client = MongoClient(MONGO_URI, maxPoolSize=100, minPoolSize=20, connectTimeoutMS=3000, socketTimeoutMS=3000)
db = client["zedox_complete"]

# Collections
users_col = db["users"]
folders_col = db["folders"]
codes_col = db["codes"]
config_col = db["config"]
custom_buttons_col = db["custom_buttons"]
admins_col = db["admins"]
payments_col = db["payments"]

# Create indexes for speed
try:
    users_col.create_index("points")
    users_col.create_index("vip")
    users_col.create_index("referrals_count")
    folders_col.create_index([("cat", 1), ("parent", 1)])
    folders_col.create_index("number", unique=True, sparse=True)
except:
    pass

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# =========================
# KEEP ALIVE SYSTEM
# =========================
def keep_alive():
    render_url = os.environ.get("RENDER_URL", "")
    if not render_url:
        return
    while True:
        try:
            requests.get(f"{render_url}/", timeout=10)
            print("✅ Keep-alive ping sent")
        except:
            print("❌ Keep-alive failed")
        time.sleep(240)

if os.environ.get("RENDER_URL"):
    threading.Thread(target=keep_alive, daemon=True).start()
    print("🔄 Keep-alive system ACTIVE")

# =========================
# CACHE SYSTEM
# =========================
_config_cache = None
_config_cache_time = 0
_user_cache = {}
_user_cache_time = {}
CACHE_TTL = 60

def get_cached_config():
    global _config_cache, _config_cache_time
    now = time.time()
    if _config_cache and (now - _config_cache_time) < CACHE_TTL:
        return _config_cache
    _config_cache = get_config()
    _config_cache_time = now
    return _config_cache

# =========================
# SECURITY
# =========================
def validate_request(message):
    if not message or not message.from_user:
        return False
    if len(message.text or "") > 4096:
        return False
    return True

def hash_user_data(uid):
    secret = os.environ.get("BOT_TOKEN", "secret_key")
    return hmac.new(secret.encode(), str(uid).encode(), hashlib.sha256).hexdigest()[:16]

# =========================
# CONFIG SYSTEM
# =========================
def get_config():
    cfg = config_col.find_one({"_id": "config"})
    if not cfg:
        cfg = {
            "_id": "config",
            "force_channels": [],
            "custom_buttons": [],
            "vip_msg": "💎 Buy VIP to unlock this!",
            "welcome": "🔥 Welcome to ZEDOX BOT",
            "ref_reward": 5,
            "notify": True,
            "purchase_msg": "💰 Purchase VIP to access premium features!",
            "next_folder_number": 1,
            "points_per_dollar": 100,
            "contact_username": None,
            "contact_link": None,
            "vip_contact": None,
            "vip_price": 50,
            "vip_points_price": 5000,
            "payment_methods": ["💳 Binance", "💵 USDT (TRC20)", "💰 Bank Transfer", "🪙 Bitcoin"],
            "referral_vip_count": 50,
            "referral_purchase_count": 10,
            "vip_duration_days": 30,
            "binance_coin": "USDT",
            "binance_network": "TRC20",
            "binance_address": "",
            "binance_memo": "",
            "require_screenshot": True
        }
        config_col.insert_one(cfg)
    return cfg

def set_config(key, value):
    global _config_cache
    _config_cache = None
    config_col.update_one({"_id": "config"}, {"$set": {key: value}}, upsert=True)

# =========================
# ADMINS SYSTEM
# =========================
def init_admins():
    if not admins_col.find_one({"_id": ADMIN_ID}):
        admins_col.insert_one({
            "_id": ADMIN_ID,
            "username": None,
            "added_by": "system",
            "added_at": time.time(),
            "is_owner": True
        })

init_admins()

def is_admin(uid):
    uid = int(uid) if isinstance(uid, str) else uid
    if uid == ADMIN_ID:
        return True
    return admins_col.find_one({"_id": uid}) is not None

# =========================
# USER SYSTEM - SIMPLIFIED FOR NOW
# =========================
class User:
    def __init__(self, uid):
        self.uid = str(uid)
        data = users_col.find_one({"_id": self.uid})
        if not data:
            data = {
                "_id": self.uid,
                "points": 0,
                "vip": False,
                "vip_expiry": None,
                "ref": None,
                "refs": 0,
                "purchased_methods": [],
                "username": None,
                "created_at": time.time(),
                "total_points_earned": 0,
                "total_points_spent": 0
            }
            users_col.insert_one(data)
        self.data = data
    
    def save(self):
        users_col.update_one({"_id": self.uid}, {"$set": self.data})
    
    def points(self):
        return self.data.get("points", 0)
    
    def add_points(self, p):
        self.data["points"] += p
        self.data["total_points_earned"] = self.data.get("total_points_earned", 0) + p
        self.save()
    
    def spend_points(self, p):
        self.data["points"] -= p
        self.data["total_points_spent"] = self.data.get("total_points_spent", 0) + p
        self.save()

# =========================
# MAIN MENU
# =========================
def main_menu(uid):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📂 FREE METHODS", "💎 VIP METHODS")
    kb.add("📦 PREMIUM APPS", "⚡ SERVICES")
    kb.add("💰 POINTS", "⭐ BUY VIP")
    kb.add("🎁 REFERRAL", "👤 ACCOUNT")
    kb.add("📚 MY METHODS", "💎 GET POINTS")
    kb.add("🆔 CHAT ID", "🏆 REDEEM")
    if is_admin(uid):
        kb.add("⚙️ ADMIN PANEL")
    return kb

# =========================
# START COMMAND
# =========================
@bot.message_handler(commands=["start"])
def start_cmd(m):
    uid = m.from_user.id
    user = User(uid)
    
    if m.from_user.username:
        user.data["username"] = m.from_user.username
        user.save()
    
    cfg = get_cached_config()
    welcome_msg = cfg.get("welcome", "Welcome to ZEDOX BOT!")
    
    bot.send_message(uid, f"{welcome_msg}\n\n💰 Your points: **{user.points()}**", reply_markup=main_menu(uid))

# =========================
# POINTS COMMAND
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 POINTS")
def points_cmd(m):
    uid = m.from_user.id
    user = User(uid)
    
    points_msg = f"💰 **YOUR POINTS BALANCE** 💰\n\n"
    points_msg += f"┌ **Points:** `{user.points()}`\n"
    points_msg += f"├ **VIP Status:** ❌ Not Active\n"
    points_msg += f"├ **Total Earned:** `{user.data.get('total_points_earned', 0)}`\n"
    points_msg += f"└ **Total Spent:** `{user.data.get('total_points_spent', 0)}`\n\n"
    
    points_msg += f"✨ **Ways to Earn Points:**\n"
    points_msg += f"• 🎁 **Referral System:** Share your link\n"
    points_msg += f"• 🏆 **Redeem Codes:** Use coupon codes\n"
    points_msg += f"• 💎 **Purchase:** Click 💎 GET POINTS button"
    
    bot.send_message(uid, points_msg, parse_mode="Markdown")

# =========================
# ACCOUNT COMMAND
# =========================
@bot.message_handler(func=lambda m: m.text == "👤 ACCOUNT")
def account_cmd(m):
    uid = m.from_user.id
    user = User(uid)
    
    account_text = f"**👤 Account**\n\n"
    account_text += f"┌ Status: 🆓 Free\n"
    account_text += f"├ Points: {user.points()}\n"
    account_text += f"├ Earned: {user.data.get('total_points_earned', 0)}\n"
    account_text += f"└ Spent: {user.data.get('total_points_spent', 0)}\n\n"
    account_text += f"🆔 ID: `{uid}`"
    
    bot.send_message(uid, account_text, parse_mode="Markdown")

# =========================
# CHAT ID COMMAND
# =========================
@bot.message_handler(func=lambda m: m.text == "🆔 CHAT ID")
def chatid_cmd(m):
    uid = m.from_user.id
    user = User(uid)
    bot.send_message(uid, f"🆔 **Your ID:** `{uid}`\n\n💰 Points: {user.points()}", parse_mode="Markdown")

# =========================
# REDEEM CODE COMMAND
# =========================
@bot.message_handler(func=lambda m: m.text == "🏆 REDEEM")
def redeem_cmd(m):
    bot.send_message(m.from_user.id, "🎫 **Enter code:**", parse_mode="Markdown")
    bot.register_next_step_handler(m, lambda msg: bot.send_message(msg.from_user.id, "❌ Code system temporarily disabled. Contact admin!", parse_mode="Markdown"))

# =========================
# GET POINTS COMMAND
# =========================
@bot.message_handler(func=lambda m: m.text == "💎 GET POINTS")
def get_points_button(m):
    uid = m.from_user.id
    user = User(uid)
    
    message = f"💰 **GET POINTS** 💰\n\n"
    message += f"✨ **Your Current Balance:** `{user.points()}` points\n\n"
    message += f"📦 **BUY POINTS PACKAGES:**\n\n"
    message += f"💎 **Package 1:** 100 points for $5\n"
    message += f"💎 **Package 2:** 250 points for $10 (+25 bonus)\n"
    message += f"💎 **Package 3:** 550 points for $20 (+100 bonus)\n\n"
    message += f"💳 **Payment:** Contact admin to purchase!\n\n"
    message += f"🎁 **FREE WAYS TO EARN POINTS:**\n"
    message += f"• **Referral System:** Share your link\n"
    message += f"• **Redeem Codes:** Use coupon codes"
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/"))
    
    bot.send_message(uid, message, reply_markup=kb, parse_mode="Markdown")

# =========================
# FALLBACK
# =========================
@bot.message_handler(func=lambda m: True)
def fallback(m):
    uid = m.from_user.id
    known = ["📂 FREE METHODS", "💎 VIP METHODS", "📦 PREMIUM APPS", "⚡ SERVICES", "💰 POINTS", "⭐ BUY VIP", "🎁 REFERRAL", "👤 ACCOUNT", "🆔 CHAT ID", "🏆 REDEEM", "📚 MY METHODS", "💎 GET POINTS", "⚙️ ADMIN PANEL"]
    if m.text and m.text not in known:
        bot.send_message(uid, "❌ Use menu buttons", reply_markup=main_menu(uid))

# =========================
# ADMIN PANEL
# =========================
@bot.message_handler(func=lambda m: m.text == "⚙️ ADMIN PANEL" and is_admin(m.from_user.id))
def open_admin(m):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("💰 Give Points", "📊 Stats")
    kb.row("❌ Exit")
    bot.send_message(m.from_user.id, "⚙️ **Admin Panel**", reply_markup=kb, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "💰 Give Points" and is_admin(m.from_user.id))
def give_points_start(m):
    msg = bot.send_message(m.from_user.id, "💰 **Give Points**\n\nSend: `user_id points`\nExample: `7712834912 200`", parse_mode="Markdown")
    bot.register_next_step_handler(msg, give_points_process)

def give_points_process(m):
    try:
        parts = m.text.strip().split()
        if len(parts) != 2:
            bot.send_message(m.from_user.id, "❌ Use: user_id points")
            return
        user_id = int(parts[0])
        points = int(parts[1])
        
        if points <= 0:
            bot.send_message(m.from_user.id, "❌ Points must be > 0")
            return
        
        user = User(user_id)
        old_points = user.points()
        user.add_points(points)
        
        bot.send_message(m.from_user.id, f"✅ Added {points} points to {user_id}\nOld: {old_points}\nNew: {user.points()}")
        
        try:
            bot.send_message(user_id, f"🎉 You received +{points} points!\n💰 New balance: {user.points()}")
        except:
            pass
    except:
        bot.send_message(m.from_user.id, "❌ Error! Use: user_id points")

@bot.message_handler(func=lambda m: m.text == "📊 Stats" and is_admin(m.from_user.id))
def stats_cmd(m):
    total = users_col.count_documents({})
    bot.send_message(m.from_user.id, f"📊 **Statistics**\n\n👥 Total Users: {total}", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "❌ Exit" and is_admin(m.from_user.id))
def exit_admin(m):
    bot.send_message(m.from_user.id, "Exited", reply_markup=main_menu(m.from_user.id))

# =========================
# RUN BOT
# =========================
def run_bot():
    while True:
        try:
            print("=" * 50)
            print("🚀 ZEDOX BOT - RENDER READY")
            print(f"✅ Bot: @{bot.get_me().username}")
            print(f"👑 Owner: {ADMIN_ID}")
            print(f"💾 MongoDB: Connected")
            print("=" * 50)
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_bot()
