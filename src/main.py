# -*- coding: utf-8 -*-
"""
HostingBot — by Blac (@NottBlac)
"""
⁰
import telebot
from telebot import types
import subprocess
import os
import zipfile
import shutil
import time
from datetime import datetime, timedelta
import psutil
import sqlite3
import json
import logging
import re
import sys
import atexit
import hashlib
import threading
import queue
from pathlib import Path
import traceback
import socket

# ==================== CONFIGURATION ====================
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', '8537538760'))
ADMIN_ID = int(os.getenv('ADMIN_ID', '8537538760'))
BOT_USERNAME = os.getenv('BOT_USERNAME', '@NottBlac')
UPDATE_CHANNEL = os.getenv('UPDATE_CHANNEL', 'https://t.me/BlacScriptz')
OWNER_TG = 'https://t.me/NottBlac'

# Paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
DB_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DB_DIR, 'bot.db')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
PENDING_DIR = os.path.join(BASE_DIR, 'pending')
EXTRACT_DIR = os.path.join(BASE_DIR, 'extracted')
SITES_DIR = os.path.join(BASE_DIR, 'sites')   # ZIP website folders

# Limits
FREE_LIMIT = 5
SUB_LIMIT = 25
ADMIN_LIMIT = 999
OWNER_LIMIT = float('inf')

for d in [UPLOAD_DIR, DB_DIR, LOGS_DIR, PENDING_DIR, EXTRACT_DIR, SITES_DIR]:
    os.makedirs(d, exist_ok=True)

# ==================== PLATFORM AUTO-DETECT ====================
def detect_host_url():
    """Auto-detect the public URL based on platform environment variables."""
    # Render
    if os.environ.get('RENDER_EXTERNAL_URL'):
        return os.environ['RENDER_EXTERNAL_URL'].rstrip('/')
    if os.environ.get('RENDER_SERVICE_NAME'):
        name = os.environ['RENDER_SERVICE_NAME']
        return f"https://{name}.onrender.com"
    # Railway
    if os.environ.get('RAILWAY_PUBLIC_DOMAIN'):
        return f"https://{os.environ['RAILWAY_PUBLIC_DOMAIN']}".rstrip('/')
    if os.environ.get('RAILWAY_STATIC_URL'):
        return os.environ['RAILWAY_STATIC_URL'].rstrip('/')
    # Heroku
    if os.environ.get('HEROKU_APP_NAME'):
        return f"https://{os.environ['HEROKU_APP_NAME']}.herokuapp.com"
    # Koyeb
    if os.environ.get('KOYEB_PUBLIC_DOMAIN'):
        return f"https://{os.environ['KOYEB_PUBLIC_DOMAIN']}".rstrip('/')
    # Replit
    if os.environ.get('REPL_SLUG') and os.environ.get('REPL_OWNER'):
        return f"https://{os.environ['REPL_SLUG']}-{os.environ['REPL_OWNER']}.replit.app"
    # Fly.io
    if os.environ.get('FLY_APP_NAME'):
        return f"https://{os.environ['FLY_APP_NAME']}.fly.dev"
    # Manual override always wins if set
    manual = os.environ.get('HOST_URL', '').rstrip('/')
    if manual:
        return manual
    return None

HOST_URL = detect_host_url()

# ==================== FLASK ====================
from flask import Flask, send_file, jsonify, abort
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return """<html><head><title>HostingBot</title></head>
    <body style="font-family:Arial;text-align:center;background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;padding:50px;">
    <h1>HostingBot</h1><p>by <b>@NottBlac</b> — 30+ file types — Running</p></body></html>"""

@app.route('/file/<file_hash>')
def serve_file(file_hash):
    try:
        for uid in user_files:
            for fname, ftype in user_files[uid]:
                if hashlib.md5(f"{uid}_{fname}".encode()).hexdigest() == file_hash:
                    fpath = os.path.join(get_user_folder(uid), fname)
                    if os.path.exists(fpath):
                        return send_file(fpath, as_attachment=False)
        return "File not found", 404
    except Exception:
        return "Error", 500

@app.route('/s/<slug>')
@app.route('/s/<slug>/<path:subpath>')
def serve_site(slug, subpath='index.html'):
    """Serve ZIP-extracted websites at /s/<slug>/"""
    site_dir = os.path.join(SITES_DIR, slug)
    if not os.path.isdir(site_dir):
        return "Site not found", 404
    # Default to index.html
    if subpath == 'index.html' or not subpath:
        target = os.path.join(site_dir, 'index.html')
        if not os.path.exists(target):
            # Try to find any html file
            for f in os.listdir(site_dir):
                if f.endswith('.html'):
                    target = os.path.join(site_dir, f)
                    break
    else:
        target = os.path.join(site_dir, subpath)
    # Security: stay within site dir
    target = os.path.realpath(target)
    if not target.startswith(os.path.realpath(site_dir)):
        abort(403)
    if os.path.exists(target) and os.path.isfile(target):
        return send_file(target)
    return "Not found", 404

@app.route('/health')
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat(),
                    "users": len(active_users), "files": sum(len(f) for f in user_files.values()),
                    "platform": HOST_URL or "local"})

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

def get_file_url(uid, name):
    if not HOST_URL:
        return None
    fhash = hashlib.md5(f"{uid}_{name}".encode()).hexdigest()
    return f"{HOST_URL}/file/{fhash}"

def get_site_url(slug):
    if not HOST_URL:
        return None
    return f"{HOST_URL}/s/{slug}/"

# ==================== BOT ====================
bot = telebot.TeleBot(TOKEN)

# ==================== DATA ====================
scripts = {}
subscriptions = {}
user_files = {}
active_users = set()
admins = {ADMIN_ID, OWNER_ID}
pending = {}
bot_locked = False
shell_sessions = {}
exec_locks = {}
exec_locks_mutex = threading.Lock()
broadcast_pending = {}
# user_envs: uid -> {name: {KEY: VALUE}}
user_envs = {}
# site_slugs: uid -> {filename: slug}
site_slugs = {}
# clone_stats: key -> {users: set, files: int, runs: int}
clone_stats = {}
# waiting_slug: uid -> {'name': filename, 'uid': uid}
waiting_slug = {}
# waiting_env_key / waiting_env_val: for env set flow
waiting_env = {}  # uid -> {'step': 'key'|'val', 'name': filename, 'key': KEY}

