import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import json
import time
import random
from datetime import datetime, timedelta
import threading
import os
import hashlib
import yt_dlp
import requests
import re
from collections import defaultdict
from youtubesearchpython import VideosSearch
import asyncio
from concurrent.futures import ThreadPoolExecutor
import shutil

# ========== تنظیمات لاکچری ==========
BOT_TOKEN = "8793482183:AAEGUa7ZEURP26N34DzKvrudnndC3q7apBk"
ADMIN_IDS = [8680457924]
bot = telebot.TeleBot(BOT_TOKEN)

# ========== تنظیمات دانلود ==========
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(f"{DOWNLOAD_DIR}/music", exist_ok=True)

# ========== کلاس دیتابیس موزیک ==========
class MusicDatabase:
    def __init__(self):
        self.users = {}
        self.playlists = {}
        self.songs = {}
        self.user_songs = defaultdict(list)
        self.favorites = defaultdict(list)
        self.queues = {}
        self.analytics = defaultdict(int)
        self.settings = {
            "max_duration": 600,
            "max_songs_per_user": 500,
            "supported_formats": ["mp3", "m4a", "wav", "flac"],
            "quality": "high",
            "max_playlist_size": 100,
            "auto_download": True,
            "multi_processing": True
        }
        self._init_sample_data()
    
    def _init_sample_data(self):
        sample_songs = [
            {"id": "1", "title": "🌟 تاکسی - Taxi", "artist": "سهراب پاکزاد", "duration": 180, "quality": "320kbps", "size": "7.2MB", "likes": 1250},
            {"id": "2", "title": "💎 اسمان - Aseman", "artist": "حامد همایون", "duration": 210, "quality": "320kbps", "size": "8.5MB", "likes": 980},
            {"id": "3", "title": "🔥 بارون - Baroon", "artist": "محسن ابراهیم‌زاده", "duration": 195, "quality": "320kbps", "size": "7.8MB", "likes": 750},
            {"id": "4", "title": "✨ زمستان - Zemestan", "artist": "امیر تتلو", "duration": 225, "quality": "320kbps", "size": "9.1MB", "likes": 2100},
            {"id": "5", "title": "🎵 نیلوفر - Niloufar", "artist": "مهدی احمدوند", "duration": 165, "quality": "320kbps", "size": "6.5MB", "likes": 560},
            {"id": "6", "title": "🌊 دریا - Darya", "artist": "آرمین زارعی", "duration": 240, "quality": "320kbps", "size": "9.8MB", "likes": 1340},
        ]
        for song in sample_songs:
            self.songs[song["id"]] = song
        
        sample_playlists = {
            "1": {"name": "🎵 تاپ هیت‌های ایرانی", "songs": ["1", "2", "3", "4", "5"], "created_by": "admin", "likes": 450},
            "2": {"name": "💫 آروم بخش", "songs": ["2", "4", "6"], "created_by": "admin", "likes": 230},
        }
        for pid, playlist in sample_playlists.items():
            self.playlists[pid] = playlist
    
    def add_user(self, user_id, name, username=None):
        if user_id not in self.users:
            self.users[user_id] = {
                "name": name,
                "username": username,
                "role": "🎵 ادمین" if user_id in ADMIN_IDS else "🎧 کاربر",
                "joined": datetime.now().isoformat(),
                "last_seen": datetime.now().isoformat(),
                "songs_downloaded": 0,
                "playlists_created": 0,
                "favorites": 0,
                "level": "🟢 مبتدی",
                "premium": False,
                "premium_expiry": None
            }
            return True
        return False
    
    def get_user(self, user_id):
        return self.users.get(user_id)
    
    def add_song(self, title, artist, duration, quality="320kbps", size="0MB"):
        song_id = str(len(self.songs) + 1)
        song = {
            "id": song_id,
            "title": title,
            "artist": artist,
            "duration": duration,
            "quality": quality,
            "size": size,
            "likes": 0,
            "downloads": 0,
            "created": datetime.now().isoformat()
        }
        self.songs[song_id] = song
        return song
    
    def get_stats(self):
        total_users = len(self.users)
        total_songs = len(self.songs)
        total_playlists = len(self.playlists)
        total_downloads = sum(user.get("songs_downloaded", 0) for user in self.users.values())
        
        return {
            "total_users": total_users,
            "total_songs": total_songs,
            "total_playlists": total_playlists,
            "total_downloads": total_downloads,
            "premium_users": len([u for u in self.users.values() if u.get("premium", False)]),
            "top_songs": sorted(self.songs.values(), key=lambda x: x.get("likes", 0), reverse=True)[:5],
            "uptime": self.get_uptime()
        }
    
    def get_uptime(self):
        seconds = int(time.time() - self.settings.get("uptime", time.time()))
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        return f"{days}d {hours}h {minutes}m"

