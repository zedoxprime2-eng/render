import os
import time
import threading
from flask import Flask
import requests
import telebot
from pymongo import MongoClient

# Flask web server
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ ZEDOX BOT IS RUNNING!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_web, daemon=True).start()

# Bot configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
MONGO_URI = os.environ.get("MONGO_URI")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN missing!")
if not MONGO_URI:
    raise ValueError("MONGO_URI missing!")

# MongoDB connection
client = MongoClient(MONGO_URI)
db = client["zedox_complete"]
users_col = db["users"]

bot = telebot.TeleBot(BOT_TOKEN)

# Keep alive
def keep_alive():
    render_url = os.environ.get("RENDER_URL", "")
    while render_url:
        try:
            requests.get(render_url, timeout=5)
            print("✅ Keep alive")
        except:
            pass
        time.sleep(240)

threading.Thread(target=keep_alive, daemon=True).start()

# Start command
@bot.message_handler(commands=['start'])
def start_command(message):
    uid = str(message.from_user.id)
    user = users_col.find_one({"_id": uid})
    if not user:
        user = {"_id": uid, "points": 0, "username": message.from_user.username}
        users_col.insert_one(user)
    bot.send_message(message.chat.id, f"✅ Welcome!\n💰 Points: {user['points']}")

# Points command
@bot.message_handler(commands=['points'])
def points_command(message):
    uid = str(message.from_user.id)
    user = users_col.find_one({"_id": uid})
    points = user['points'] if user else 0
    bot.send_message(message.chat.id, f"💰 Your points: {points}")

# Admin give points
@bot.message_handler(commands=['give'])
def give_command(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        bot.send_message(message.chat.id, "❌ Admin only!")
        return
    try:
        parts = message.text.split()
        user_id = parts[1]
        points = int(parts[2])
        users_col.update_one({"_id": user_id}, {"$inc": {"points": points}})
        bot.send_message(message.chat.id, f"✅ Added {points} points to {user_id}")
    except:
        bot.send_message(message.chat.id, "❌ Use: /give user_id points")

# Stats
@bot.message_handler(commands=['stats'])
def stats_command(message):
    if str(message.from_user.id) == str(ADMIN_ID):
        total = users_col.count_documents({})
        bot.send_message(message.chat.id, f"📊 Total users: {total}")

print("=" * 40)
print("🚀 BOT STARTED!")
print(f"✅ Bot: @{bot.get_me().username}")
print("=" * 40)

bot.infinity_polling()