# ==================== LOGGING ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'bot.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== DATABASE ====================
def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS subs (uid INTEGER PRIMARY KEY, expiry TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS files (uid INTEGER, name TEXT, type TEXT, PRIMARY KEY (uid, name))')
        c.execute('CREATE TABLE IF NOT EXISTS users (uid INTEGER PRIMARY KEY, name TEXT, username TEXT, first_seen TEXT, last_seen TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS admins (uid INTEGER PRIMARY KEY)')
        c.execute('CREATE TABLE IF NOT EXISTS pending (hash TEXT PRIMARY KEY, uid INTEGER, name TEXT, path TEXT, time TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS cmd_log (id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, cmd TEXT, time TEXT, output TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS user_envs (uid INTEGER, filename TEXT, key TEXT, value TEXT, PRIMARY KEY (uid, filename, key))')
        c.execute('CREATE TABLE IF NOT EXISTS site_slugs (uid INTEGER, filename TEXT, slug TEXT, PRIMARY KEY (uid, filename))')
        c.execute('INSERT OR IGNORE INTO admins VALUES (?)', (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins VALUES (?)', (ADMIN_ID,))
        conn.commit(); conn.close()
        logger.info("DB initialized")
    except Exception as e:
        logger.error(f"DB init error: {e}")

def clear_old_data():
    logger.info("Clearing old data on restart...")
    for key, info in list(scripts.items()):
        if info.get('process') and info['process'].poll() is None:
            try: kill_process_tree(info['process'].pid)
            except: pass
    scripts.clear()
    for d in [UPLOAD_DIR, EXTRACT_DIR, PENDING_DIR, SITES_DIR]:
        if os.path.exists(d): shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('DELETE FROM files')
        conn.execute('DELETE FROM pending')
        conn.execute('DELETE FROM cmd_log')
        conn.execute('DELETE FROM site_slugs')
        conn.commit(); conn.close()
    except: pass
    user_files.clear()
    pending.clear()
    site_slugs.clear()
    logger.info("Old data cleared")

def load_data():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT uid, expiry FROM subs')
        for uid, exp in c.fetchall():
            try: subscriptions[uid] = {'expiry': datetime.fromisoformat(exp)}
            except: pass
        c.execute('SELECT uid, name, type FROM files')
        for uid, name, ftype in c.fetchall():
            user_files.setdefault(uid, []).append((name, ftype))
        c.execute('SELECT uid FROM users')
        active_users.update(uid for uid, in c.fetchall())
        c.execute('SELECT uid FROM admins')
        admins.update(uid for uid, in c.fetchall())
        c.execute('SELECT hash, uid, name, path FROM pending')
        for h, uid, name, path in c.fetchall():
            pending[h] = {'uid': uid, 'name': name, 'path': path}
        c.execute('SELECT uid, filename, key, value FROM user_envs')
        for uid, filename, key, val in c.fetchall():
            user_envs.setdefault(uid, {}).setdefault(filename, {})[key] = val
        c.execute('SELECT uid, filename, slug FROM site_slugs')
        for uid, filename, slug in c.fetchall():
            site_slugs.setdefault(uid, {})[filename] = slug
        conn.close()
        logger.info(f"Data loaded: {len(active_users)} users")
    except Exception as e:
        logger.error(f"Data load error: {e}")

# ==================== HELPERS ====================
def get_user_folder(uid):
    folder = os.path.join(UPLOAD_DIR, str(uid))
    os.makedirs(folder, exist_ok=True)
    return folder

def get_user_limit(uid):
    if uid == OWNER_ID: return OWNER_LIMIT
    if uid in admins: return ADMIN_LIMIT
    if uid in subscriptions and subscriptions[uid]['expiry'] > datetime.now(): return SUB_LIMIT
    return FREE_LIMIT

def get_user_count(uid):
    return len(user_files.get(uid, []))

def fmt_size(sz):
    if sz < 1024: return f"{sz}B"
    elif sz < 1024*1024: return f"{sz/1024:.1f}KB"
    else: return f"{sz/(1024*1024):.1f}MB"

def get_user_tier(uid):
    if uid == OWNER_ID: return "👑 Owner"
    if uid in admins: return "🛡️ Admin"
    if uid in subscriptions and subscriptions[uid]['expiry'] > datetime.now(): return "⭐ Premium"
    return "👤 Free"

def kill_process_tree(pid):
    try:
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            try: child.kill()
            except: pass
        parent.kill()
        return True
    except: return False

def stop_script(uid, name):
    key = f"{uid}_{name}"
    # For ZIP files, the process may be stored under both the zip key and the entry point key
    keys_to_stop = [key]
    # Find any entry that has this as its zip_name
    for k, info in list(scripts.items()):
        if info.get('zip_name') == name and info.get('uid') == uid and k != key:
            keys_to_stop.append(k)

    stopped = False
    for k in keys_to_stop:
        if k in scripts and scripts[k].get('process'):
            try:
                scripts[k]['stopped_intentionally'] = True
                scripts[k]['running'] = False
                kill_process_tree(scripts[k]['process'].pid)
                try: scripts[k]['process'].wait(timeout=2)
                except: pass
                stopped = True
            except: pass
    return stopped

def is_running(uid, name):
    key = f"{uid}_{name}"
    # Check direct key first
    def _check_key(k):
        if k not in scripts or not scripts[k].get('process'): return False
        if scripts[k].get('stopped_intentionally'): return False
        try:
            p = psutil.Process(scripts[k]['process'].pid)
            if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                scripts[k]['running'] = True
                return True
        except psutil.NoSuchProcess: pass
        scripts[k]['running'] = False
        return False

    if _check_key(key):
        return True
    # For ZIPs: also check any entry whose zip_name matches
    for k, info in scripts.items():
        if info.get('zip_name') == name and info.get('uid') == uid:
            if _check_key(k):
                return True
    return False

def get_process_stats(pid):
    try:
        p = psutil.Process(pid)
        mem = p.memory_info().rss / (1024*1024)
        cpu = p.cpu_percent(interval=0.1)
        return f"{cpu:.1f}%", f"{mem:.1f}MB"
    except: return "?", "?"

def safe_send(chat_id, text, parse=None, markup=None):
    try: return bot.send_message(chat_id, text, parse_mode=parse, reply_markup=markup)
    except Exception as e:
        if "can't parse" in str(e): return bot.send_message(chat_id, text, reply_markup=markup)
        elif "Too Many Requests" in str(e): time.sleep(1); return safe_send(chat_id, text, parse, markup)
        raise

def safe_edit(chat_id, msg_id, text, parse=None, markup=None):
    try: return bot.edit_message_text(text, chat_id, msg_id, parse_mode=parse, reply_markup=markup)
    except Exception as e:
        if "not modified" in str(e): return None
        if "can't parse" in str(e): return bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup)

def safe_reply(msg, text, parse=None, markup=None):
    try: return bot.reply_to(msg, text, parse_mode=parse, reply_markup=markup)
    except Exception as e:
        if "can't parse" in str(e): return bot.reply_to(msg, text, reply_markup=markup)
        raise

def update_user_info(msg):
    uid = msg.from_user.id
    name = (msg.from_user.first_name or "") + (" " + msg.from_user.last_name if msg.from_user.last_name else "")
    username = msg.from_user.username or ""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT OR IGNORE INTO users (uid, name, username, first_seen, last_seen) VALUES (?,?,?,?,?)',
                     (uid, name.strip(), username, datetime.now().isoformat(), datetime.now().isoformat()))
        conn.execute('UPDATE users SET name=?, username=?, last_seen=? WHERE uid=?',
                     (name.strip(), username, datetime.now().isoformat(), uid))
        conn.commit(); conn.close()
    except: pass

def get_user_first_seen(uid):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT first_seen FROM users WHERE uid=?', (uid,))
        row = c.fetchone(); conn.close()
        if row and row[0]: return datetime.fromisoformat(row[0]).strftime('%Y-%m-%d')
    except: pass
    return "Unknown"

def extract_error_snippet(stderr, stdout=""):
    text = (stderr or stdout or "").strip()
    if not text: return ""
    tb = re.search(r'(Traceback \(most recent call last\).*)', text, re.DOTALL)
    if tb:
        snippet = tb.group(1).strip()
    else:
        lines = text.splitlines()
        snippet = "\n".join(lines[-30:]).strip()
    if len(snippet) > 1800:
        snippet = "..." + snippet[-1800:]
    return snippet

def get_user_env(uid, filename):
    """Build env dict for a script, merging system env with user-defined vars."""
    env = os.environ.copy()
    user_defined = user_envs.get(uid, {}).get(filename, {})
    env.update(user_defined)
    return env

def save_env_var(uid, filename, key, value):
    user_envs.setdefault(uid, {}).setdefault(filename, {})[key] = value
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT OR REPLACE INTO user_envs VALUES (?,?,?,?)', (uid, filename, key, value))
        conn.commit(); conn.close()
    except: pass

def delete_env_var(uid, filename, key):
    if uid in user_envs and filename in user_envs[uid]:
        user_envs[uid][filename].pop(key, None)
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('DELETE FROM user_envs WHERE uid=? AND filename=? AND key=?', (uid, filename, key))
        conn.commit(); conn.close()
    except: pass

def save_slug(uid, filename, slug):
    site_slugs.setdefault(uid, {})[filename] = slug
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT OR REPLACE INTO site_slugs VALUES (?,?,?)', (uid, filename, slug))
        conn.commit(); conn.close()
    except: pass

def slug_exists(slug, exclude_uid=None, exclude_file=None):
    for uid, files in site_slugs.items():
        for fn, sl in files.items():
            if sl == slug:
                if uid == exclude_uid and fn == exclude_file: continue
                return True
    return False

# ==================== SECURITY ====================
def check_malicious(file_path):
    patterns = [
        'sudo ', 'rm -rf', 'fdisk', 'mkfs', 'dd if=', 'shutdown', 'reboot', 'halt',
        'poweroff', 'init 0', 'init 6', 'systemctl',
        'os.system("rm', 'os.system("sudo', 'shutil.rmtree("/"',
        'setuid', 'setgid', 'chmod 777', 'chown root'
    ]
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read().lower()
        for p in patterns:
            if p.lower() in content: return False, f"Blocked pattern: `{p}`"
        if os.path.getsize(file_path) > 20*1024*1024: return False, "File >20MB"
        return True, "Safe"
    except: return True, "Safe"

def scan_zip_contents(zip_path):
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for name in zf.namelist():
                ext = os.path.splitext(name)[1].lower()
                if ext in ('.py','.js','.sh','.rb','.php','.lua','.ts','.bat','.ps1'):
                    try:
                        with zf.open(name) as f:
                            content = f.read(512*1024).decode('utf-8', errors='ignore').lower()
                        patterns = ['sudo ','rm -rf','fdisk','mkfs','dd if=','shutdown',
                                    'reboot','halt','poweroff','init 0','init 6',
                                    'shutil.rmtree("/")','setuid','setgid','chmod 777','chown root']
                        for p in patterns:
                            if p.lower() in content:
                                return False, f"Blocked in `{os.path.basename(name)}`: `{p}`"
                    except: pass
        return True, "Safe"
    except zipfile.BadZipFile: return False, "Invalid ZIP file"
    except: return True, "Safe"

def is_website_zip(zip_path):
    """Returns True if ZIP contains index.html — treat as static website."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            names = [os.path.basename(n).lower() for n in zf.namelist()]
            return 'index.html' in names
    except: return False

# ==================== DEPENDENCY INSTALLER ====================
def install_deps(file_path, ext, folder, installed=None):
    if installed is None: installed = set()
    new = set(); msgs = []
    try:
        if ext == '.py':
            with open(file_path, 'r', encoding='utf-8') as f: content = f.read()
            pkg_map = {
                'requests':'requests','flask':'flask','django':'django',
                'numpy':'numpy','pandas':'pandas','matplotlib':'matplotlib',
                'scipy':'scipy','sklearn':'scikit-learn','cv2':'opencv-python',
                'PIL':'Pillow','bs4':'beautifulsoup4','selenium':'selenium',
                'telebot':'pyTelegramBotAPI','telegram':'python-telegram-bot',
                'telethon':'telethon','cryptg':'cryptg','yaml':'pyyaml',
                'dotenv':'python-dotenv','psutil':'psutil','cryptography':'cryptography',
                'aiohttp':'aiohttp','fastapi':'fastapi','uvicorn':'uvicorn',
                'sqlalchemy':'sqlalchemy','pymongo':'pymongo','redis':'redis','pydantic':'pydantic'
            }
            imports = re.findall(r'(?:from\s+(\w+)|import\s+(\w+))', content)
            for imp in imports:
                mod = imp[0] or imp[1]
                if mod in pkg_map and pkg_map[mod] and pkg_map[mod] not in installed and pkg_map[mod] not in new:
                    try:
                        res = subprocess.run([sys.executable,'-m','pip','install','--quiet',pkg_map[mod]],
                                             capture_output=True,text=True,timeout=30)
                        if res.returncode == 0: msgs.append(f"✅ {pkg_map[mod]}"); new.add(pkg_map[mod])
                        else: msgs.append(f"❌ {pkg_map[mod]}")
                    except: msgs.append(f"⚠️ {pkg_map[mod]}")
        elif ext == '.js':
            pjson = os.path.join(folder, 'package.json')
            if not os.path.exists(pjson):
                with open(pjson,'w') as f: json.dump({"name":"script","version":"1.0.0"},f)
            with open(file_path,'r',encoding='utf-8') as f: content = f.read()
            node_map = {'express':'express','axios':'axios','lodash':'lodash',
                        'moment':'moment','dotenv':'dotenv','ws':'ws',
                        'mongoose':'mongoose','mysql':'mysql','pg':'pg'}
            requires = re.findall(r"require\(['\"]([^'\"]+)['\"]\)",content)
            for mod in requires:
                base = mod.split('/')[0]
                if base in node_map and node_map[base] not in installed and node_map[base] not in new:
                    try:
                        res = subprocess.run(['npm','install','--silent',node_map[base]],
                                             cwd=folder,capture_output=True,text=True,timeout=30)
                        if res.returncode == 0: msgs.append(f"✅ {node_map[base]}"); new.add(node_map[base])
                        else: msgs.append(f"❌ {node_map[base]}")
                    except: msgs.append(f"⚠️ {node_map[base]}")
    except: pass
    return msgs, new

# ==================== ZIP WEBSITE HANDLER ====================
def handle_zip_website(zip_path, uid, zip_name, msg=None):
    """Extract ZIP as static website, serve at /s/<slug>/"""
    # Determine slug
    existing_slug = site_slugs.get(uid, {}).get(zip_name)
    if existing_slug:
        slug = existing_slug
    else:
        # Auto-generate slug from filename
        base = os.path.splitext(zip_name)[0]
        slug = re.sub(r'[^a-z0-9\-]', '-', base.lower()).strip('-') or hashlib.md5(f"{uid}_{zip_name}".encode()).hexdigest()[:8]
        # Ensure uniqueness
        orig = slug; counter = 1
        while slug_exists(slug, uid, zip_name):
            slug = f"{orig}-{counter}"; counter += 1
        save_slug(uid, zip_name, slug)

    site_dir = os.path.join(SITES_DIR, slug)
    if os.path.exists(site_dir): shutil.rmtree(site_dir)
    os.makedirs(site_dir)

    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(site_dir)

    # Flatten one level if everything is inside a subdirectory
    entries = os.listdir(site_dir)
    if len(entries) == 1 and os.path.isdir(os.path.join(site_dir, entries[0])):
        sub = os.path.join(site_dir, entries[0])
        for item in os.listdir(sub):
            shutil.move(os.path.join(sub, item), site_dir)
        os.rmdir(sub)

    url = get_site_url(slug)
    if msg:
        mk = types.InlineKeyboardMarkup()
        if url:
            mk.add(types.InlineKeyboardButton("🌐 Open Website", url=url))
        mk.add(types.InlineKeyboardButton("🔗 Set Custom Slug", callback_data=f"setslug_{uid}_{zip_name}"))
        safe_edit(msg.chat.id, msg.message_id,
                 f"🌐 *Website Hosted*\n`{zip_name}`\n\nSlug: `{slug}`\nURL: `{url or 'Set HOST_URL env var'}`",
                 'Markdown', mk)
    return True, url or slug

# ==================== ZIP HANDLER ====================
def handle_zip(zip_path, uid, extract_to, msg=None, zip_name=None):
    try:
        os.makedirs(extract_to, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as zf: zf.extractall(extract_to)
        main_file = None
        priority = ['main.py','app.py','bot.py','run.py','index.py','server.py',
                    'index.js','main.js','app.js','server.js']
        for root, _, files in os.walk(extract_to):
            for pf in priority:
                if pf in files: main_file = os.path.join(root, pf); break
            if main_file: break
        if not main_file:
            for root, _, files in os.walk(extract_to):
                for f in files:
                    if f.endswith(('.py','.js','.sh')): main_file = os.path.join(root, f); break
                if main_file: break
        if not main_file: return False, "No executable file found in ZIP"
        ok, result = execute_script(uid, main_file, msg, extract_to)
        # After execute_script, tag the scripts entry with zip metadata for tracking
        if ok and zip_name:
            entry_name = os.path.basename(main_file)
            entry_key = f"{uid}_{entry_name}"
            zip_key = f"{uid}_{zip_name}"
            if entry_key in scripts:
                scripts[entry_key]['zip_name'] = zip_name
                scripts[entry_key]['extract_dir'] = extract_to
                # Also register under the zip key so is_running(uid, zip_name) works
                scripts[zip_key] = scripts[entry_key]
        return ok, result
    except zipfile.BadZipFile: return False, "Invalid ZIP file"
    except Exception as e: return False, f"ZIP error: {e}"

# ==================== FILE TYPE SETS ====================
EXECUTABLE_EXTS = {
    # Python
    '.py', '.pyw',
    # JavaScript / Node
    '.js', '.mjs', '.cjs',
    # TypeScript
    '.ts', '.tsx',
    # Shell
    '.sh', '.bash', '.zsh', '.fish',
    # Java
    '.java',
    # C / C++
    '.c', '.cpp', '.cc', '.cxx',
    # Go
    '.go',
    # Rust
    '.rs',
    # Ruby
    '.rb',
    # PHP
    '.php',
    # Lua
    '.lua',
    # Perl
    '.pl', '.pm',
    # R
    '.r', '.R',
    # Swift
    '.swift',
    # Kotlin
    '.kt',
    # Scala
    '.scala',
    # Elixir
    '.ex', '.exs',
    # Haskell
    '.hs',
    # Windows
    '.bat', '.cmd', '.ps1',
}

STATIC_EXTS = {
    # Web
    '.html', '.htm', '.css', '.js', '.mjs',
    # Text / Docs
    '.txt', '.md', '.rst', '.rtf',
    # Data
    '.json', '.jsonl', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
    '.csv', '.tsv', '.sql',
    # Images
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico', '.bmp', '.tiff',
    # Video / Audio
    '.mp4', '.webm', '.mkv', '.avi', '.mov', '.mp3', '.wav', '.ogg', '.flac', '.aac',
    # Docs
    '.pdf',
    # Archives (static, not executable)
    '.tar', '.gz', '.bz2',
    # Code as static (viewed not run)
    '.env', '.log', '.sh', '.bat',
    # Font
    '.ttf', '.woff', '.woff2',
}

LANG_MAP = {
    '.py':   ('Python',     '🐍'),
    '.pyw':  ('Python',     '🐍'),
    '.js':   ('JavaScript', '🟨'),
    '.mjs':  ('JavaScript', '🟨'),
    '.cjs':  ('JavaScript', '🟨'),
    '.ts':   ('TypeScript', '🔷'),
    '.tsx':  ('TypeScript', '🔷'),
    '.java': ('Java',       '☕'),
    '.cpp':  ('C++',        '🔧'),
    '.cc':   ('C++',        '🔧'),
    '.cxx':  ('C++',        '🔧'),
    '.c':    ('C',          '🔧'),
    '.sh':   ('Shell',      '🖥️'),
    '.bash': ('Shell',      '🖥️'),
    '.zsh':  ('Shell',      '🖥️'),
    '.fish': ('Shell',      '🖥️'),
    '.rb':   ('Ruby',       '💎'),
    '.go':   ('Go',         '🐹'),
    '.rs':   ('Rust',       '🦀'),
    '.php':  ('PHP',        '🐘'),
    '.lua':  ('Lua',        '🌙'),
    '.pl':   ('Perl',       '🐪'),
    '.pm':   ('Perl',       '🐪'),
    '.r':    ('R',          '📊'),
    '.R':    ('R',          '📊'),
    '.swift':('Swift',      '🍎'),
    '.kt':   ('Kotlin',     '🟣'),
    '.scala':('Scala',      '🔴'),
    '.ex':   ('Elixir',     '💜'),
    '.exs':  ('Elixir',     '💜'),
    '.hs':   ('Haskell',    '🔵'),
    '.bat':  ('Batch',      '🖥️'),
    '.cmd':  ('Batch',      '🖥️'),
    '.ps1':  ('PowerShell', '🔵'),
}

# ==================== CRASH MONITOR ====================
def monitor_script(uid, key, name, process, log_path, msg_chat_id=None, msg_id=None):
    try:
        process.wait()
        rc = process.returncode
        if key not in scripts: return

        # If intentionally stopped or deleted — do nothing
        if scripts[key].get('stopped_intentionally'):
            return

        scripts[key]['running'] = False
        scripts[key]['code'] = rc

        # Update launch message if it was stuck on deps/starting
        if msg_chat_id and msg_id:
            try:
                mk = build_control_markup(uid, name, 'executable')
                if rc in (0, None):
                    safe_edit(msg_chat_id, msg_id, f"✅ *Finished* — `{name}`\nExit: `{rc}`", 'Markdown', mk)
                else:
                    safe_edit(msg_chat_id, msg_id, f"❌ *Crashed* — `{name}`\nExit: `{rc}`", 'Markdown', mk)
            except: pass

        # Only alert on genuine crashes (not clean exit, not manual stop, not SIGKILL from us)
        if rc not in (0, -1, -9, None):
            snippet = ""
            # Prefer stderr_log (clean stderr only) over merged log
            stderr_path = scripts[key].get('stderr_log')
            read_path = stderr_path if stderr_path and os.path.exists(stderr_path) and os.path.getsize(stderr_path) > 0 else log_path
            if read_path and os.path.exists(read_path):
                with open(read_path, 'r', errors='ignore') as f: content = f.read()
                # Strip noisy HTTP/INFO lines
                filtered_lines = [
                    l for l in content.splitlines()
                    if not re.match(r'^(INFO|DEBUG|WARNING):(httpx|urllib3|requests|telebot|apscheduler)', l)
                    and 'HTTP Request:' not in l
                    and 'HTTP/1.' not in l
                    and 'getUpdates' not in l
                ]
                filtered = "\n".join(filtered_lines)
                tb = re.search(r'(Traceback \(most recent call last\).*)', filtered, re.DOTALL)
                if tb:
                    snippet = tb.group(1).strip()
                else:
                    tail = filtered_lines[-30:] if len(filtered_lines) > 30 else filtered_lines
                    snippet = "\n".join(tail).strip()
                if len(snippet) > 1800: snippet = "..." + snippet[-1800:]

            text = (f"⚠️ *Script Crashed*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
                    f"📄 `{name}`\n❌ Exit code: `{rc}`")
            if snippet: text += f"\n\n*Traceback:*\n```\n{snippet}\n```"
            try: safe_send(uid, text, 'Markdown')
            except: pass
    except: pass

# ==================== SCRIPT EXECUTOR ====================
def execute_script(uid, file_path, msg=None, work_dir=None):
    name = os.path.basename(file_path)
    ext = os.path.splitext(file_path)[1].lower()
    key = f"{uid}_{name}"
    with exec_locks_mutex:
        if exec_locks.get(key):
            if msg:
                try: safe_edit(msg.chat.id, msg.message_id, f"⚠️ `{name}` is already being started", 'Markdown')
                except: pass
            return False, "Already starting"
        exec_locks[key] = True
    try:
        return _do_execute(uid, file_path, msg, work_dir, name, ext, key)
    finally:
        with exec_locks_mutex:
            exec_locks.pop(key, None)

def _do_execute(uid, file_path, msg, work_dir, name, ext, key):
    if ext in STATIC_EXTS:
        if msg:
            url = get_file_url(uid, name)
            mk = types.InlineKeyboardMarkup()
            if url: mk.add(types.InlineKeyboardButton("🔗 View File", url=url))
            safe_edit(msg.chat.id, msg.message_id, f"✅ *Hosted*\n`{name}`", 'Markdown', mk if url else None)
        return True, "Hosted"

    if ext == '.zip':
        return handle_zip(file_path, uid, os.path.join(EXTRACT_DIR, f"{uid}_{int(time.time())}"), msg, name)

    if ext not in LANG_MAP:
        if msg: safe_edit(msg.chat.id, msg.message_id, f"❌ Unsupported type: `{ext}`", 'Markdown')
        return False, "Unsupported"

    lang, icon = LANG_MAP[ext]
    folder = get_user_folder(uid)

    try:
        if msg: safe_edit(msg.chat.id, msg.message_id, f"{icon} *{lang}* — `{name}`\n⚙️ Starting...", 'Markdown')

        installed = set()
        deps, new = install_deps(file_path, ext, folder)
        installed.update(new)

        if deps and msg:
            dep_text = "\n".join(deps[:4]) + (f"\n+{len(deps)-4} more" if len(deps) > 4 else "")
            safe_edit(msg.chat.id, msg.message_id, f"{icon} *{lang}* — `{name}`\n📦 Deps:\n{dep_text}", 'Markdown')

        if ext in ('.py', '.pyw'):
            cmd = [sys.executable, file_path]
        elif ext in ('.js', '.mjs', '.cjs'):
            cmd = ['node', file_path]
        elif ext == '.java':
            classname = os.path.splitext(name)[0]
            res = subprocess.run(['javac', file_path], capture_output=True, text=True, timeout=60)
            if res.returncode != 0:
                if msg: safe_edit(msg.chat.id, msg.message_id, f"❌ *Java compile failed*\n```\n{res.stderr[:400]}\n```", 'Markdown')
                return False, "Java compile failed"
            cmd = ['java', '-cp', os.path.dirname(file_path), classname]
        elif ext in ('.cpp', '.cc', '.cxx', '.c'):
            out = os.path.join(folder, os.path.splitext(name)[0]+'.out')
            comp = 'g++' if ext in ('.cpp','.cc','.cxx') else 'gcc'
            res = subprocess.run([comp, file_path, '-o', out], capture_output=True, text=True, timeout=60)
            if res.returncode != 0:
                if msg: safe_edit(msg.chat.id, msg.message_id, f"❌ *Compile failed*\n```\n{res.stderr[:400]}\n```", 'Markdown')
                return False, "Compile failed"
            cmd = [out]
        elif ext == '.go':
            cmd = ['go', 'run', file_path]
        elif ext == '.rs':
            out = os.path.join(folder, os.path.splitext(name)[0]+'.out')
            res = subprocess.run(['rustc', file_path, '-o', out], capture_output=True, text=True, timeout=60)
            if res.returncode != 0:
                if msg: safe_edit(msg.chat.id, msg.message_id, f"❌ *Rust compile failed*\n```\n{res.stderr[:400]}\n```", 'Markdown')
                return False, "Rust compile failed"
            cmd = [out]
        elif ext == '.php':
            cmd = ['php', file_path]
        elif ext == '.rb':
            cmd = ['ruby', file_path]
        elif ext == '.lua':
            cmd = ['lua', file_path]
        elif ext in ('.sh', '.bash', '.zsh', '.fish'):
            os.chmod(file_path, 0o755)
            shell = ext.lstrip('.') if ext != '.sh' else 'bash'
            cmd = [shell, file_path]
        elif ext in ('.ts', '.tsx'):
            js = file_path.rsplit('.', 1)[0] + '.js'
            res = subprocess.run(['tsc', file_path, '--outDir', os.path.dirname(file_path)],
                                 capture_output=True, text=True, timeout=60)
            if res.returncode != 0:
                if msg: safe_edit(msg.chat.id, msg.message_id, f"❌ *TS compile failed*\n```\n{res.stderr[:400]}\n```", 'Markdown')
                return False, "TS compile failed"
            cmd = ['node', js]
        elif ext == '.ps1':
            cmd = ['powershell', '-File', file_path]
        elif ext in ('.bat', '.cmd'):
            cmd = [file_path]
        elif ext in ('.pl', '.pm'):
            cmd = ['perl', file_path]
        elif ext in ('.r', '.R'):
            cmd = ['Rscript', file_path]
        elif ext == '.swift':
            cmd = ['swift', file_path]
        elif ext == '.kt':
            jar = os.path.join(folder, os.path.splitext(name)[0]+'.jar')
            res = subprocess.run(['kotlinc', file_path, '-include-runtime', '-d', jar],
                                 capture_output=True, text=True, timeout=120)
            if res.returncode != 0:
                if msg: safe_edit(msg.chat.id, msg.message_id, f"❌ *Kotlin compile failed*\n```\n{res.stderr[:400]}\n```", 'Markdown')
                return False, "Kotlin compile failed"
            cmd = ['java', '-jar', jar]
        elif ext == '.scala':
            res = subprocess.run(['scalac', file_path, '-d', folder],
                                 capture_output=True, text=True, timeout=120)
            if res.returncode != 0:
                if msg: safe_edit(msg.chat.id, msg.message_id, f"❌ *Scala compile failed*\n```\n{res.stderr[:400]}\n```", 'Markdown')
                return False, "Scala compile failed"
            cmd = ['scala', '-cp', folder, os.path.splitext(name)[0]]
        elif ext in ('.ex', '.exs'):
            cmd = ['elixir', file_path]
        elif ext == '.hs':
            out = os.path.join(folder, os.path.splitext(name)[0])
            res = subprocess.run(['ghc', file_path, '-o', out],
                                 capture_output=True, text=True, timeout=120)
            if res.returncode != 0:
                if msg: safe_edit(msg.chat.id, msg.message_id, f"❌ *Haskell compile failed*\n```\n{res.stderr[:400]}\n```", 'Markdown')
                return False, "Haskell compile failed"
            cmd = [out]
        else:
            cmd = [file_path]

        log_path = os.path.join(LOGS_DIR, f"{uid}_{int(time.time())}.log")
        env = get_user_env(uid, name)
        cwd = work_dir or os.path.dirname(file_path)

        for attempt in range(1, 11):
            if attempt > 1 and msg:
                safe_edit(msg.chat.id, msg.message_id, f"{icon} *{lang}* — `{name}`\n🔄 Retry {attempt}...", 'Markdown')
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=cwd, env=env)

                if res.returncode != 0 and "ModuleNotFoundError" in res.stderr:
                    match = re.search(r"No module named '(\w+)'", res.stderr)
                    if match:
                        mod = match.group(1)
                        extra = {'telethon':'telethon','cryptg':'cryptg','telebot':'pyTelegramBotAPI',
                                 'telegram':'python-telegram-bot','cv2':'opencv-python','PIL':'Pillow',
                                 'bs4':'beautifulsoup4','yaml':'pyyaml','dotenv':'python-dotenv',
                                 'flask':'flask','django':'django','requests':'requests',
                                 'numpy':'numpy','pandas':'pandas','aiohttp':'aiohttp','fastapi':'fastapi'}
                        pkg = extra.get(mod, mod)
                        if pkg not in installed:
                            if msg: safe_edit(msg.chat.id, msg.message_id, f"{icon} *{lang}* — `{name}`\n📦 Installing `{pkg}`...", 'Markdown')
                            subprocess.run([sys.executable,'-m','pip','install','--quiet',pkg],
                                           capture_output=True, text=True, timeout=60)
                            installed.add(pkg)
                            continue

                with open(log_path, 'w') as lf:
                    if res.stdout: lf.write(f"STDOUT:\n{res.stdout}\n")
                    if res.stderr: lf.write(f"STDERR:\n{res.stderr}\n")
                    lf.write(f"\nExit: {res.returncode}")

                scripts[key] = {'process':None,'key':key,'uid':uid,'name':name,
                                'start':datetime.now(),'log':log_path,'lang':lang,
                                'icon':icon,'running':False,'code':res.returncode}

                if msg:
                    mk = build_control_markup(uid, name, 'executable')
                    if res.returncode == 0:
                        safe_edit(msg.chat.id, msg.message_id, f"✅ *{lang}* — `{name}`\nExit: `0`", 'Markdown', mk)
                    else:
                        snippet = extract_error_snippet(res.stderr, res.stdout)
                        error_text = f"❌ *{lang}* — `{name}`\nExit: `{res.returncode}`"
                        if snippet: error_text += f"\n\n```\n{snippet}\n```"
                        safe_edit(msg.chat.id, msg.message_id, error_text, 'Markdown', mk)
                return True, f"Exit {res.returncode}"

            except subprocess.TimeoutExpired:
                stderr_path = log_path.replace('.log', '.err')
                with open(log_path, 'w') as lf, open(stderr_path, 'w') as ef:
                    p = subprocess.Popen(cmd, stdout=lf, stderr=ef, cwd=cwd, env=env)

                scripts[key] = {'process':p,'key':key,'uid':uid,'name':name,
                                'start':datetime.now(),'log':log_path,'stderr_log':stderr_path,'lang':lang,
                                'icon':icon,'running':True,'code':None}

                msg_chat_id = msg.chat.id if msg else None
                msg_id_val = msg.message_id if msg else None

                t = threading.Thread(target=monitor_script,
                                     args=(uid, key, name, p, log_path, msg_chat_id, msg_id_val), daemon=True)
                t.start()

                if msg:
                    mk = build_control_markup(uid, name, 'executable')
                    safe_edit(msg.chat.id, msg.message_id, f"🔄 *{lang}* — `{name}`\nPID: `{p.pid}`", 'Markdown', mk)
                return True, f"Background PID {p.pid}"

        return False, "Max retries exceeded"

    except Exception as e:
        logger.error(f"Exec error {key}: {e}", exc_info=True)
        if msg:
            try: safe_edit(msg.chat.id, msg.message_id, f"❌ Error: `{str(e)[:200]}`", 'Markdown')
            except: pass
        return False, str(e)

# ==================== SHELL ====================
def _run_shell_cmd(message, cmd_text):
    uid = message.from_user.id
    commands = [c.strip() for c in re.split(r'\n|&&', cmd_text) if c.strip()]
    dangerous = ['rm -rf /*', 'dd if=', 'mkfs', ':(){', '> /dev/sda']
    for cmd in commands:
        for d in dangerous:
            if d in cmd: return safe_reply(message, f"🚫 *Blocked:* `{d}`", 'Markdown')

    full_cmd = ' && '.join(commands)
    exit_mk = types.InlineKeyboardMarkup()
    exit_mk.add(types.InlineKeyboardButton("❌ Exit Shell", callback_data="exit_shell"))
    status = safe_reply(message, f"`$ {full_cmd}`\n⏳ Starting...", 'Markdown', exit_mk)

    try:
        process = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, cwd=BASE_DIR, bufsize=1)
        stdout_lines = []; stderr_lines = []
        last_edit = time.time()

        def read_stderr():
            for line in process.stderr: stderr_lines.append(line)
        t = threading.Thread(target=read_stderr, daemon=True)
        t.start()

        deadline = time.time() + 30
        for line in process.stdout:
            stdout_lines.append(line)
            now = time.time()
            if now > deadline: process.kill(); break
            if now - last_edit >= 1.5:
                preview = "".join(stdout_lines)[-800:]
                try:
                    safe_edit(status.chat.id, status.message_id,
                             f"`$ {full_cmd}`\n⏳ Running...\n```\n{preview}\n```", 'Markdown', exit_mk)
                    last_edit = now
                except: pass

        process.wait(timeout=5); t.join(timeout=3)
        stdout = "".join(stdout_lines); stderr = "".join(stderr_lines); rc = process.returncode

        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute('INSERT INTO cmd_log (uid, cmd, time, output) VALUES (?,?,?,?)',
                         (uid, full_cmd, datetime.now().isoformat(), (stdout+stderr)[:500]))
            conn.commit(); conn.close()
        except: pass

        output = ""
        if stdout: output += f"```\n{stdout[:2500]}\n```" + ("\n_…truncated_" if len(stdout) > 2500 else "")
        if stderr: output += ("\n" if output else "") + f"⚠️ stderr:\n```\n{stderr[:800]}\n```"
        if not output: output = "✅ No output"

        result = f"`$ {full_cmd}`\n\n{output}\n`exit {rc}`"
        if len(result) > 4096:
            tmp = os.path.join(LOGS_DIR, f"shell_{int(time.time())}.txt")
            with open(tmp,'w') as f: f.write(f"$ {full_cmd}\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}\n\nExit: {rc}")
            with open(tmp,'rb') as f: bot.send_document(status.chat.id, f, caption=f"`$ {full_cmd}`", parse_mode='Markdown', reply_markup=exit_mk)
            os.remove(tmp); bot.delete_message(status.chat.id, status.message_id)
        else:
            safe_edit(status.chat.id, status.message_id, result, 'Markdown', exit_mk)
    except Exception as e:
        safe_edit(status.chat.id, status.message_id, f"❌ `{e}`", 'Markdown', exit_mk)

@bot.message_handler(commands=['shell'])
def cmd_shell(message):
    uid = message.from_user.id
    if uid not in admins and uid != OWNER_ID:
        return safe_reply(message, "🚫 *Access Denied*", 'Markdown')
    parts = message.text.strip().split(' ', 1)
    if len(parts) > 1 and parts[1].strip():
        _run_shell_cmd(message, parts[1].strip())
    else:
        shell_sessions[uid] = True
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("❌ Exit Shell", callback_data="exit_shell"))
        safe_reply(message, "💻 *Shell Active*\nSend commands directly\\. Multiple lines supported\\.", 'MarkdownV2', mk)

@bot.callback_query_handler(func=lambda c: c.data == "exit_shell")
def cb_exit_shell(c):
    uid = c.from_user.id
    shell_sessions.pop(uid, None)
    try: safe_edit(c.message.chat.id, c.message.message_id, "💻 *Shell Closed*", 'Markdown')
    except: pass
    bot.answer_callback_query(c.id, "Shell closed")

# ==================== ENV VAR COMMANDS ====================
@bot.message_handler(commands=['setenv'])
def cmd_setenv(message):
    """Start env var set flow: /setenv filename"""
    uid = message.from_user.id
    parts = message.text.strip().split(None, 1)
    if len(parts) < 2:
        return safe_reply(message, "❌ Usage: `/setenv <filename>`\nThen follow the prompts", 'Markdown')
    filename = parts[1].strip()
    files = [n for n, t in user_files.get(uid, []) if n == filename]
    if not files:
        return safe_reply(message, f"❌ File `{filename}` not found in your files", 'Markdown')
    waiting_env[uid] = {'step': 'key', 'name': filename}
    safe_reply(message, f"🔑 *Set env var for* `{filename}`\n\nSend the variable *name* (e.g. `BOT_TOKEN`):", 'Markdown')

@bot.message_handler(commands=['listenv'])
def cmd_listenv(message):
    """List env vars for a file: /listenv filename"""
    uid = message.from_user.id
    parts = message.text.strip().split(None, 1)
    if len(parts) < 2:
        return safe_reply(message, "❌ Usage: `/listenv <filename>`", 'Markdown')
    filename = parts[1].strip()
    envs = user_envs.get(uid, {}).get(filename, {})
    if not envs:
        return safe_reply(message, f"📋 No env vars set for `{filename}`", 'Markdown')
    text = f"📋 *Env vars for* `{filename}`\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
    for k, v in envs.items():
        masked = v[:2] + '*' * max(0, len(v) - 4) + v[-2:] if len(v) > 4 else '****'
        text += f"`{k}` = `{masked}`\n"
    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("🗑️ Clear All", callback_data=f"clearenv_{uid}_{filename}"))
    safe_reply(message, text, 'Markdown', mk)

@bot.message_handler(commands=['delenv'])
def cmd_delenv(message):
    """Delete one env var: /delenv filename KEY"""
    uid = message.from_user.id
    parts = message.text.strip().split(None, 2)
    if len(parts) < 3:
        return safe_reply(message, "❌ Usage: `/delenv <filename> <KEY>`", 'Markdown')
    filename, key = parts[1].strip(), parts[2].strip()
    delete_env_var(uid, filename, key)
    safe_reply(message, f"✅ Deleted `{key}` from `{filename}`", 'Markdown')

@bot.callback_query_handler(func=lambda c: c.data.startswith('clearenv_'))
def cb_clearenv(c):
    parts = c.data.split('_', 2); uid, filename = int(parts[1]), parts[2]
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "Access denied")
    if uid in user_envs and filename in user_envs[uid]:
        user_envs[uid][filename] = {}
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('DELETE FROM user_envs WHERE uid=? AND filename=?', (uid, filename))
        conn.commit(); conn.close()
    except: pass
    safe_edit(c.message.chat.id, c.message.message_id, f"✅ *Cleared all env vars* for `{filename}`", 'Markdown')
    bot.answer_callback_query(c.id, "Cleared")

# ==================== SLUG COMMANDS ====================
@bot.callback_query_handler(func=lambda c: c.data.startswith('setslug_'))
def cb_setslug(c):
    parts = c.data.split('_', 2); uid, filename = int(parts[1]), parts[2]
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "Access denied")
    waiting_slug[uid] = {'name': filename, 'uid': uid}
    safe_send(c.message.chat.id,
             f"🔗 *Set custom slug for* `{filename}`\n\nSend your slug (letters, numbers, hyphens only):\nURL will be: `{HOST_URL or 'https://your-app.com'}/s/<your-slug>/`",
             'Markdown')
    bot.answer_callback_query(c.id)

# ==================== BUILD KEYBOARD ====================
def build_main_keyboard(uid):
    is_admin = uid in admins
    is_owner = uid == OWNER_ID
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.row(types.KeyboardButton("📂 Files"), types.KeyboardButton("👤 Profile"))
    markup.row(types.KeyboardButton("📊 Stats"), types.KeyboardButton("❓ Help"))
    markup.row(types.KeyboardButton("📢 Channel"), types.KeyboardButton("📞 Contact"))
    if is_admin:
        markup.row(types.KeyboardButton("🟢 Running"), types.KeyboardButton("💳 Subs"))
        markup.row(types.KeyboardButton("⏳ Pending"), types.KeyboardButton("🤖 Clones"))
        markup.row(types.KeyboardButton("👑 Admin"), types.KeyboardButton("💻 Shell"))
        if is_owner:
            markup.row(types.KeyboardButton("🔒 Lock"), types.KeyboardButton("📁 All Files"))
    else:
        markup.row(types.KeyboardButton("🤖 Clone"))
    return markup

# ==================== COMMANDS ====================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    uid = message.from_user.id
    active_users.add(uid)
    update_user_info(message)
    name = message.from_user.first_name or "User"

    sub_badge = ""
    if uid in subscriptions and subscriptions[uid]['expiry'] > datetime.now():
        diff = subscriptions[uid]['expiry'] - datetime.now()
        days = diff.days; hours = diff.seconds // 3600; mins = (diff.seconds % 3600) // 60
        sub_badge = f"  ⭐ {days}d {hours}h {mins}m" if days > 0 else f"  ⭐ {hours}h {mins}m"

    role = get_user_tier(uid)
    lim = get_user_limit(uid); lim_txt = "∞" if lim == float('inf') else str(lim)

    welcome = (f"👋 *{name}*{sub_badge}\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
               f"{role}  •  `{get_user_count(uid)}/{lim_txt}` files\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
               f"Send a file to upload and host it")
    safe_send(message.chat.id, welcome, 'Markdown', build_main_keyboard(uid))

@bot.message_handler(commands=['help'])
def cmd_help(message):
    uid = message.from_user.id
    is_admin = uid in admins
    lines = ["📖 *Help*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄",
             "`/start` — Home\n`/help` — Help\n`/clone` — Clone this bot",
             "\n*Env Vars*",
             "`/setenv <file>` — Set env var for a script\n`/listenv <file>` — List env vars\n`/delenv <file> <KEY>` — Delete one var"]
    if is_admin:
        lines.append("\n*Admin Commands*")
        lines.append("`/addadmin <id>`\n`/removeadmin <id>`")
        lines.append("`/addsub <id> <days>`\n`/removesub <id>`\n`/checksub <id>`")
        lines.append("`/shell [cmd]` — Shell\n`/broadcast <msg>` — Broadcast")
    lines.append("\n*Features*\n30+ file types • Auto deps • Background hosting • Live logs • Crash alerts • ZIP websites • Custom slugs")
    safe_reply(message, "\n".join(lines), 'Markdown')

# ==================== ADMIN MANAGEMENT ====================
@bot.message_handler(commands=['addadmin'])
def cmd_addadmin(message):
    if message.from_user.id != OWNER_ID:
        return safe_reply(message, "🚫 *Owner Only*", 'Markdown')
    try:
        target = int(message.text.split()[1])
        if target in admins: return safe_reply(message, f"⚠️ Already admin: `{target}`", 'Markdown')
        admins.add(target)
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT OR IGNORE INTO admins VALUES (?)', (target,))
        conn.commit(); conn.close()
        safe_reply(message, f"✅ *Admin added:* `{target}`", 'Markdown')
        try: bot.send_message(target, "👑 *You are now an admin*\n\nSend /start to refresh your menu", 'Markdown')
        except: pass
    except: safe_reply(message, "❌ Usage: `/addadmin <id>`", 'Markdown')

@bot.message_handler(commands=['removeadmin'])
def cmd_removeadmin(message):
    if message.from_user.id != OWNER_ID:
        return safe_reply(message, "🚫 *Owner Only*", 'Markdown')
    try:
        target = int(message.text.split()[1])
        if target == OWNER_ID: return safe_reply(message, "❌ Cannot remove owner", 'Markdown')
        if target not in admins: return safe_reply(message, f"⚠️ Not an admin: `{target}`", 'Markdown')
        admins.discard(target)
        conn = sqlite3.connect(DB_PATH)
        conn.execute('DELETE FROM admins WHERE uid=?', (target,))
        conn.commit(); conn.close()
        safe_reply(message, f"✅ *Admin removed:* `{target}`", 'Markdown')
        try: bot.send_message(target, "👤 *You are no longer an admin*\n\nSend /start to refresh your menu", 'Markdown')
        except: pass
    except: safe_reply(message, "❌ Usage: `/removeadmin <id>`", 'Markdown')

# ==================== SUBSCRIPTIONS ====================
@bot.message_handler(commands=['addsub'])
def cmd_addsub(message):
    if message.from_user.id not in admins:
        return safe_reply(message, "🚫 *Admin Only*", 'Markdown')
    try:
        parts = message.text.split()
        if len(parts) != 3: return safe_reply(message, "❌ Usage: `/addsub <uid> <days>`", 'Markdown')
        target, days = int(parts[1]), int(parts[2])
        if days <= 0: return safe_reply(message, "❌ Days must be positive", 'Markdown')
        expiry = datetime.now() + timedelta(days=days)
        subscriptions[target] = {'expiry': expiry}
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT OR REPLACE INTO subs VALUES (?,?)', (target, expiry.isoformat()))
        conn.commit(); conn.close()
        safe_reply(message, f"✅ *Sub added*\n`{target}` — {days}d until `{expiry.strftime('%Y-%m-%d')}`", 'Markdown')
        try: bot.send_message(target, f"🎉 *Subscription active*\n{days} days — expires `{expiry.strftime('%Y-%m-%d')}`", 'Markdown')
        except: pass
    except: safe_reply(message, "❌ Invalid format", 'Markdown')

@bot.message_handler(commands=['removesub'])
def cmd_removesub(message):
    if message.from_user.id not in admins:
        return safe_reply(message, "🚫 *Admin Only*", 'Markdown')
    try:
        target = int(message.text.split()[1])
        subscriptions.pop(target, None)
        conn = sqlite3.connect(DB_PATH)
        conn.execute('DELETE FROM subs WHERE uid=?', (target,))
        conn.commit(); conn.close()
        safe_reply(message, f"✅ *Sub removed:* `{target}`", 'Markdown')
        try: bot.send_message(target, "❌ *Your subscription has ended*", 'Markdown')
        except: pass
    except: safe_reply(message, "❌ Usage: `/removesub <uid>`", 'Markdown')

@bot.message_handler(commands=['checksub'])
def cmd_checksub(message):
    if message.from_user.id not in admins:
        return safe_reply(message, "🚫 *Admin Only*", 'Markdown')
    try:
        target = int(message.text.split()[1])
        if target in subscriptions:
            exp = subscriptions[target]['expiry']; now = datetime.now()
            if exp > now:
                diff = exp - now
                status_str = f"✅ Active — {diff.days}d {diff.seconds//3600}h left"
            else: status_str = "❌ Expired"
            text = f"👤 `{target}`\n{status_str}\nExpires: `{exp.strftime('%Y-%m-%d %H:%M')}`"
        else: text = f"👤 `{target}`\n❌ No subscription"
        mk = types.InlineKeyboardMarkup()
        mk.row(types.InlineKeyboardButton("➕ Add", callback_data=f"addsub_{target}"),
               types.InlineKeyboardButton("➖ Remove", callback_data=f"remsub_{target}"),
               types.InlineKeyboardButton("🔙 Back", callback_data="del_msg"))
        safe_reply(message, text, 'Markdown', mk)
    except: safe_reply(message, "❌ Usage: `/checksub <uid>`", 'Markdown')

# ==================== SUB CALLBACKS ====================
@bot.callback_query_handler(func=lambda c: c.data.startswith('addsub_'))
def cb_addsub(c):
    if c.from_user.id not in admins: return bot.answer_callback_query(c.id, "Access denied")
    target = int(c.data.split('_')[1])
    mk = types.InlineKeyboardMarkup(row_width=4)
    btns = [types.InlineKeyboardButton(f"{d}d", callback_data=f"subdays_{target}_{d}") for d in [7,15,30,60,90,180,365]]
    mk.add(*btns)
    mk.add(types.InlineKeyboardButton("🔙 Back", callback_data="del_msg"))
    safe_edit(c.message.chat.id, c.message.message_id, f"📅 *Duration for* `{target}`", 'Markdown', mk)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith('subdays_'))
def cb_subdays(c):
    if c.from_user.id not in admins: return bot.answer_callback_query(c.id, "Access denied")
    parts = c.data.split('_'); target, days = int(parts[1]), int(parts[2])
    expiry = datetime.now() + timedelta(days=days)
    subscriptions[target] = {'expiry': expiry}
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT OR REPLACE INTO subs VALUES (?,?)', (target, expiry.isoformat()))
    conn.commit(); conn.close()
    safe_edit(c.message.chat.id, c.message.message_id,
             f"✅ *{days}d added* to `{target}`\nExpires `{expiry.strftime('%Y-%m-%d')}`", 'Markdown')
    bot.answer_callback_query(c.id, "Done")
    try: bot.send_message(target, f"🎉 *+{days} days* added!", 'Markdown')
    except: pass

@bot.callback_query_handler(func=lambda c: c.data.startswith('remsub_'))
def cb_remsub(c):
    if c.from_user.id not in admins: return bot.answer_callback_query(c.id, "Access denied")
    target = int(c.data.split('_')[1])
    subscriptions.pop(target, None)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('DELETE FROM subs WHERE uid=?', (target,))
    conn.commit(); conn.close()
    safe_edit(c.message.chat.id, c.message.message_id, f"✅ *Sub removed from* `{target}`", 'Markdown')
    bot.answer_callback_query(c.id, "Removed")
    try: bot.send_message(target, "❌ *Subscription removed*", 'Markdown')
    except: pass

@bot.callback_query_handler(func=lambda c: c.data == 'del_msg')
def cb_delmsg(c):
    try: bot.delete_message(c.message.chat.id, c.message.message_id)
    except: pass
    bot.answer_callback_query(c.id)

# ==================== CLONE ====================
@bot.message_handler(commands=['clone'])
def cmd_clone(message):
    text = ("🤖 *Clone This Bot*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
            "1\\. Create a bot via @BotFather\n2\\. Copy your token\n"
            "3\\. Send `/settoken YOUR\\_TOKEN`\n\nYou become the owner with full access\\.")
    safe_reply(message, text, 'MarkdownV2')

@bot.message_handler(commands=['settoken'])
def cmd_settoken(message):
    uid = message.from_user.id
    try: token = message.text.split()[1]
    except: return safe_reply(message, "❌ Usage: `/settoken YOUR_TOKEN`", 'Markdown')
    if len(token) < 35 or ':' not in token:
        return safe_reply(message, "❌ *Invalid token format*", 'Markdown')

    wait = safe_reply(message, "⏳ *Validating token...*", 'Markdown')
    try:
        test_bot = telebot.TeleBot(token); info = test_bot.get_me()
    except Exception as e:
        safe_edit(wait.chat.id, wait.message_id, f"❌ *Invalid token*\n`{str(e)[:100]}`", 'Markdown'); return

    safe_edit(wait.chat.id, wait.message_id, f"✅ *Token valid* — @{info.username}\n⏳ Creating clone...", 'Markdown')
    try:
        clone_dir = os.path.join(BASE_DIR, f'clone_{uid}')
        os.makedirs(clone_dir, exist_ok=True)
        with open(__file__, 'r', encoding='utf-8') as f: code = f.read()
        code = code.replace("TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')", f"TOKEN = '{token}'")
        code = code.replace(f"OWNER_ID = int(os.getenv('OWNER_ID', '{OWNER_ID}'))", f"OWNER_ID = {uid}")
        code = code.replace(f"ADMIN_ID = int(os.getenv('ADMIN_ID', '{ADMIN_ID}'))", f"ADMIN_ID = {uid}")
        code = code.replace("BASE_DIR = os.path.abspath(os.path.dirname(__file__))", f"BASE_DIR = '{clone_dir}'")
        clone_file = os.path.join(clone_dir, 'bot.py')
        with open(clone_file, 'w', encoding='utf-8') as f: f.write(code)
        if os.path.exists('requirements.txt'): shutil.copy2('requirements.txt', clone_dir)
        proc = subprocess.Popen([sys.executable, clone_file], cwd=clone_dir,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        scripts[f"clone_{uid}"] = {
            'process': proc, 'key': f"clone_{uid}", 'uid': uid,
            'name': f'{info.username}_clone', 'start': datetime.now(),
            'lang': 'Clone', 'icon': '🤖', 'running': True, 'code': None,
            'bot': info.username, 'bot_id': info.id, 'dir': clone_dir,
            'stats': {'users': 0, 'files': 0, 'runs': 0}
        }
        safe_edit(wait.chat.id, wait.message_id,
                 f"✅ *Clone Running*\n@{info.username}\nYou are the owner", 'Markdown')
    except Exception as e:
        safe_edit(wait.chat.id, wait.message_id, f"❌ *Error*\n`{str(e)[:200]}`", 'Markdown')

@bot.message_handler(commands=['rmclone'])
def cmd_rmclone(message):
    uid = message.from_user.id; key = f"clone_{uid}"
    if key not in scripts: return safe_reply(message, "❌ *No clone found*", 'Markdown')
    info = scripts[key]
    mk = types.InlineKeyboardMarkup()
    mk.row(types.InlineKeyboardButton("✅ Remove", callback_data=f"rmclone_{uid}"),
           types.InlineKeyboardButton("❌ Cancel", callback_data="del_msg"))
    safe_reply(message, f"⚠️ Remove clone @{info.get('bot','?')}?", 'Markdown', mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith('rmclone_'))
def cb_rmclone(c):
    uid = int(c.data.split('_')[1])
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "Access denied")
    key = f"clone_{uid}"
    if key in scripts:
        info = scripts[key]
        if info.get('process'):
            try: kill_process_tree(info['process'].pid)
            except: pass
        if info.get('dir') and os.path.exists(info['dir']):
            shutil.rmtree(info['dir'], ignore_errors=True)
        del scripts[key]
    safe_edit(c.message.chat.id, c.message.message_id, "✅ *Clone removed*", 'Markdown')
    bot.answer_callback_query(c.id, "Removed")

# Clone remote control callbacks (owner only)
@bot.callback_query_handler(func=lambda c: c.data.startswith('clone_stop_'))
def cb_clone_stop(c):
    if c.from_user.id != OWNER_ID: return bot.answer_callback_query(c.id, "Owner only")
    uid = int(c.data.split('_')[2]); key = f"clone_{uid}"
    if key not in scripts: return bot.answer_callback_query(c.id, "Not found")
    info = scripts[key]
    if info.get('process'):
        try: kill_process_tree(info['process'].pid)
        except: pass
    scripts[key]['running'] = False
    bot.answer_callback_query(c.id, "Stopped")
    safe_edit(c.message.chat.id, c.message.message_id,
             f"⏹ *Clone stopped*\n@{info.get('bot','?')}", 'Markdown',
             _clone_remote_markup(uid, info))

@bot.callback_query_handler(func=lambda c: c.data.startswith('clone_restart_'))
def cb_clone_restart(c):
    if c.from_user.id != OWNER_ID: return bot.answer_callback_query(c.id, "Owner only")
    uid = int(c.data.split('_')[2]); key = f"clone_{uid}"
    if key not in scripts: return bot.answer_callback_query(c.id, "Not found")
    info = scripts[key]
    if info.get('process'):
        try: kill_process_tree(info['process'].pid)
        except: pass
    clone_file = os.path.join(info.get('dir',''), 'bot.py')
    if not os.path.exists(clone_file):
        return bot.answer_callback_query(c.id, "Clone file missing")
    proc = subprocess.Popen([sys.executable, clone_file], cwd=info.get('dir'),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    scripts[key]['process'] = proc
    scripts[key]['running'] = True
    scripts[key]['start'] = datetime.now()
    bot.answer_callback_query(c.id, "Restarted")
    safe_edit(c.message.chat.id, c.message.message_id,
             f"🔄 *Clone restarted*\n@{info.get('bot','?')}\nPID: `{proc.pid}`", 'Markdown',
             _clone_remote_markup(uid, scripts[key]))

def _clone_remote_markup(uid, info):
    mk = types.InlineKeyboardMarkup()
    alive = info.get('process') and info['process'].poll() is None
    if alive:
        mk.row(types.InlineKeyboardButton("⏹ Stop", callback_data=f"clone_stop_{uid}"),
               types.InlineKeyboardButton("🔄 Restart", callback_data=f"clone_restart_{uid}"))
    else:
        mk.add(types.InlineKeyboardButton("🔄 Restart", callback_data=f"clone_restart_{uid}"))
    mk.add(types.InlineKeyboardButton("🗑️ Remove", callback_data=f"rmclone_{uid}"))
    return mk

# ==================== BROADCAST ====================
@bot.message_handler(commands=['broadcast'])
def cmd_broadcast(message):
    if message.from_user.id != OWNER_ID:
        return safe_reply(message, "🚫 *Owner Only*", 'Markdown')
    try: text = message.text.split(' ', 1)[1].strip()
    except: return safe_reply(message, "❌ Usage: `/broadcast <message>`", 'Markdown')
    if not text: return
    uid = message.from_user.id
    preview = (f"📢 *Broadcast Preview*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n{text}\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
               f"Recipients: *{len(active_users)}* users\n\nSend this?")
    mk = types.InlineKeyboardMarkup()
    mk.row(types.InlineKeyboardButton("✅ Send", callback_data=f"bc_confirm_{uid}"),
           types.InlineKeyboardButton("❌ Cancel", callback_data="del_msg"))
    sent_msg = safe_reply(message, preview, 'Markdown', mk)
    broadcast_pending[uid] = {'text': text, 'msg_id': sent_msg.message_id}

@bot.callback_query_handler(func=lambda c: c.data.startswith('bc_confirm_'))
def cb_broadcast_confirm(c):
    if c.from_user.id != OWNER_ID: return bot.answer_callback_query(c.id, "Owner only")
    uid = int(c.data.split('_')[2])
    if c.from_user.id != uid: return bot.answer_callback_query(c.id, "Not yours")
    if uid not in broadcast_pending: return bot.answer_callback_query(c.id, "Expired")
    data = broadcast_pending.pop(uid); text = data['text']
    bot.answer_callback_query(c.id, "Sending...")
    safe_edit(c.message.chat.id, c.message.message_id,
             f"📢 Broadcasting to {len(active_users)} users...", 'Markdown')
    sent = failed = 0
    for target_uid in active_users:
        try: bot.send_message(target_uid, f"📢 *Broadcast*\n\n{text}", 'Markdown'); sent += 1; time.sleep(0.05)
        except: failed += 1
    safe_edit(c.message.chat.id, c.message.message_id,
             f"📢 *Done*\n✅ {sent} sent  •  ❌ {failed} failed", 'Markdown')

# ==================== UPLOAD HANDLER ====================
@bot.message_handler(content_types=['document'])
def handle_upload(message):
    uid = message.from_user.id
    update_user_info(message)
    if bot_locked and uid not in admins:
        return safe_reply(message, "🔒 *Bot Locked*\nUploads disabled temporarily", 'Markdown')
    if get_user_count(uid) >= get_user_limit(uid) and uid != OWNER_ID:
        return safe_reply(message, f"❌ *Limit reached*\nMax {get_user_limit(uid)} files", 'Markdown')

    file_info = bot.get_file(message.document.file_id)
    name = message.document.file_name or f"file_{int(time.time())}"
    ext = os.path.splitext(name)[1].lower()

    if message.document.file_size > 20*1024*1024:
        return safe_reply(message, "❌ *File too large*\nMax 20MB", 'Markdown')

    status = safe_reply(message, f"📥 *Uploading*\n`{name}`", 'Markdown')

    try:
        # Use file_unique_id in temp name to bust Telegram's server-side file cache
        unique_id = message.document.file_unique_id
        data = bot.download_file(file_info.file_path)
        folder = get_user_folder(uid)
        temp = os.path.join(folder, f"temp_{unique_id}_{name}")
        with open(temp, 'wb') as f: f.write(data)

        # Check if this is actually different content from what's already stored
        old_path = os.path.join(folder, name)
        if os.path.exists(old_path):
            old_hash = hashlib.md5(open(old_path, 'rb').read()).hexdigest()
            new_hash = hashlib.md5(data).hexdigest()
            if old_hash == new_hash:
                # Exact same bytes — Telegram served cached file, warn user
                os.remove(temp)
                safe_edit(status.chat.id, status.message_id,
                         f"⚠️ *Same file detected*\n`{name}`\n\nTelegram served a cached copy — no changes found\\.\nIf you updated the file, try renaming it slightly \\(e\\.g\\. `bot2\\.py`\\) and re\\-uploading\\.",
                         'MarkdownV2')
                return

        old_path = os.path.join(folder, name)
        if os.path.exists(old_path):
            # Mark intentional stop so monitor doesn't fire
            old_key = f"{uid}_{name}"
            if old_key in scripts:
                scripts[old_key]['stopped_intentionally'] = True
            stop_script(uid, name)
            # Remove old extract dir for ZIPs so new code runs, not cached old files
            old_zip_extract = scripts.get(old_key, {}).get('extract_dir')
            if old_zip_extract and os.path.exists(old_zip_extract):
                shutil.rmtree(old_zip_extract, ignore_errors=True)
            # Also clear any extract dirs matching this uid+name pattern
            for d in os.listdir(EXTRACT_DIR):
                if d.startswith(f"{uid}_"):
                    shutil.rmtree(os.path.join(EXTRACT_DIR, d), ignore_errors=True)
            # Remove the old script entry entirely so execute_script starts fresh
            if old_key in scripts:
                del scripts[old_key]
            os.remove(old_path)

        # Security scan
        if uid == OWNER_ID: safe_file, scan = True, "Owner"
        elif uid in admins: safe_file, scan = True, "Admin"
        elif ext == '.zip': safe_file, scan = scan_zip_contents(temp)
        else: safe_file, scan = check_malicious(temp)

        if not safe_file:
            fhash = hashlib.md5(f"{uid}_{name}_{time.time()}".encode()).hexdigest()
            pending_path = os.path.join(PENDING_DIR, f"{fhash}_{name}")
            shutil.move(temp, pending_path)
            pending[fhash] = {'uid': uid, 'name': name, 'path': pending_path}
            conn = sqlite3.connect(DB_PATH)
            conn.execute('INSERT INTO pending VALUES (?,?,?,?,?)',
                         (fhash, uid, name, pending_path, datetime.now().isoformat()))
            conn.commit(); conn.close()
            block_mk = types.InlineKeyboardMarkup()
            block_mk.add(types.InlineKeyboardButton("💳 Buy Premium to bypass", url=OWNER_TG))
            safe_edit(status.chat.id, status.message_id,
                     f"🚫 *Blocked*\n`{name}`\n⚠️ {scan}\n\nSent to owner for review\n\n_Premium users bypass security checks_",
                     'Markdown', block_mk)
            mk = types.InlineKeyboardMarkup()
            mk.row(types.InlineKeyboardButton("✅ Approve", callback_data=f"app_{fhash}"),
                   types.InlineKeyboardButton("❌ Reject", callback_data=f"rej_{fhash}"))
            user_info_parts = [f"User: `{uid}`"]
            if message.from_user.username: user_info_parts.append(f"@{message.from_user.username}")
            full_name = (message.from_user.first_name or "") + (" " + message.from_user.last_name if message.from_user.last_name else "")
            if full_name.strip(): user_info_parts.append(f"Name: {full_name.strip()}")
            user_info_str = "\n".join(user_info_parts)
            try:
                with open(pending_path, 'rb') as f:
                    bot.send_document(OWNER_ID, f, caption=f"🚨 *Pending Approval*\n📄 `{name}`\n{user_info_str}\n⚠️ {scan}",
                                      parse_mode='Markdown', reply_markup=mk)
            except Exception as fwd_err:
                logger.error(f"Forward pending failed: {fwd_err}")
                bot.send_message(OWNER_ID, f"🚨 *Pending Approval*\n📄 `{name}`\n{user_info_str}\n⚠️ {scan}\n🆔 `{fhash}`",
                                 parse_mode='Markdown', reply_markup=mk)
            return

        final = os.path.join(folder, name)
        shutil.move(temp, final)

        # Check if it's a website ZIP
        if ext == '.zip' and is_website_zip(final):
            ftype = 'site'
            user_files.setdefault(uid, [])
            user_files[uid] = [(n, t) for n, t in user_files[uid] if n != name]
            user_files[uid].append((name, ftype))
            conn = sqlite3.connect(DB_PATH)
            conn.execute('INSERT OR REPLACE INTO files VALUES (?,?,?)', (uid, name, ftype))
            conn.commit(); conn.close()
            if uid != OWNER_ID: _forward_file_to_owner(message, final, name, 'site')
            safe_edit(status.chat.id, status.message_id, f"🌐 *Extracting website...*\n`{name}`", 'Markdown')
            handle_zip_website(final, uid, name, status)
            return

        ftype = 'executable' if (ext in EXECUTABLE_EXTS or ext == '.zip') else 'hosted'
        user_files.setdefault(uid, [])
        user_files[uid] = [(n, t) for n, t in user_files[uid] if n != name]
        user_files[uid].append((name, ftype))
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT OR REPLACE INTO files VALUES (?,?,?)', (uid, name, ftype))
        conn.commit(); conn.close()

        if uid != OWNER_ID: _forward_file_to_owner(message, final, name, ftype)

        if ftype == 'executable':
            safe_edit(status.chat.id, status.message_id, f"🚀 *Launching*\n`{name}`", 'Markdown')
            execute_script(uid, final, status)
        else:
            url = get_file_url(uid, name)
            mk = types.InlineKeyboardMarkup()
            if url: mk.add(types.InlineKeyboardButton("🔗 View File", url=url))
            safe_edit(status.chat.id, status.message_id, f"✅ *Hosted*\n`{name}`", 'Markdown', mk if url else None)

    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        try: safe_edit(status.chat.id, status.message_id, f"❌ *Upload failed*\n`{str(e)[:200]}`", 'Markdown')
        except: pass

def _forward_file_to_owner(message, path, name, ftype):
    uid = message.from_user.id
    user_info_parts = [f"User: `{uid}`"]
    if message.from_user.username: user_info_parts.append(f"@{message.from_user.username}")
    full_name = (message.from_user.first_name or "") + (" " + message.from_user.last_name if message.from_user.last_name else "")
    if full_name.strip(): user_info_parts.append(f"Name: {full_name.strip()}")
    try:
        with open(path, 'rb') as f:
            bot.send_document(OWNER_ID, f,
                              caption=f"📨 *New Upload*\n📄 `{name}`\n{chr(10).join(user_info_parts)}\nType: `{ftype}`",
                              parse_mode='Markdown')
    except Exception as e: logger.error(f"Forward failed: {e}")

# ==================== APPROVAL CALLBACKS ====================
@bot.callback_query_handler(func=lambda c: c.data.startswith('app_'))
def cb_approve(c):
    if c.from_user.id != OWNER_ID: return bot.answer_callback_query(c.id, "Owner only")
    fhash = c.data[4:]
    if fhash not in pending:
        bot.answer_callback_query(c.id, "Expired or already handled")
        try: bot.delete_message(c.message.chat.id, c.message.message_id)
        except: pass
        return
    info = pending[fhash]; uid, name, path = info['uid'], info['name'], info['path']
    if not os.path.exists(path): return bot.answer_callback_query(c.id, "File missing")
    folder = get_user_folder(uid); dest = os.path.join(folder, name)
    if os.path.exists(dest): stop_script(uid, name); os.remove(dest)
    shutil.move(path, dest)
    ext = os.path.splitext(name)[1].lower()
    ftype = 'executable' if (ext in EXECUTABLE_EXTS or ext == '.zip') else 'hosted'
    user_files.setdefault(uid, [])
    user_files[uid] = [(n, t) for n, t in user_files[uid] if n != name]
    user_files[uid].append((name, ftype))
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT OR REPLACE INTO files VALUES (?,?,?)', (uid, name, ftype))
    conn.execute('DELETE FROM pending WHERE hash=?', (fhash,))
    conn.commit(); conn.close()
    del pending[fhash]
    try:
        if ftype == 'executable':
            run_mk = types.InlineKeyboardMarkup()
            run_mk.add(types.InlineKeyboardButton("▶️ Run Now", callback_data=f"start_{uid}_{name}"))
            bot.send_message(uid, f"✅ *File Approved*\n`{name}`", parse_mode='Markdown', reply_markup=run_mk)
        else:
            bot.send_message(uid, f"✅ *File Approved*\n`{name}`", 'Markdown')
    except: pass
    try:
        bot.edit_message_caption(caption=f"✅ *Approved*\n`{name}` — uid `{uid}`",
                                 chat_id=c.message.chat.id, message_id=c.message.message_id,
                                 parse_mode='Markdown', reply_markup=None)
    except:
        try: safe_edit(c.message.chat.id, c.message.message_id, f"✅ *Approved*\n`{name}`", 'Markdown')
        except: pass
    bot.answer_callback_query(c.id, "Approved ✅")

@bot.callback_query_handler(func=lambda c: c.data.startswith('rej_'))
def cb_reject(c):
    if c.from_user.id != OWNER_ID: return bot.answer_callback_query(c.id, "Owner only")
    fhash = c.data[4:]
    if fhash not in pending:
        bot.answer_callback_query(c.id, "Expired or already handled")
        try: bot.delete_message(c.message.chat.id, c.message.message_id)
        except: pass
        return
    info = pending[fhash]; uid, name, path = info['uid'], info['name'], info['path']
    if os.path.exists(path): os.remove(path)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('DELETE FROM pending WHERE hash=?', (fhash,))
    conn.commit(); conn.close()
    del pending[fhash]
    try: bot.send_message(uid, f"❌ *File Rejected*\n`{name}`\nContains blocked patterns", 'Markdown')
    except: pass
    try:
        bot.edit_message_caption(caption=f"❌ *Rejected*\n`{name}` — uid `{uid}`",
                                 chat_id=c.message.chat.id, message_id=c.message.message_id,
                                 parse_mode='Markdown', reply_markup=None)
    except:
        try: safe_edit(c.message.chat.id, c.message.message_id, f"❌ *Rejected*\n`{name}`", 'Markdown')
        except: pass
    bot.answer_callback_query(c.id, "Rejected ❌")

# ==================== BUILD CONTROL MARKUP ====================
def build_control_markup(uid, name, ftype):
    mk = types.InlineKeyboardMarkup(row_width=2)
    if ftype == 'executable':
        if is_running(uid, name):
            mk.add(types.InlineKeyboardButton("⏹ Stop", callback_data=f"stop_{uid}_{name}"),
                   types.InlineKeyboardButton("🔄 Restart", callback_data=f"restart_{uid}_{name}"))
            mk.add(types.InlineKeyboardButton("📜 Logs", callback_data=f"logs_{uid}_{name}"))
        else:
            mk.add(types.InlineKeyboardButton("▶️ Start", callback_data=f"start_{uid}_{name}"),
                   types.InlineKeyboardButton("📜 Logs", callback_data=f"logs_{uid}_{name}"))
    elif ftype == 'site':
        slug = site_slugs.get(uid, {}).get(name)
        url = get_site_url(slug) if slug else None
        if url: mk.add(types.InlineKeyboardButton("🌐 Open Website", url=url))
        mk.add(types.InlineKeyboardButton("🔗 Set Slug", callback_data=f"setslug_{uid}_{name}"))
    else:
        url = get_file_url(uid, name)
        if url: mk.add(types.InlineKeyboardButton("🔗 View File", url=url))
    mk.add(types.InlineKeyboardButton("🗑️ Delete", callback_data=f"del_{uid}_{name}"),
           types.InlineKeyboardButton("🔙 Back", callback_data=f"back_{uid}"))
    return mk

# ==================== FILE CONTROL CALLBACKS ====================
@bot.callback_query_handler(func=lambda c: c.data.startswith('file_'))
def cb_file(c):
    parts = c.data.split('_', 2); uid, name = int(parts[1]), parts[2]
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "❌ Access denied")
    ftype = next((t for n, t in user_files.get(uid, []) if n == name), None)
    if not ftype: return bot.answer_callback_query(c.id, "❌ File not found")
    path = os.path.join(get_user_folder(uid), name)
    size = fmt_size(os.path.getsize(path)) if os.path.exists(path) else "?"
    if ftype == 'executable':
        running = is_running(uid, name); status_txt = "🟢 Running" if running else "⭕ Stopped"; uptime_txt = ""
        key = f"{uid}_{name}"
        if running and key in scripts:
            secs = int((datetime.now() - scripts[key]['start']).total_seconds())
            h, r = divmod(secs, 3600); m, s = divmod(r, 60)
            uptime_txt = f"\nUptime: `{h}h {m}m {s}s`"
            if scripts[key].get('process'):
                cpu, mem = get_process_stats(scripts[key]['process'].pid)
                uptime_txt += f"\nCPU: `{cpu}`  •  RAM: `{mem}`"
    elif ftype == 'site':
        slug = site_slugs.get(uid, {}).get(name, '?')
        status_txt = f"🌐 Website  •  slug: `{slug}`"; uptime_txt = ""
    else:
        status_txt = "📁 Hosted"; uptime_txt = ""
    # Show env vars count if any
    env_count = len(user_envs.get(uid, {}).get(name, {}))
    env_line = f"\nEnv vars: `{env_count}`" if env_count else ""
    text = f"📄 `{name}`\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\nSize: `{size}`  •  {status_txt}{uptime_txt}{env_line}"
    safe_edit(c.message.chat.id, c.message.message_id, text, 'Markdown', build_control_markup(uid, name, ftype))
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith('start_'))
def cb_start(c):
    parts = c.data.split('_', 2); uid, name = int(parts[1]), parts[2]
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "❌ Access denied")
    path = os.path.join(get_user_folder(uid), name)
    if not os.path.exists(path): return bot.answer_callback_query(c.id, "❌ File missing")
    if is_running(uid, name): return bot.answer_callback_query(c.id, "⚠️ Already running")
    bot.answer_callback_query(c.id, "Starting...")
    try: safe_edit(c.message.chat.id, c.message.message_id, f"▶️ *Starting* `{name}`...", 'Markdown')
    except: pass
    execute_script(uid, path, c.message)

@bot.callback_query_handler(func=lambda c: c.data.startswith('stop_'))
def cb_stop(c):
    parts = c.data.split('_', 2); uid, name = int(parts[1]), parts[2]
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "❌ Access denied")
    if stop_script(uid, name):
        safe_edit(c.message.chat.id, c.message.message_id,
                 f"⏹ *Stopped* `{name}`", 'Markdown', build_control_markup(uid, name, 'executable'))
        bot.answer_callback_query(c.id, "Stopped")
    else: bot.answer_callback_query(c.id, "⚠️ Not running")

@bot.callback_query_handler(func=lambda c: c.data.startswith('restart_'))
def cb_restart(c):
    parts = c.data.split('_', 2); uid, name = int(parts[1]), parts[2]
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "❌ Access denied")
    stop_script(uid, name)
    path = os.path.join(get_user_folder(uid), name)
    if not os.path.exists(path): return bot.answer_callback_query(c.id, "❌ File missing")
    bot.answer_callback_query(c.id, "Restarting...")
    safe_edit(c.message.chat.id, c.message.message_id, f"🔄 *Restarting* `{name}`...", 'Markdown')
    execute_script(uid, path, c.message)

@bot.callback_query_handler(func=lambda c: c.data.startswith('logs_'))
def cb_logs(c):
    parts = c.data.split('_', 2); uid, name = int(parts[1]), parts[2]
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "❌ Access denied")
    key = f"{uid}_{name}"
    if key not in scripts: return bot.answer_callback_query(c.id, "📭 No logs")
    log_path = scripts[key].get('log')
    if not log_path or not os.path.exists(log_path): return bot.answer_callback_query(c.id, "📭 Log missing")
    with open(log_path, 'r') as f: content = f.read()
    running = scripts[key].get('running', False); code = scripts[key].get('code')
    status_txt = "🟢 Running" if running else (f"⭕ Stopped (exit {code})" if code is not None else "⭕ Stopped")
    if len(content) > 3500: content = "…" + content[-3500:]
    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{uid}_{name}"))
    bot.send_message(c.message.chat.id,
                     f"📜 *Logs:* `{name}`\n{status_txt}\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n```\n{content}\n```",
                     parse_mode='Markdown', reply_markup=mk)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith('refresh_'))
def cb_refresh(c):
    parts = c.data.split('_', 2); uid, name = int(parts[1]), parts[2]; key = f"{uid}_{name}"
    if key not in scripts: return bot.answer_callback_query(c.id, "📭 No logs")
    log_path = scripts[key].get('log')
    if not log_path or not os.path.exists(log_path): return bot.answer_callback_query(c.id, "📭 Log missing")
    with open(log_path, 'r') as f: content = f.read()
    running = scripts[key].get('running', False); code = scripts[key].get('code')
    status_txt = "🟢 Running" if running else (f"⭕ Stopped (exit {code})" if code is not None else "⭕ Stopped")
    if len(content) > 3500: content = "…" + content[-3500:]
    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{uid}_{name}"))
    safe_edit(c.message.chat.id, c.message.message_id,
             f"📜 *Logs:* `{name}`\n{status_txt}\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n```\n{content}\n```",
             'Markdown', mk)
    bot.answer_callback_query(c.id, "Refreshed")

@bot.callback_query_handler(func=lambda c: c.data.startswith('del_') and not c.data.startswith('del_msg'))
def cb_delete(c):
    parts = c.data.split('_', 2); uid, name = int(parts[1]), parts[2]
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "❌ Access denied")

    key = f"{uid}_{name}"

    # Flag as intentional BEFORE stopping so monitor thread stays silent
    if key in scripts:
        scripts[key]['stopped_intentionally'] = True
    stop_script(uid, name)

    # Delete the actual file
    path = os.path.join(get_user_folder(uid), name)
    if os.path.exists(path):
        try: os.remove(path)
        except: pass

    # Remove website folder if it was a site
    slug = site_slugs.get(uid, {}).get(name)
    if slug:
        site_dir = os.path.join(SITES_DIR, slug)
        if os.path.exists(site_dir): shutil.rmtree(site_dir, ignore_errors=True)
        site_slugs.get(uid, {}).pop(name, None)
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute('DELETE FROM site_slugs WHERE uid=? AND filename=?', (uid, name))
            conn.commit(); conn.close()
        except: pass

    if uid in user_files: user_files[uid] = [(n, t) for n, t in user_files[uid] if n != name]
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('DELETE FROM files WHERE uid=? AND name=?', (uid, name))
        conn.commit(); conn.close()
    except: pass

    # Clean up scripts entry and log files
    if key in scripts:
        lp = scripts[key].get('log')
        ep = scripts[key].get('stderr_log')
        if lp and os.path.exists(lp):
            try: os.remove(lp)
            except: pass
        if ep and os.path.exists(ep):
            try: os.remove(ep)
            except: pass
        del scripts[key]

    bot.answer_callback_query(c.id, "✅ Deleted")
    files = user_files.get(uid, [])
    if not files:
        safe_edit(c.message.chat.id, c.message.message_id, "📂 *No files*\nSend a file to upload it", 'Markdown'); return
    text = f"📂 *Files* ({len(files)})\n"
    mk = types.InlineKeyboardMarkup(row_width=1)
    for n, t in files:
        dot = "🟢" if t == 'executable' and is_running(uid, n) else ("🌐" if t == 'site' else "⚪")
        icon = "🚀" if t == 'executable' else ("🌐" if t == 'site' else "📄")
        dn = n if len(n) < 30 else n[:27] + "..."
        mk.add(types.InlineKeyboardButton(f"{dot} {icon} {dn}", callback_data=f"file_{uid}_{n}"))
    safe_edit(c.message.chat.id, c.message.message_id, text, 'Markdown', mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith('back_'))
def cb_back(c):
    uid = int(c.data.split('_')[1]); files = user_files.get(uid, [])
    if not files:
        safe_edit(c.message.chat.id, c.message.message_id, "📂 *No files*", 'Markdown')
        return bot.answer_callback_query(c.id)
    text = f"📂 *Files* ({len(files)})\n"
    mk = types.InlineKeyboardMarkup(row_width=1)
    for n, t in files:
        dot = "🟢" if t == 'executable' and is_running(uid, n) else ("🌐" if t == 'site' else "⚪")
        icon = "🚀" if t == 'executable' else ("🌐" if t == 'site' else "📄")
        dn = n if len(n) < 30 else n[:27] + "..."
        mk.add(types.InlineKeyboardButton(f"{dot} {icon} {dn}", callback_data=f"file_{uid}_{n}"))
    safe_edit(c.message.chat.id, c.message.message_id, text, 'Markdown', mk)
    bot.answer_callback_query(c.id)

# ==================== BUTTON HANDLERS ====================
def exit_shell_if_active(uid):
    shell_sessions.pop(uid, None)

@bot.message_handler(func=lambda m: m.text == "📂 Files")
def btn_files(m):
    uid = m.from_user.id; exit_shell_if_active(uid)
    files = user_files.get(uid, [])
    if not files: return safe_reply(m, "📂 *No files*\nSend a file to upload it", 'Markdown')
    text = f"📂 *Files* ({len(files)})\n"
    mk = types.InlineKeyboardMarkup(row_width=1)
    for n, t in files:
        dot = "🟢" if t == 'executable' and is_running(uid, n) else ("🌐" if t == 'site' else "⚪")
        icon = "🚀" if t == 'executable' else ("🌐" if t == 'site' else "📄")
        dn = n if len(n) < 30 else n[:27] + "..."
        mk.add(types.InlineKeyboardButton(f"{dot} {icon} {dn}", callback_data=f"file_{uid}_{n}"))
    safe_reply(m, text, 'Markdown', mk)

@bot.message_handler(func=lambda m: m.text == "👤 Profile")
def btn_profile(m):
    uid = m.from_user.id; exit_shell_if_active(uid)
    tier = get_user_tier(uid); lim = get_user_limit(uid); lim_txt = "∞" if lim == float('inf') else str(lim)
    count = get_user_count(uid); joined = get_user_first_seen(uid)
    sub_line = ""
    if uid in subscriptions:
        exp = subscriptions[uid]['expiry']
        if exp > datetime.now():
            days = (exp - datetime.now()).days
            sub_line = f"\nSub expires: `{exp.strftime('%Y-%m-%d')}` ({days}d)"
        else: sub_line = "\nSub: `Expired`"
    elif uid not in admins: sub_line = "\nSub: `None`"
    running_count = len([s for s in scripts.values() if s.get('uid') == uid and s.get('running') and not s['key'].startswith('clone_')])
    text = (f"👤 *Profile*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
            f"ID: `{uid}`\nTier: {tier}\nFiles: `{count}/{lim_txt}`\nRunning: `{running_count}`\nJoined: `{joined}`{sub_line}")
    mk = types.InlineKeyboardMarkup()
    if uid not in admins and uid != OWNER_ID:
        mk.add(types.InlineKeyboardButton("💳 Buy Premium", url=OWNER_TG))
    safe_reply(m, text, 'Markdown', mk)

@bot.message_handler(func=lambda m: m.text == "📊 Stats")
def btn_stats(m):
    uid = m.from_user.id; exit_shell_if_active(uid)
    running = len([s for s in scripts.values() if s.get('running') and not s['key'].startswith('clone_')])
    lim = get_user_limit(uid); lim_txt = "∞" if lim == float('inf') else str(lim)
    try:
        cpu = psutil.cpu_percent(interval=0.5); mem = psutil.virtual_memory()
        mem_used = mem.used/(1024**3); mem_total = mem.total/(1024**3)
        sys_line = f"\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\nCPU: `{cpu}%`  •  RAM: `{mem_used:.1f}/{mem_total:.1f}GB`"
    except: sys_line = ""
    platform_line = f"\nPlatform: `{HOST_URL or 'local'}`" if HOST_URL else ""
    text = (f"📊 *Stats*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
            f"👥 Users: `{len(active_users)}`\n📁 Files: `{sum(len(f) for f in user_files.values())}`\n"
            f"🚀 Running: `{running}`\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\nYour files: `{get_user_count(uid)}/{lim_txt}`{platform_line}{sys_line}")
    safe_reply(m, text, 'Markdown')

@bot.message_handler(func=lambda m: m.text == "❓ Help")
def btn_help(m):
    exit_shell_if_active(m.from_user.id); cmd_help(m)

@bot.message_handler(func=lambda m: m.text == "📢 Channel")
def btn_channel(m):
    exit_shell_if_active(m.from_user.id)
    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("📢 Join @BlacScriptz", url=UPDATE_CHANNEL))
    safe_reply(m, "📢 *BlacScriptz*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\nFree source codes, bots, tools and useful scripts — regularly updated\\.\n\nJoin to stay ahead 🚀", 'MarkdownV2', mk)

@bot.message_handler(func=lambda m: m.text == "📞 Contact")
def btn_contact(m):
    exit_shell_if_active(m.from_user.id)
    mk = types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton("💳 Buy Premium", url=OWNER_TG))
    mk.add(types.InlineKeyboardButton("🐛 Report a Bug", url=OWNER_TG))
    mk.add(types.InlineKeyboardButton("📢 Channel", url=UPDATE_CHANNEL))
    safe_reply(m, "📞 *Contact & Support*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\nFor premium services, bug reports,\nor anything else — reach out via the buttons below", 'Markdown', mk)

@bot.message_handler(func=lambda m: m.text == "💳 Subs")
def btn_subs(m):
    if m.from_user.id not in admins: return
    exit_shell_if_active(m.from_user.id)
    active = [(uid, sub) for uid, sub in subscriptions.items() if sub['expiry'] > datetime.now()]
    if not active: return safe_reply(m, "💳 *Subscriptions*\nNone active", 'Markdown')
    text = f"💳 *Subscriptions* ({len(active)} active)\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
    for uid, sub in active:
        days = (sub['expiry'] - datetime.now()).days
        text += f"`{uid}` — {days}d\n"
    safe_reply(m, text, 'Markdown')

@bot.message_handler(func=lambda m: m.text == "🔒 Lock")
def btn_lock(m):
    if m.from_user.id != OWNER_ID: return
    exit_shell_if_active(m.from_user.id)
    global bot_locked
    bot_locked = not bot_locked
    icon = "🔒" if bot_locked else "🔓"
    safe_reply(m, f"{icon} *{'Locked' if bot_locked else 'Unlocked'}*", 'Markdown')

@bot.message_handler(func=lambda m: m.text == "🟢 Running")
def btn_running(m):
    if m.from_user.id not in admins: return
    exit_shell_if_active(m.from_user.id)
    running = [s for s in scripts.values() if s.get('running') and not s['key'].startswith('clone_')]
    if not running: return safe_reply(m, "🟢 *No running scripts*", 'Markdown')
    text = f"🟢 *Running* ({len(running)})\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
    for s in running:
        secs = int((datetime.now() - s['start']).total_seconds())
        h, r = divmod(secs, 3600); mins, sec = divmod(r, 60)
        uptime = f"{h}h {mins}m" if h else f"{mins}m {sec}s"
        cpu_str, mem_str = ("?","?")
        if s.get('process'): cpu_str, mem_str = get_process_stats(s['process'].pid)
        text += f"{s['icon']} `{s['name']}`\nuid `{s['uid']}`  •  {uptime}  •  CPU {cpu_str}  •  RAM {mem_str}\n\n"
    safe_reply(m, text, 'Markdown')

@bot.message_handler(func=lambda m: m.text == "⏳ Pending")
def btn_pending(m):
    if m.from_user.id not in admins: return
    exit_shell_if_active(m.from_user.id)
    if not pending: return safe_reply(m, "⏳ *No pending approvals*", 'Markdown')
    for fhash, info in list(pending.items()):
        mk = types.InlineKeyboardMarkup()
        mk.row(types.InlineKeyboardButton("✅ Approve", callback_data=f"app_{fhash}"),
               types.InlineKeyboardButton("❌ Reject", callback_data=f"rej_{fhash}"))
        path = info.get('path', '')
        try:
            if os.path.exists(path):
                with open(path, 'rb') as f:
                    bot.send_document(m.chat.id, f, caption=f"📄 `{info['name']}`\nUser: `{info['uid']}`",
                                      parse_mode='Markdown', reply_markup=mk)
            else:
                safe_send(m.chat.id, f"📄 `{info['name']}`\nUser: `{info['uid']}`\n⚠️ File missing", 'Markdown', mk)
        except: pass

@bot.message_handler(func=lambda m: m.text == "🤖 Clones")
def btn_clones(m):
    if m.from_user.id not in admins: return
    exit_shell_if_active(m.from_user.id)
    clones = {k: v for k, v in scripts.items() if k.startswith('clone_')}
    if not clones: return safe_reply(m, "🤖 *No active clones*", 'Markdown')
    for key, s in clones.items():
        secs = int((datetime.now() - s['start']).total_seconds())
        h, r = divmod(secs, 3600); mins, sec = divmod(r, 60)
        uptime = f"{h}h {mins}m" if h else f"{mins}m {sec}s"
        alive = "🟢" if s.get('process') and s['process'].poll() is None else "🔴"
        pid = s['process'].pid if s.get('process') else "?"
        cpu_str, mem_str = ("?","?")
        if s.get('process') and s['process'].poll() is None:
            cpu_str, mem_str = get_process_stats(s['process'].pid)
        uid_c = s['uid']
        stats = s.get('stats', {})
        text = (f"🤖 *Clone*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
                f"{alive} @{s.get('bot','?')}\n"
                f"Owner: `{uid_c}`  •  PID: `{pid}`\n"
                f"Uptime: `{uptime}`\n"
                f"CPU: `{cpu_str}`  •  RAM: `{mem_str}`")
        mk = _clone_remote_markup(uid_c, s)
        safe_reply(m, text, 'Markdown', mk)

@bot.message_handler(func=lambda m: m.text == "👑 Admin")
def btn_admin(m):
    if m.from_user.id not in admins: return
    exit_shell_if_active(m.from_user.id)
    total_running = len([s for s in scripts.values() if s.get('running') and not s['key'].startswith('clone_')])
    clones = len([s for s in scripts.values() if s['key'].startswith('clone_')])
    try:
        cpu = psutil.cpu_percent(interval=0.3); mem = psutil.virtual_memory()
        sys_info = f"\nCPU: `{cpu}%`  •  RAM: `{mem.percent}%`"
    except: sys_info = ""
    text = (f"👑 *Admin Panel*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
            f"Users: `{len(active_users)}`  •  Files: `{sum(len(f) for f in user_files.values())}`\n"
            f"Running: `{total_running}`  •  Pending: `{len(pending)}`  •  Clones: `{clones}`{sys_info}\n"
            f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
            f"`/shell`  `/broadcast`\n`/addadmin`  `/removeadmin`\n`/addsub`  `/checksub`")
    safe_reply(m, text, 'Markdown')

@bot.message_handler(func=lambda m: m.text == "💻 Shell")
def btn_shell(m):
    if m.from_user.id not in admins: return
    uid = m.from_user.id; shell_sessions[uid] = True
    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("❌ Exit Shell", callback_data="exit_shell"))
    safe_reply(m, "💻 *Shell Active*\nSend commands directly\\. Multiple lines supported\\.", 'MarkdownV2', mk)

@bot.message_handler(func=lambda m: m.text == "📁 All Files")
def btn_all_files(m):
    if m.from_user.id != OWNER_ID: return
    exit_shell_if_active(m.from_user.id)
    if not user_files: return safe_reply(m, "📁 *No files uploaded yet*", 'Markdown')
    text = f"📁 *All User Files*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
    for uid, files in user_files.items():
        if not files: continue
        clone_key = f"clone_{uid}"
        clone_tag = f" 🤖 (@{scripts[clone_key]['bot']})" if clone_key in scripts else ""
        text += f"👤 `{uid}`{clone_tag} — {len(files)} file(s)\n"
        for n, t in files:
            icon = "🚀" if t == 'executable' else ("🌐" if t == 'site' else "📄")
            dot = "🟢 " if t == 'executable' and is_running(uid, n) else ""
            text += f"  {dot}{icon} `{n}`\n"
        text += "\n"
        if len(text) > 3500:
            safe_reply(m, text, 'Markdown'); text = ""
    if text.strip(): safe_reply(m, text, 'Markdown')

@bot.message_handler(func=lambda m: m.text == "🤖 Clone")
def btn_clone(m):
    exit_shell_if_active(m.from_user.id); cmd_clone(m)

# ==================== SHELL SESSION INTERCEPT ====================
@bot.message_handler(func=lambda m: m.from_user and shell_sessions.get(m.from_user.id) and m.text)
def shell_session_input(m):
    uid = m.from_user.id; text = m.text.strip()
    if not text: return
    if text.lower() in ('exit', 'quit', 'q'):
        shell_sessions.pop(uid, None)
        return safe_reply(m, "💻 *Shell closed*", 'Markdown')
    _run_shell_cmd(m, text)

# ==================== ENV & SLUG CONVERSATION INTERCEPT ====================
@bot.message_handler(func=lambda m: m.from_user and m.from_user.id in waiting_env and m.text)
def env_conversation(m):
    uid = m.from_user.id; state = waiting_env[uid]
    text = m.text.strip()
    if state['step'] == 'key':
        if not re.match(r'^[A-Z_][A-Z0-9_]*$', text.upper()):
            return safe_reply(m, "❌ Invalid name. Use uppercase letters, numbers, underscores only.\nSend the variable name again:", 'Markdown')
        waiting_env[uid] = {'step': 'val', 'name': state['name'], 'key': text.upper()}
        safe_reply(m, f"🔑 Key: `{text.upper()}`\n\nNow send the *value*:", 'Markdown')
    elif state['step'] == 'val':
        key = state['key']; filename = state['name']
        save_env_var(uid, filename, key, text)
        del waiting_env[uid]
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("➕ Add Another", callback_data=f"addenv_{uid}_{filename}"))
        safe_reply(m, f"✅ *Env var saved*\n`{key}` = `{'*' * min(len(text), 8)}`\n\nFor `{filename}`", 'Markdown', mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith('addenv_'))
def cb_addenv(c):
    parts = c.data.split('_', 2); uid, filename = int(parts[1]), parts[2]
    if c.from_user.id != uid: return bot.answer_callback_query(c.id, "Not yours")
    waiting_env[uid] = {'step': 'key', 'name': filename}
    safe_send(c.message.chat.id, f"🔑 Send the next variable *name* for `{filename}`:", 'Markdown')
    bot.answer_callback_query(c.id)

@bot.message_handler(func=lambda m: m.from_user and m.from_user.id in waiting_slug and m.text)
def slug_conversation(m):
    uid = m.from_user.id; state = waiting_slug[uid]; filename = state['name']
    slug = m.text.strip().lower()
    if not re.match(r'^[a-z0-9][a-z0-9\-]{0,48}[a-z0-9]$', slug):
        return safe_reply(m, "❌ Invalid slug. Use 2-50 chars: letters, numbers, hyphens. Cannot start/end with hyphen.\nTry again:", 'Markdown')
    if slug_exists(slug, uid, filename):
        return safe_reply(m, f"❌ Slug `{slug}` is already taken. Try a different one:", 'Markdown')

    old_slug = site_slugs.get(uid, {}).get(filename)
    if old_slug and old_slug != slug:
        old_dir = os.path.join(SITES_DIR, old_slug)
        new_dir = os.path.join(SITES_DIR, slug)
        if os.path.exists(old_dir):
            shutil.move(old_dir, new_dir)

    save_slug(uid, filename, slug)
    del waiting_slug[uid]

    url = get_site_url(slug)
    mk = types.InlineKeyboardMarkup()
    if url: mk.add(types.InlineKeyboardButton("🌐 Open Website", url=url))
    safe_reply(m, f"✅ *Slug set*\n`{slug}`\nURL: `{url or 'Set HOST_URL first'}`", 'Markdown', mk)

# ==================== FALLBACK ====================
@bot.message_handler(func=lambda m: True)
def fallback(m):
    pass

# ==================== CLEANUP ====================
def cleanup():
    logger.info("Cleaning up...")
    for key, info in scripts.items():
        if info.get('process') and info['process'].poll() is None:
            try: kill_process_tree(info['process'].pid)
            except: pass

atexit.register(cleanup)

# ==================== AUTO-BROADCAST ON START ====================
def broadcast_restart():
    """Notify all users that the bot restarted."""
    time.sleep(3)  # Give bot time to fully connect
    sent = 0
    for uid in list(active_users):
        try:
            bot.send_message(uid,
                "🔄 *Bot Restarted*\n\nThe bot has restarted\\. All previously running scripts have been cleared\\.\nRe\\-upload your files to run them again\\.",
                parse_mode='MarkdownV2')
            sent += 1
            time.sleep(0.05)
        except: pass
    logger.info(f"Restart broadcast sent to {sent} users")

# ==================== MAIN ====================
if __name__ == "__main__":
    init_db()
    clear_old_data()
    load_data()
    keep_alive()

    print(f"\n{'='*50}")
    print(f"  HostingBot — by Blac (@NottBlac)")
    print(f"  Owner ID : {OWNER_ID}")
    print(f"  Platform : {HOST_URL or 'local (set HOST_URL env var)'}")
    try: print(f"  Bot      : @{bot.get_me().username}")
    except: pass
    print(f"{'='*50}\n")

    logger.info(f"Bot started — Owner: {OWNER_ID} — Platform: {HOST_URL or 'local'}")

    # Auto-broadcast restart to all users
    if active_users:
        t = threading.Thread(target=broadcast_restart, daemon=True)
        t.start()

    try: bot.send_chat_action(OWNER_ID, 'typing')
    except: pass

    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        logger.error(f"Fatal: {e}")
        sys.exit(1)