db = MusicDatabase()

# ========== ابزارهای دانلود موزیک ==========
class MusicDownloader:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.active_downloads = {}
    
    def search_song(self, query):
        try:
            videos_search = VideosSearch(query, limit=10)
            results = videos_search.result()
            songs = []
            
            for video in results.get('result', []):
                duration = video.get('duration', '0:00')
                duration_seconds = self._parse_duration(duration)
                
                songs.append({
                    "id": video.get('id'),
                    "title": video.get('title'),
                    "duration": duration_seconds,
                    "duration_str": duration,
                    "channel": video.get('channel', {}).get('name', 'Unknown'),
                    "views": video.get('viewCount', {}).get('short', '0'),
                    "thumbnail": video.get('thumbnails', [{}])[-1].get('url', ''),
                    "url": f"https://youtube.com/watch?v={video.get('id')}"
                })
            
            return songs
        except Exception as e:
            print(f"Search error: {e}")
            return []
    
    def _parse_duration(self, duration_str):
        try:
            parts = duration_str.split(':')
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            return 0
        except:
            return 0
    
    def download_song(self, url, quality="high"):
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '320',
                }],
                'outtmpl': f'{DOWNLOAD_DIR}/music/%(title)s.%(ext)s',
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'extractaudio': True,
                'audioformat': 'mp3',
                'restrictfilenames': True,
            }
            
            if quality == "high":
                ydl_opts['postprocessors'][0]['preferredquality'] = '320'
            elif quality == "medium":
                ydl_opts['postprocessors'][0]['preferredquality'] = '192'
            else:
                ydl_opts['postprocessors'][0]['preferredquality'] = '128'
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                mp3_filename = filename.rsplit('.', 1)[0] + '.mp3'
                
                if os.path.exists(mp3_filename):
                    size = os.path.getsize(mp3_filename) / (1024 * 1024)
                    duration = info.get('duration', 0)
                    
                    return {
                        "success": True,
                        "filename": mp3_filename,
                        "title": info.get('title', 'Unknown'),
                        "artist": info.get('uploader', 'Unknown'),
                        "duration": duration,
                        "size": f"{size:.1f}MB",
                        "path": mp3_filename
                    }
            
            return {"success": False, "error": "دانلود ناموفق"}
        except Exception as e:
            print(f"Download error: {e}")
            return {"success": False, "error": str(e)}
    
    def download_from_youtube(self, url, callback=None):
        def _download():
            result = self.download_song(url)
            if callback:
                callback(result)
            return result
        
        future = self.executor.submit(_download)
        return future

downloader = MusicDownloader()

# ========== کیبوردهای لاکچری ==========
def music_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🔍 جستجوی موزیک", callback_data="music_search"),
        InlineKeyboardButton("📥 دانلود", callback_data="music_download"),
        InlineKeyboardButton("🎵 پلی‌لیست‌ها", callback_data="music_playlists"),
        InlineKeyboardButton("⭐ علاقه‌مندی‌ها", callback_data="music_favorites"),
        InlineKeyboardButton("🎧 در حال پخش", callback_data="music_nowplaying"),
        InlineKeyboardButton("📊 آمار", callback_data="music_stats"),
        InlineKeyboardButton("📁 کتابخانه", callback_data="music_library"),
        InlineKeyboardButton("💎 پریمیوم", callback_data="music_premium"),
        InlineKeyboardButton("👤 پروفایل", callback_data="music_profile"),
        InlineKeyboardButton("🎤 تاپ چارت", callback_data="music_charts"),
        InlineKeyboardButton("🔄 بروزرسانی", callback_data="music_refresh"),
        InlineKeyboardButton("🆘 راهنما", callback_data="music_help")
    )
    return keyboard

def playlist_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("➕ ساخت پلی‌لیست", callback_data="playlist_create"),
        InlineKeyboardButton("📋 پلی‌لیست‌های من", callback_data="playlist_mine"),
        InlineKeyboardButton("🔥 محبوب‌ترین", callback_data="playlist_popular"),
        InlineKeyboardButton("⭐ پلی‌لیست‌های پیشنهادی", callback_data="playlist_suggested")
    )
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="music_main"))
    return keyboard

def song_actions(song_id):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("▶️ پخش", callback_data=f"song_play_{song_id}"),
        InlineKeyboardButton("⬇️ دانلود", callback_data=f"song_download_{song_id}"),
        InlineKeyboardButton("❤️ لایک", callback_data=f"song_like_{song_id}"),
        InlineKeyboardButton("⭐ افزودن به علاقه‌مندی‌ها", callback_data=f"song_favorite_{song_id}")
    )
    keyboard.add(
        InlineKeyboardButton("📋 افزودن به پلی‌لیست", callback_data=f"song_addplaylist_{song_id}"),
        InlineKeyboardButton("🔗 اشتراک‌گذاری", callback_data=f"song_share_{song_id}"),
        InlineKeyboardButton("🎵 مشابه", callback_data=f"song_similar_{song_id}"),
        InlineKeyboardButton("📊 اطلاعات", callback_data=f"song_info_{song_id}")
    )
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="music_library"))
    return keyboard

# ========== مدیریت کالبک‌ها ==========
@bot.callback_query_handler(func=lambda call: True)
def music_callback(call):
    user_id = call.from_user.id
    
    # ===== منوی اصلی =====
    if call.data == "music_main":
        show_main_menu(call)
    
    # ===== جستجوی موزیک =====
    elif call.data == "music_search":
        bot.answer_callback_query(call.id, "🔍 لطفاً نام آهنگ را وارد کنید")
        bot.send_message(
            call.message.chat.id,
            "🎵 **جستجوی موزیک**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "لطفاً نام آهنگ یا خواننده را ارسال کنید:\n\n"
            "💡 مثال: `تاکسی سهراب پاکزاد`",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 بازگشت", callback_data="music_main")
            )
        )
    
    # ===== دانلود =====
    elif call.data == "music_download":
        bot.answer_callback_query(call.id, "📥 لطفاً لینک یوتیوب را ارسال کنید")
        bot.send_message(
            call.message.chat.id,
            "📥 **دانلود موزیک از یوتیوب**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "لطفاً لینک ویدیوی یوتیوب را ارسال کنید:\n\n"
            "💡 مثال: `https://youtube.com/watch?v=...`\n\n"
            "⭐ **کیفیت‌های موجود:**\n"
            "• 🎵 320kbps (بالاترین کیفیت)\n"
            "• 🎵 192kbps (کیفیت خوب)\n"
            "• 🎵 128kbps (معمولی)",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 بازگشت", callback_data="music_main")
            )
        )
    
    # ===== پلی‌لیست‌ها =====
    elif call.data == "music_playlists":
        show_playlists(call)
    
    # ===== علاقه‌مندی‌ها =====
    elif call.data == "music_favorites":
        show_favorites(call)
    
    # ===== در حال پخش =====
    elif call.data == "music_nowplaying":
        show_now_playing(call)
    
    # ===== آمار =====
    elif call.data == "music_stats":
        show_stats(call)
    
    # ===== کتابخانه =====
    elif call.data == "music_library":
        show_library(call)
    
    # ===== پریمیوم =====
    elif call.data == "music_premium":
        show_premium(call)
    
    # ===== پروفایل =====
    elif call.data == "music_profile":
        show_profile(call)
    
    # ===== تاپ چارت =====
    elif call.data == "music_charts":
        show_charts(call)
    
    # ===== بروزرسانی =====
    elif call.data == "music_refresh":
        stats = db.get_stats()
        bot.answer_callback_query(call.id, "🔄 بروزرسانی شد!")
        bot.edit_message_text(
            f"✅ **بروزرسانی انجام شد!**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎵 آهنگ‌ها: `{stats['total_songs']}`\n"
            f"👥 کاربران: `{stats['total_users']}`\n"
            f"📥 دانلودها: `{stats['total_downloads']}`\n"
            f"📋 پلی‌لیست‌ها: `{stats['total_playlists']}`\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=music_menu(),
            parse_mode='Markdown'
        )
    
    # ===== راهنما =====
    elif call.data == "music_help":
        show_help(call)
    
    # ===== پلی‌لیست =====
    elif call.data == "playlist_create":
        bot.answer_callback_query(call.id, "📝 نام پلی‌لیست را وارد کنید")
        bot.send_message(
            call.message.chat.id,
            "📝 **ساخت پلی‌لیست جدید**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "لطفاً نام پلی‌لیست را ارسال کنید:\n\n"
            "💡 مثال: `🎵 آهنگ‌های آرام`",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 بازگشت", callback_data="music_playlists")
            )
        )
    
    elif call.data == "playlist_mine":
        show_my_playlists(call)
    
    elif call.data == "playlist_popular":
        show_popular_playlists(call)
    
    # ===== عملیات آهنگ =====
    elif call.data.startswith("song_play_"):
        song_id = call.data.split("_")[2]
        song = db.songs.get(song_id)
        if song:
            bot.answer_callback_query(call.id, f"▶️ در حال پخش {song['title']}")
            bot.send_message(
                call.message.chat.id,
                f"🎵 **در حال پخش:**\n"
                f"🎤 **نام:** {song['title']}\n"
                f"👤 **خواننده:** {song['artist']}\n"
                f"⏱ **مدت:** {song['duration']} ثانیه\n"
                f"📊 **کیفیت:** {song['quality']}\n"
                f"📦 **حجم:** {song['size']}\n"
                f"❤️ **لایک‌ها:** {song['likes']}\n\n"
                f"📌 **لینک پخش (محلی):** `/play_{song_id}`",
                parse_mode='Markdown'
            )
    
    elif call.data.startswith("song_download_"):
        song_id = call.data.split("_")[2]
        song = db.songs.get(song_id)
        if song:
            bot.answer_callback_query(call.id, f"⬇️ در حال دانلود {song['title']}")
            bot.send_message(
                call.message.chat.id,
                f"⬇️ **دانلود آهنگ**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎤 **نام:** {song['title']}\n"
                f"👤 **خواننده:** {song['artist']}\n"
                f"📦 **حجم:** {song['size']}\n"
                f"📊 **کیفیت:** {song['quality']}\n\n"
                f"✅ لطفاً منتظر بمانید...\n"
                f"📌 **بعد از دانلود:** `/download_{song_id}`",
                parse_mode='Markdown'
            )
    
    elif call.data.startswith("song_like_"):
        song_id = call.data.split("_")[2]
        song = db.songs.get(song_id)
        if song:
            song['likes'] = song.get('likes', 0) + 1
            bot.answer_callback_query(call.id, "❤️ لایک شد!")
            bot.edit_message_text(
                f"🎵 **{song['title']}**\n"
                f"❤️ لایک‌ها: {song['likes']}\n"
                f"👤 **خواننده:** {song['artist']}\n"
                f"⏱ **مدت:** {song['duration']} ثانیه",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=song_actions(song_id),
                parse_mode='Markdown'
            )
    
    elif call.data.startswith("song_favorite_"):
        song_id = call.data.split("_")[2]
        song = db.songs.get(song_id)
        if song and song_id not in db.favorites[user_id]:
            db.favorites[user_id].append(song_id)
            bot.answer_callback_query(call.id, f"⭐ به علاقه‌مندی‌ها اضافه شد!")
            bot.send_message(
                call.message.chat.id,
                f"⭐ **{song['title']}** به علاقه‌مندی‌های شما اضافه شد!",
                parse_mode='Markdown'
            )
    
    elif call.data == "music_profile":
        show_profile(call)
    
    elif call.data.startswith("song_info_"):
        song_id = call.data.split("_")[2]
        song = db.songs.get(song_id)
        if song:
            text = f"""
📊 **اطلاعات آهنگ**
━━━━━━━━━━━━━━━━━━━━━━
🎵 **نام:** {song['title']}
🎤 **خواننده:** {song['artist']}
⏱ **مدت:** {song['duration']} ثانیه
📊 **کیفیت:** {song['quality']}
📦 **حجم:** {song['size']}
❤️ **لایک‌ها:** {song.get('likes', 0)}
📥 **دانلودها:** {song.get('downloads', 0)}
🆔 **شناسه:** `{song['id']}`
📅 **تاریخ اضافه:** {song.get('created', 'نامشخص')}
━━━━━━━━━━━━━━━━━━━━━━
"""
            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=song_actions(song_id),
                parse_mode='Markdown'
            )

# ========== توابع نمایش ==========
def show_main_menu(call):
    user = db.get_user(call.from_user.id)
    stats = db.get_stats()
    
    text = f"""
🎵 **پنل موزیک Luffy Ultra** 🎵
━━━━━━━━━━━━━━━━━━━━━━
👤 **کاربر:** {call.from_user.first_name}
🎧 **نقش:** {user['role'] if user else '🎧 کاربر'}
📊 **آهنگ‌ها:** `{stats['total_songs']}`
📋 **پلی‌لیست‌ها:** `{stats['total_playlists']}`
👥 **کاربران:** `{stats['total_users']}`
📥 **دانلودها:** `{stats['total_downloads']}`
⏱ **آپتایم:** `{stats['uptime']}`
━━━━━━━━━━━━━━━━━━━━━━

🌟 **خوش آمدید!** از منوی زیر استفاده کنید:
"""
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=music_menu(),
        parse_mode='Markdown'
    )
    bot.answer_callback_query(call.id, "🎵 پنل موزیک")

def show_playlists(call):
    playlists = db.playlists
    if not playlists:
        bot.edit_message_text(
            "📭 **هیچ پلی‌لیستی یافت نشد**",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=playlist_menu(),
            parse_mode='Markdown'
        )
        return
    
    text = "📋 **پلی‌لیست‌های موجود**\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    for pid, playlist in list(playlists.items())[:8]:
        text += f"{playlist['name']}\n"
        text += f"🎵 {len(playlist['songs'])} آهنگ | ❤️ {playlist.get('likes', 0)} لایک\n\n"
        keyboard.add(
            InlineKeyboardButton(f"▶️ {playlist['name'][:15]}", callback_data=f"playlist_view_{pid}")
        )
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
    bot.answer_callback_query(call.id, "📋 پلی‌لیست‌ها")

def show_favorites(call):
    user_id = call.from_user.id
    favorites = db.favorites.get(user_id, [])
    
    if not favorites:
        bot.edit_message_text(
            "⭐ **علاقه‌مندی‌های شما خالی است!**\n\n"
            "💡 برای افزودن آهنگ به علاقه‌مندی‌ها، روی دکمه ⭐ کلیک کنید.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=music_menu(),
            parse_mode='Markdown'
        )
        return
    
    text = "⭐ **علاقه‌مندی‌های شما**\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for song_id in favorites[:10]:
        song = db.songs.get(song_id)
        if song:
            text += f"🎵 **{song['title']}** - {song['artist']}\n"
            text += f"⏱ {song['duration']}s | ❤️ {song.get('likes', 0)}\n\n"
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=music_menu(),
        parse_mode='Markdown'
    )
    bot.answer_callback_query(call.id, "⭐ علاقه‌مندی‌ها")

def show_stats(call):
    stats = db.get_stats()
    text = f"""
📊 **آمار پنل موزیک**
━━━━━━━━━━━━━━━━━━━━━━
👥 **کاربران:** `{stats['total_users']}`
🎵 **آهنگ‌ها:** `{stats['total_songs']}`
📋 **پلی‌لیست‌ها:** `{stats['total_playlists']}`
📥 **دانلودها:** `{stats['total_downloads']}`
💎 **کاربران پریمیوم:** `{stats['premium_users']}`
⏱ **آپتایم:** `{stats['uptime']}`

🏆 **تاپ آهنگ‌ها:**
"""
    for i, song in enumerate(stats['top_songs'][:3], 1):
        text += f"{i}. 🎵 **{song['title']}** - {song['artist']} ❤️ {song.get('likes', 0)}\n"
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=music_menu(),
        parse_mode='Markdown'
    )
    bot.answer_callback_query(call.id, "📊 آمار")

def show_library(call):
    songs = list(db.songs.values())
    if not songs:
        bot.edit_message_text(
            "📁 **کتابخانه موسیقی خالی است!**",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=music_menu(),
            parse_mode='Markdown'
        )
        return
    
    text = "📁 **کتابخانه موسیقی**\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    for song in songs[:10]:
        text += f"🎵 **{song['title']}** - {song['artist']}\n"
        text += f"⏱ {song['duration']}s | ❤️ {song.get('likes', 0)}\n\n"
        keyboard.add(
            InlineKeyboardButton(f"▶️ {song['title'][:15]}", callback_data=f"song_play_{song['id']}"),
            InlineKeyboardButton(f"⬇️ دانلود", callback_data=f"song_download_{song['id']}")
        )
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
    bot.answer_callback_query(call.id, "📁 کتابخانه")

def show_premium(call):
    user = db.get_user(call.from_user.id)
    text = f"""
💎 **پریمیوم Luffy Ultra**
━━━━━━━━━━━━━━━━━━━━━━
{'✅' if user.get('premium', False) else '❌'} **وضعیت:** {('🟢 پریمیوم' if user.get('premium', False) else '🔴 معمولی')}

🌟 **مزایای پریمیوم:**
• 📥 دانلود نامحدود
• 🎵 کیفیت 320kbps
• 📋 پلی‌لیست نامحدود
• ⚡ دانلود همزمان ۵ آهنگ
• 🎧 پخش بدون تبلیغات
• 📱 پشتیبانی ۲۴/۷

💰 **قیمت‌ها:**
• 🗓️ ۱ ماهه: `۵۰,۰۰۰ تومان`
• 🗓️ ۳ ماهه: `۱۲۰,۰۰۰ تومان`
• 🗓️ ۱ ساله: `۴۰۰,۰۰۰ تومان`

📌 برای تهیه پریمیوم با ادمین تماس بگیرید:
@LuffySupport
━━━━━━━━━━━━━━━━━━━━━━
"""
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=music_menu(),
        parse_mode='Markdown'
    )
    bot.answer_callback_query(call.id, "💎 پریمیوم")

def show_profile(call):
    user = db.get_user(call.from_user.id)
    if not user:
        bot.answer_callback_query(call.id, "❌ کاربر یافت نشد!")
        return
    
    text = f"""
👤 **پروفایل کاربر**
━━━━━━━━━━━━━━━━━━━━━━
📛 **نام:** {user['name']}
🆔 **آیدی:** `{call.from_user.id}`
🎧 **نقش:** {user['role']}
📅 **عضویت:** {user['joined']}
📥 **آهنگ‌های دانلود شده:** {user.get('songs_downloaded', 0)}
📋 **پلی‌لیست‌های ساخته شده:** {user.get('playlists_created', 0)}
⭐ **علاقه‌مندی‌ها:** {len(db.favorites.get(call.from_user.id, []))}
💎 **پریمیوم:** {'✅ فعال' if user.get('premium', False) else '❌ غیرفعال'}
🏅 **سطح:** {user.get('level', '🟢 مبتدی')}
━━━━━━━━━━━━━━━━━━━━━━
"""
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=music_menu(),
        parse_mode='Markdown'
    )
    bot.answer_callback_query(call.id, "👤 پروفایل")

def show_charts(call):
    songs = list(db.songs.values())
    sorted_songs = sorted(songs, key=lambda x: x.get('likes', 0), reverse=True)[:10]
    
    if not sorted_songs:
        bot.edit_message_text(
            "📊 **تاپ چارت خالی است!**",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=music_menu(),
            parse_mode='Markdown'
        )
        return
    
    text = "🏆 **تاپ چارت هفته**\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    emojis = ["🥇", "🥈", "🥉"]
    
    for i, song in enumerate(sorted_songs):
        rank = f"{i+1}."
        if i < 3:
            rank = emojis[i]
        
        text += f"{rank} **{song['title']}**\n"
        text += f"   👤 {song['artist']} | ❤️ {song.get('likes', 0)} | ⏱ {song['duration']}s\n\n"
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=music_menu(),
        parse_mode='Markdown'
    )
    bot.answer_callback_query(call.id, "🏆 تاپ چارت")

def show_now_playing(call):
    text = """
🎧 **در حال پخش**
━━━━━━━━━━━━━━━━━━━━━━
🎵 **آهنگ:** هیچ آهنگی در حال پخش نیست
━━━━━━━━━━━━━━━━━━━━━━

📌 برای پخش آهنگ، روی دکمه ▶️ کلیک کنید.
"""
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=music_menu(),
        parse_mode='Markdown'
    )
    bot.answer_callback_query(call.id, "🎧 در حال پخش")

def show_help(call):
    text = """
🆘 **راهنمای پنل موزیک**
━━━━━━━━━━━━━━━━━━━━━━
🎵 **جستجوی موزیک:**
• نام آهنگ یا خواننده را ارسال کنید
• نتایج جستجو نمایش داده می‌شود

📥 **دانلود:**
• لینک یوتیوب را ارسال کنید
• کیفیت مورد نظر را انتخاب کنید
• آهنگ دانلود و در کتابخانه ذخیره می‌شود

📋 **پلی‌لیست‌ها:**
• پلی‌لیست جدید بسازید
• آهنگ‌ها را مدیریت کنید
• پلی‌لیست‌های محبوب را ببینید

⭐ **علاقه‌مندی‌ها:**
• آهنگ‌های مورد علاقه را ذخیره کنید
• دسترسی سریع به آهنگ‌ها

💎 **پریمیوم:**
• امکانات ویژه
• دانلود نامحدود
• کیفیت بالا

📌 **دستورات سریع:**
/start - منوی اصلی
/search [نام] - جستجو
/download [لینک] - دانلود
/playlist - پلی‌لیست‌ها
/favorites - علاقه‌مندی‌ها
/help - راهنما

📌 **پشتیبانی:** @LuffySupport
━━━━━━━━━━━━━━━━━━━━━━
"""
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=music_menu(),
        parse_mode='Markdown'
    )
    bot.answer_callback_query(call.id, "🆘 راهنما")

# ========== دستورات متنی ==========
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    name = message.from_user.first_name
    username = message.from_user.username
    
    db.add_user(user_id, name, username)
    stats = db.get_stats()
    
    welcome = f"""
🎵 **به پنل موزیک Luffy Ultra خوش آمدید!** 🎵
━━━━━━━━━━━━━━━━━━━━━━
👤 **کاربر:** {name}
🎧 **نقش:** {db.users[user_id]['role']}
🎵 **آهنگ‌ها:** `{stats['total_songs']}`
📋 **پلی‌لیست‌ها:** `{stats['total_playlists']}`
👥 **کاربران:** `{stats['total_users']}`
━━━━━━━━━━━━━━━━━━━━━━

🌟 **با این ربات می‌توانید:**
• 🎵 جستجو و دانلود موزیک
• 📋 ایجاد پلی‌لیست
• ⭐ ذخیره علاقه‌مندی‌ها
• 🎧 پخش آهنگ‌ها
• 💎 استفاده از امکانات پریمیوم

📌 از منوی زیر استفاده کنید:
"""
    bot.send_message(
        message.chat.id,
        welcome,
        reply_markup=music_menu(),
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['search'])
def search_command(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(
            message,
            "🎵 **جستجوی موزیک**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 **فرمت:** `/search [نام آهنگ یا خواننده]`\n\n"
            "💡 **مثال:** `/search تاکسی سهراب پاکزاد`",
            parse_mode='Markdown'
        )
        return
    
    query = args[1]
    bot.reply_to(message, f"🔍 در حال جستجوی **{query}**...")
    
    results = downloader.search_song(query)
    
    if not results:
        bot.reply_to(message, "❌ هیچ نتیجه‌ای یافت نشد!")
        return
    
    text = f"🎵 **نتایج جستجو برای:** {query}\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    for i, song in enumerate(results[:5], 1):
        text += f"{i}. **{song['title']}**\n"
        text += f"   👤 {song['channel']} | ⏱ {song['duration_str']} | 👁 {song['views']}\n\n"
        keyboard.add(
            InlineKeyboardButton(
                f"▶️ دانلود {i}", 
                callback_data=f"youtube_download_{song['id']}"
            )
        )
    
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="music_main"))
    
    bot.reply_to(message, text, reply_markup=keyboard, parse_mode='Markdown')

@bot.message_handler(commands=['download'])
def download_command(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(
            message,
            "📥 **دانلود موزیک**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 **فرمت:** `/download [لینک یوتیوب]`\n\n"
            "💡 **مثال:** `/download https://youtube.com/watch?v=...`",
            parse_mode='Markdown'
        )
        return
    
    url = args[1]
    bot.reply_to(message, "⏳ در حال دانلود... لطفاً صبر کنید...")
    
    def on_download_complete(result):
        if result.get("success"):
            song = db.add_song(
                result["title"],
                result["artist"],
                result["duration"],
                "320kbps",
                result["size"]
            )
            
            # ارسال فایل
            with open(result["path"], 'rb') as f:
                bot.send_audio(
                    message.chat.id,
                    f,
                    title=result["title"],
                    performer=result["artist"],
                    duration=result["duration"],
                    caption=f"✅ **دانلود کامل شد!**\n\n🎵 **{result['title']}**\n👤 {result['artist']}\n📦 {result['size']}",
                    parse_mode='Markdown'
                )
            
            # به‌روزرسانی آمار کاربر
            user = db.get_user(message.from_user.id)
            if user:
                user['songs_downloaded'] = user.get('songs_downloaded', 0) + 1
        else:
            bot.reply_to(message, f"❌ دانلود ناموفق: {result.get('error', 'خطای ناشناخته')}")
    
    downloader.download_from_youtube(url, on_download_complete)

@bot.message_handler(commands=['playlist'])
def playlist_command(message):
    show_playlist_menu(message)

@bot.message_handler(commands=['favorites'])
def favorites_command(message):
    user_id = message.from_user.id
    favorites = db.favorites.get(user_id, [])
    
    if not favorites:
        bot.reply_to(
            message,
            "⭐ **علاقه‌مندی‌های شما خالی است!**\n\n"
            "💡 برای افزودن آهنگ، روی دکمه ⭐ کلیک کنید.",
            parse_mode='Markdown'
        )
        return
    
    text = "⭐ **علاقه‌مندی‌های شما**\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for song_id in favorites[:10]:
        song = db.songs.get(song_id)
        if song:
            text += f"🎵 **{song['title']}** - {song['artist']}\n"
    
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['stats'])
def stats_command(message):
    stats = db.get_stats()
    text = f"""
📊 **آمار پنل موزیک**
━━━━━━━━━━━━━━━━━━━━━━
👥 **کاربران:** `{stats['total_users']}`
🎵 **آهنگ‌ها:** `{stats['total_songs']}`
📋 **پلی‌لیست‌ها:** `{stats['total_playlists']}`
📥 **دانلودها:** `{stats['total_downloads']}`
💎 **پریمیوم:** `{stats['premium_users']}`
⏱ **آپتایم:** `{stats['uptime']}`
━━━━━━━━━━━━━━━━━━━━━━
"""
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['profile'])
def profile_command(message):
    user = db.get_user(message.from_user.id)
    if not user:
        bot.reply_to(message, "❌ کاربر یافت نشد!")
        return
    
    text = f"""
👤 **پروفایل شما**
━━━━━━━━━━━━━━━━━━━━━━
📛 **نام:** {user['name']}
🆔 **آیدی:** `{message.from_user.id}`
🎧 **نقش:** {user['role']}
📅 **عضویت:** {user['joined']}
📥 **دانلودها:** {user.get('songs_downloaded', 0)}
⭐ **علاقه‌مندی‌ها:** {len(db.favorites.get(message.from_user.id, []))}
💎 **پریمیوم:** {'✅ فعال' if user.get('premium', False) else '❌ غیرفعال'}
━━━━━━━━━━━━━━━━━━━━━━
"""
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['help'])
def help_command(message):
    text = """
🆘 **راهنمای کامل**
━━━━━━━━━━━━━━━━━━━━━━
🎵 **دستورات اصلی:**
/start - منوی اصلی
/search [نام] - جستجوی موزیک
/download [لینک] - دانلود از یوتیوب
/playlist - پلی‌لیست‌ها
/favorites - علاقه‌مندی‌ها
/stats - آمار پنل
/profile - پروفایل
/help - راهنما

📌 **پشتیبانی:** @LuffySupport
━━━━━━━━━━━━━━━━━━━━━━
"""
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['premium'])
def premium_command(message):
    text = """
💎 **پریمیوم Luffy Ultra**
━━━━━━━━━━━━━━━━━━━━━━
🌟 **مزایا:**
• 📥 دانلود نامحدود
• 🎵 کیفیت 320kbps
• 📋 پلی‌لیست نامحدود
• ⚡ دانلود همزمان ۵ آهنگ
• 🎧 پخش بدون تبلیغات

💰 **قیمت‌ها:**
• 🗓️ ۱ ماهه: `۵۰,۰۰۰ تومان`
• 🗓️ ۳ ماهه: `۱۲۰,۰۰۰ تومان`
• 🗓️ ۱ ساله: `۴۰۰,۰۰۰ تومان`

📌 برای تهیه با ادمین تماس بگیرید:
@LuffySupport
━━━━━━━━━━━━━━━━━━━━━━
"""
    bot.reply_to(message, text, parse_mode='Markdown')

# ========== مدیریت پیام‌های معمولی ==========
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    text = message.text.lower()
    
    if text in ["سلام", "سلامی", "درود", "hi", "hello"]:
        bot.reply_to(
            message,
            f"🎵 سلام {message.from_user.first_name} جان! به پنل موزیک خوش آمدی! 🌟"
        )
    
    elif text in ["ممنون", "مرسی", "thanks"]:
        bot.reply_to(message, "🙏 خواهش می‌کنم! از همراهی شما خوشحالم! 🎵")
    
    elif text in ["کمک", "help", "راهنما"]:
        bot.reply_to(message, "🆘 برای راهنما، /help رو بزن!")
    
    elif text in ["آمار", "stats", "وضعیت"]:
        stats = db.get_stats()
        bot.reply_to(
            message,
            f"📊 **آمار پنل:**\n"
            f"🎵 {stats['total_songs']} آهنگ\n"
            f"👥 {stats['total_users']} کاربر\n"
            f"📋 {stats['total_playlists']} پلی‌لیست",
            parse_mode='Markdown'
        )
    
    elif "دانلود" in text and "youtube" in text:
        bot.reply_to(
            message,
            "📥 لطفاً از دستور `/download [لینک]` استفاده کنید.",
            parse_mode='Markdown'
        )
    
    elif any(word in text for word in ["موزیک", "آهنگ", "موسیقی", "ترانه"]):
        bot.reply_to(
            message,
            "🎵 برای جستجوی موزیک از `/search [نام]` استفاده کنید!",
            parse_mode='Markdown'
        )
    
    else:
        # اگر متن طولانی بود و شبیه لینک بود
        if "youtube.com" in text or "youtu.be" in text:
            bot.reply_to(
                message,
                "📥 لطفاً از دستور `/download [لینک]` برای دانلود استفاده کنید.",
                parse_mode='Markdown'
            )
        elif len(text) > 10:
            # جستجوی خودکار برای پیام‌های طولانی
            bot.reply_to(
                message,
                f"🔍 در حال جستجوی **{text[:30]}...**\n"
                f"💡 برای جستجوی دقیق‌تر از `/search [نام]` استفاده کنید.",
                parse_mode='Markdown'
            )
            # جستجوی خودکار
            results = downloader.search_song(text)
            if results:
                text_result = f"🎵 **نتایج جستجو:**\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
                for i, song in enumerate(results[:3], 1):
                    text_result += f"{i}. **{song['title']}** - {song['channel']}\n"
                bot.reply_to(message, text_result, parse_mode='Markdown')
        else:
            responses = [
                "🎵 متوجه نشدم! برای راهنما /help رو بزن.",
                "🎧 منظورت رو کامل متوجه نشدم! لطفاً واضح‌تر بگو.",
                "🎶 از منوی دکمه‌ها استفاده کن!",
                "🌟 برای جستجوی موزیک، /search رو بزن."
            ]
            bot.reply_to(message, random.choice(responses))

# ========== اجرا ==========
if __name__ == "__main__":
    print("=" * 70)
    print("🎵 Luffy Ultra Music Bot نسخه 5.0.0 🎵")
    print("=" * 70)
    print(f"🎵 تعداد آهنگ‌ها: {len(db.songs)}")
    print(f"📋 تعداد پلی‌لیست‌ها: {len(db.playlists)}")
    print(f"👥 ادمین‌ها: {ADMIN_IDS}")
    print("✅ برای شروع، /start رو بزن")
    print("=" * 70)
    
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=60)
        except Exception as e:
            print(f"❌ خطا: {e}")
            print("🔄 راه‌اندازی مجدد در 5 ثانیه...")
            time.sleep(5)
            continue