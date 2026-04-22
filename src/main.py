# -*- coding: utf-8 -*-
"""
HostingBot — by Blac (@NottBlac)
A professional multi‑user hosting bot with isolated per‑user VPS environments.
"""

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
import glob
import tempfile
import resource
import pty
import select
import termios
import struct
import fcntl

# ==================== CONFIGURATION ====================
TOKEN   = os.getenv('TELEGRAM_BOT_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', '8537538760'))
ADMIN_ID = int(os.getenv('ADMIN_ID', '8537538760'))
BOT_USERNAME   = os.getenv('BOT_USERNAME', '@NottBlac')
UPDATE_CHANNEL = os.getenv('UPDATE_CHANNEL', 'https://t.me/BlacScriptz')
OWNER_TG       = 'https://t.me/NottBlac'

# Paths
BASE_DIR    = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR  = os.path.join(BASE_DIR, 'uploads')
DB_DIR      = os.path.join(BASE_DIR, 'data')
DB_PATH     = os.path.join(DB_DIR,   'bot.db')
LOGS_DIR    = os.path.join(BASE_DIR, 'logs')
PENDING_DIR = os.path.join(BASE_DIR, 'pending')
EXTRACT_DIR = os.path.join(BASE_DIR, 'extracted')
SITES_DIR   = os.path.join(BASE_DIR, 'sites')
TEMP_DIR    = os.path.join(BASE_DIR, 'temp')

# Limits (tier‑based)
FREE_LIMIT  = 5
SUB_LIMIT   = 25
ADMIN_LIMIT = 999
OWNER_LIMIT = float('inf')

# Resource limits (RAM in bytes)
TIER_RAM = {
    'free': 1024 * 1024 * 1024,          # 1 GB
    'premium': 2 * 1024 * 1024 * 1024,   # 2 GB
    'admin': 4 * 1024 * 1024 * 1024,     # 4 GB
    'owner': None                        # unlimited
}

for _d in [UPLOAD_DIR, DB_DIR, LOGS_DIR, PENDING_DIR, EXTRACT_DIR, SITES_DIR, TEMP_DIR]:
    os.makedirs(_d, exist_ok=True)

# ==================== PLATFORM AUTO-DETECT ====================
def detect_host_url():
    if os.environ.get('RENDER_EXTERNAL_URL'):
        return os.environ['RENDER_EXTERNAL_URL'].rstrip('/')
    if os.environ.get('RENDER_SERVICE_NAME'):
        return f"https://{os.environ['RENDER_SERVICE_NAME']}.onrender.com"
    if os.environ.get('RAILWAY_PUBLIC_DOMAIN'):
        return f"https://{os.environ['RAILWAY_PUBLIC_DOMAIN']}".rstrip('/')
    if os.environ.get('RAILWAY_STATIC_URL'):
        return os.environ['RAILWAY_STATIC_URL'].rstrip('/')
    if os.environ.get('HEROKU_APP_NAME'):
        return f"https://{os.environ['HEROKU_APP_NAME']}.herokuapp.com"
    if os.environ.get('KOYEB_PUBLIC_DOMAIN'):
        return f"https://{os.environ['KOYEB_PUBLIC_DOMAIN']}".rstrip('/')
    if os.environ.get('REPL_SLUG') and os.environ.get('REPL_OWNER'):
        return f"https://{os.environ['REPL_SLUG']}-{os.environ['REPL_OWNER']}.replit.app"
    if os.environ.get('FLY_APP_NAME'):
        return f"https://{os.environ['FLY_APP_NAME']}.fly.dev"
    return os.environ.get('HOST_URL', '').rstrip('/') or None

HOST_URL = detect_host_url()

# ==================== FLASK ====================
from flask import Flask, send_file, send_from_directory, jsonify, abort
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return ("<html><head><title>HostingBot</title></head>"
            "<body style='font-family:Arial;text-align:center;"
            "background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);"
            "color:white;padding:50px;'>"
            "<h1>HostingBot</h1><p>by <b>@NottBlac</b> — Running</p></body></html>")

@app.route('/file/<uid>/<path:filename>')
def serve_file(uid, filename):
    user_dir = os.path.join(UPLOAD_DIR, str(uid))
    full_path = os.path.join(user_dir, filename)
    logger.info(f"Serving file: uid={uid}, filename={filename}, full_path={full_path}")
    if not os.path.exists(full_path):
        logger.warning(f"File not found: {full_path}")
        return "File not found", 404
    return send_from_directory(user_dir, filename)

@app.route('/s/<slug>')
@app.route('/s/<slug>/<path:subpath>')
def serve_site(slug, subpath='index.html'):
    site_dir = os.path.join(SITES_DIR, slug)
    if not os.path.isdir(site_dir):
        return "Site not found", 404
    target = os.path.join(site_dir, subpath if subpath else 'index.html')
    if not os.path.exists(target) and subpath in ('', 'index.html'):
        for f in os.listdir(site_dir):
            if f.endswith('.html'):
                target = os.path.join(site_dir, f)
                break
    target = os.path.realpath(target)
    if not target.startswith(os.path.realpath(site_dir)):
        abort(403)
    if os.path.exists(target) and os.path.isfile(target):
        return send_file(target)
    return "Not found", 404

@app.route('/health')
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat(),
                    "users": len(active_users),
                    "files": sum(len(f) for f in user_files.values()),
                    "platform": HOST_URL or "local"})

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def keep_alive():
    t = Thread(target=run_flask, daemon=True)
    t.start()

def get_file_url(uid, name):
    if not HOST_URL:
        return None
    return f"{HOST_URL}/file/{uid}/{name}"

def get_site_url(slug):
    if not HOST_URL: return None
    return f"{HOST_URL}/s/{slug}/"

# ==================== BOT ====================
bot = telebot.TeleBot(TOKEN)

# ==================== DATA ====================
scripts         = {}   # key -> process info dict
subscriptions   = {}   # uid -> {expiry}
user_files      = {}   # uid -> [(name, ftype)]
active_users    = set()
admins          = {ADMIN_ID, OWNER_ID}
pending         = {}   # hash -> {uid, name, path}
bot_locked      = False
shell_sessions  = {}   # uid -> True
exec_locks      = {}
exec_locks_mutex = threading.Lock()
broadcast_pending = {}
user_envs       = {}   # uid -> {filename -> {KEY: VALUE}}
site_slugs      = {}   # uid -> {filename -> slug}
waiting_slug    = {}   # uid -> {name, uid}
waiting_env     = {}   # uid -> {step, name, key, chat_id, msg_id}
banned_users    = set()

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
        c.execute('CREATE TABLE IF NOT EXISTS banned (uid INTEGER PRIMARY KEY)')
        c.execute('INSERT OR IGNORE INTO admins VALUES (?)', (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins VALUES (?)', (ADMIN_ID,))
        conn.commit(); conn.close()
        logger.info("DB initialized")
    except Exception as e:
        logger.error(f"DB init error: {e}")

def clear_old_data():
    logger.info("Clearing old data...")
    for info in list(scripts.values()):
        if info.get('process') and info['process'].poll() is None:
            try: kill_process_tree(info['process'].pid)
            except: pass
    scripts.clear()
    for d in [UPLOAD_DIR, EXTRACT_DIR, PENDING_DIR, SITES_DIR, TEMP_DIR]:
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
    user_files.clear(); pending.clear(); site_slugs.clear()
    logger.info("Data cleared")

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
        c.execute('SELECT uid FROM banned')
        banned_users.update(uid for uid, in c.fetchall())
        conn.close()
        logger.info(f"Data loaded: {len(active_users)} users")
    except Exception as e:
        logger.error(f"Data load error: {e}")

# ==================== HELPERS ====================
def get_user_folder(uid):
    folder = os.path.join(UPLOAD_DIR, str(uid))
    os.makedirs(folder, exist_ok=True)
    return folder

def get_user_home(uid):
    home = os.path.join(get_user_folder(uid), 'home')
    os.makedirs(home, exist_ok=True)
    return home

def get_user_tier(uid):
    if uid == OWNER_ID: return 'owner'
    if uid in admins: return 'admin'
    if uid in subscriptions and subscriptions[uid]['expiry'] > datetime.now(): return 'premium'
    return 'free'

def get_user_limit(uid):
    tier = get_user_tier(uid)
    if tier == 'owner': return OWNER_LIMIT
    if tier == 'admin': return ADMIN_LIMIT
    if tier == 'premium': return SUB_LIMIT
    return FREE_LIMIT

def get_user_ram_limit(uid):
    tier = get_user_tier(uid)
    return TIER_RAM[tier]

def get_user_count(uid):
    return len(user_files.get(uid, []))

def fmt_size(sz):
    if sz < 1024: return f"{sz}B"
    if sz < 1024*1024: return f"{sz/1024:.1f}KB"
    return f"{sz/(1024*1024):.1f}MB"

def kill_process_tree(pid):
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            try: child.terminate()
            except: pass
        parent.terminate()
        gone, alive = psutil.wait_procs(children + [parent], timeout=3)
        for p in alive:
            try: p.kill()
            except: pass
        return True
    except psutil.NoSuchProcess:
        return True
    except Exception as e:
        logger.error(f"kill_process_tree error: {e}")
        return False

def stop_script(uid, name):
    key = f"{uid}_{name}"
    if key in scripts:
        scripts[key]['stopped_intentionally'] = True
        scripts[key]['running'] = False
        if scripts[key].get('process'):
            try: kill_process_tree(scripts[key]['process'].pid)
            except: pass
    time.sleep(0.5)
    return True

def is_running(uid, name):
    key = f"{uid}_{name}"
    if key not in scripts or not scripts[key].get('process'): return False
    if scripts[key].get('stopped_intentionally'): return False
    try:
        p = psutil.Process(scripts[key]['process'].pid)
        if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
            scripts[key]['running'] = True
            return True
    except psutil.NoSuchProcess: pass
    scripts[key]['running'] = False
    return False

def get_process_stats(pid):
    try:
        p = psutil.Process(pid)
        return f"{p.cpu_percent(interval=0.1):.1f}%", f"{p.memory_info().rss/(1024*1024):.1f}MB"
    except: return "?", "?"

def safe_send(chat_id, text, parse=None, markup=None):
    try: return bot.send_message(chat_id, text, parse_mode=parse, reply_markup=markup)
    except Exception as e:
        if "can't parse" in str(e): return bot.send_message(chat_id, text, reply_markup=markup)
        if "Too Many Requests" in str(e): time.sleep(1); return safe_send(chat_id, text, parse, markup)
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
        now = datetime.now().isoformat()
        conn.execute('INSERT OR IGNORE INTO users VALUES (?,?,?,?,?)',
                     (uid, name.strip(), username, now, now))
        conn.execute('UPDATE users SET name=?,username=?,last_seen=? WHERE uid=?',
                     (name.strip(), username, now, uid))
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

def setup_user_home(uid):
    home = get_user_home(uid)
    bashrc = os.path.join(home, '.bashrc')
    if not os.path.exists(bashrc):
        with open(bashrc, 'w') as f:
            f.write(r'''# User private environment
export HOME="{home}"
export PATH="$HOME/.pyenv/bin:$HOME/.nvm/versions/node/*/bin:$HOME/bin:$PATH"
export PYENV_ROOT="$HOME/.pyenv"
export NVM_DIR="$HOME/.nvm"
export LC_ALL=C.UTF-8

# Initialize pyenv if present
if [ -d "$PYENV_ROOT" ]; then
    eval "$(pyenv init -)"
fi

# Initialize nvm if present
if [ -d "$NVM_DIR" ]; then
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
    [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"
fi

alias python=python3
alias pip=pip3
'''.replace('{home}', home))

    # Install pyenv if missing
    pyenv_dir = os.path.join(home, '.pyenv')
    if not os.path.exists(pyenv_dir):
        subprocess.run(['git', 'clone', '--depth', '1', 'https://github.com/pyenv/pyenv.git', pyenv_dir],
                       capture_output=True, timeout=60)

    # Install nvm if missing
    nvm_dir = os.path.join(home, '.nvm')
    if not os.path.exists(nvm_dir):
        subprocess.run(['git', 'clone', '--depth', '1', 'https://github.com/nvm-sh/nvm.git', nvm_dir],
                       capture_output=True, timeout=60)

    return home

def get_user_env(uid, name=None):
    home = setup_user_home(uid)
    env = {
        'HOME': home,
        'PATH': f"{home}/.pyenv/bin:{home}/.nvm/versions/node/*/bin:{home}/bin:" + os.environ.get('PATH', '/usr/bin:/bin:/usr/local/bin'),
        'PYENV_ROOT': f"{home}/.pyenv",
        'NVM_DIR': f"{home}/.nvm",
        'USER': str(uid),
        'LANG': 'en_US.UTF-8',
        'LC_ALL': 'C.UTF-8',
        'TERM': 'xterm-256color',
    }
    if name and uid in user_envs and name in user_envs[uid]:
        env.update(user_envs[uid][name])
    return env

def resource_limits(uid):
    tier = get_user_tier(uid)
    
    # Owner gets no limits
    if tier == 'owner':
        return lambda: None
    
    ram_limit = TIER_RAM[tier]
    cpu_seconds = 3600  # 1 hour
    
    if tier == 'free':
        nproc = 128
        nofile = 4096
    elif tier == 'premium':
        nproc = 256
        nofile = 8192
    else:  # admin
        nproc = 512
        nofile = 16384
    
    def set_limits():
        if ram_limit is not None:
            resource.setrlimit(resource.RLIMIT_AS, (ram_limit, ram_limit))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_FSIZE, (100*1024*1024, 100*1024*1024))
        resource.setrlimit(resource.RLIMIT_NPROC, (nproc, nproc))
        resource.setrlimit(resource.RLIMIT_NOFILE, (nofile, nofile))
    return set_limits

def save_env_var(uid, filename, key, value):
    user_envs.setdefault(uid, {}).setdefault(filename, {})[key] = value
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT OR REPLACE INTO user_envs VALUES (?,?,?,?)', (uid, filename, key, value))
        conn.commit(); conn.close()
    except: pass

def delete_env_var(uid, filename, key):
    user_envs.get(uid, {}).get(filename, {}).pop(key, None)
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

def extract_error_snippet(stderr, stdout=""):
    text = (stderr or stdout or "").strip()
    if not text: return ""
    tb = re.search(r'(Traceback \(most recent call last\).*)', text, re.DOTALL)
    snippet = tb.group(1).strip() if tb else "\n".join(text.splitlines()[-30:]).strip()
    return ("..." + snippet[-1800:]) if len(snippet) > 1800 else snippet

# ==================== SECURITY ====================
_DANGEROUS_STRINGS = [
    'rm -rf', 'fdisk', 'mkfs', 'dd if=', 'shutdown', 'reboot', 'halt',
    'poweroff', 'init 0', 'init 6', 'systemctl',
    'shutil.rmtree("/"', 'setuid', 'setgid', 'chmod 777', 'chown root',
    'sudo ', '/etc/passwd', '/etc/shadow', '/etc/hosts', '/proc/self',
    '.ssh/', 'id_rsa',
]

_DANGEROUS_REGEX = [
    (re.compile(r'\bos\.listdir\s*\('), 'os.listdir'),
    (re.compile(r'\bos\.walk\s*\('), 'os.walk'),
    (re.compile(r'\bos\.scandir\s*\('), 'os.scandir'),
    (re.compile(r'\bos\.getcwd\s*\('), 'os.getcwd'),
    (re.compile(r'\bos\.chdir\s*\('), 'os.chdir'),
    (re.compile(r'\bos\.environ\b'), 'os.environ'),
    (re.compile(r'\bos\.getenv\s*\('), 'os.getenv'),
    (re.compile(r'\bos\.path\.abspath\s*\('), 'os.path.abspath'),
    (re.compile(r'\bos\.system\s*\('), 'os.system'),
    (re.compile(r'\bos\.popen\s*\('), 'os.popen'),
    (re.compile(r'\bos\.remove\s*\('), 'os.remove'),
    (re.compile(r'\bopen\s*\('), 'open()'),
    (re.compile(r'\bsubprocess\s*\.'), 'subprocess'),
    (re.compile(r'\bimport\s+subprocess\b'), 'import subprocess'),
    (re.compile(r'\bfrom\s+subprocess\b'), 'from subprocess'),
    (re.compile(r'\bimport\s+socket\b'), 'import socket'),
    (re.compile(r'\bfrom\s+socket\b'), 'from socket'),
    (re.compile(r'\brequests\s*\.'), 'requests'),
    (re.compile(r'\bhttpx\s*\.'), 'httpx'),
    (re.compile(r'\baiohttp\s*\.'), 'aiohttp'),
    (re.compile(r'\burllib\s*\.'), 'urllib'),
    (re.compile(r'\bhttp\.client\b'), 'http.client'),
    (re.compile(r'\bsend_document\s*\('), 'send_document'),
    (re.compile(r'\bsend_photo\s*\('), 'send_photo'),
    (re.compile(r'\bsend_video\s*\('), 'send_video'),
    (re.compile(r'\bsend_audio\s*\('), 'send_audio'),
    (re.compile(r'\bsend_file\s*\('), 'send_file'),
    (re.compile(r'\bsend_media_group\s*\('), 'send_media_group'),
    (re.compile(r'\bzipfile\s*\.'), 'zipfile'),
    (re.compile(r'\bimport\s+zipfile\b'), 'import zipfile'),
    (re.compile(r'\btarfile\s*\.'), 'tarfile'),
    (re.compile(r'\bshutil\.copy\b'), 'shutil.copy'),
    (re.compile(r'\bshutil\.move\b'), 'shutil.move'),
    (re.compile(r'\bshutil\.make_archive\b'), 'shutil.make_archive'),
    (re.compile(r'\beval\s*\('), 'eval()'),
    (re.compile(r'\bexec\s*\('), 'exec()'),
    (re.compile(r'\b__import__\s*\('), '__import__'),
    (re.compile(r'\bimportlib\b'), 'importlib'),
    (re.compile(r'\bcompile\s*\('), 'compile()'),
]

def _scan_content(content):
    cl = content.lower()
    for p in _DANGEROUS_STRINGS:
        if p.lower() in cl:
            return False, f"Blocked: `{p}`"
    for pattern, label in _DANGEROUS_REGEX:
        if pattern.search(content):
            return False, f"Blocked: `{label}`"
    return True, "Safe"

def check_malicious(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        ok, reason = _scan_content(content)
        if not ok: return False, reason
        if os.path.getsize(file_path) > 20*1024*1024: return False, "File >20MB"
        return True, "Safe"
    except: return True, "Safe"

def scan_zip_contents(zip_path):
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for name in zf.namelist():
                if os.path.splitext(name)[1].lower() in (
                    '.py','.pyw','.js','.mjs','.cjs','.ts','.tsx',
                    '.sh','.bash','.rb','.php','.lua','.pl','.bat','.cmd','.ps1'
                ):
                    try:
                        content = zf.open(name).read(512*1024).decode('utf-8', errors='ignore')
                        ok, reason = _scan_content(content)
                        if not ok:
                            return False, f"In `{os.path.basename(name)}`: {reason}"
                    except: pass
        return True, "Safe"
    except zipfile.BadZipFile: return False, "Invalid ZIP file"
    except: return True, "Safe"

def is_website_zip(zip_path):
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            return 'index.html' in [os.path.basename(n).lower() for n in zf.namelist()]
    except: return False

# ==================== DEPENDENCY INSTALLER ====================
def install_deps(file_path, ext, folder, uid, script_name, installed=None):
    if installed is None: installed = set()
    new = set(); msgs = []
    try:
        if ext in ('.py', '.pyw'):
            home = get_user_home(uid)
            python_bin = os.path.join(home, '.pyenv', 'shims', 'python')
            if not os.path.exists(python_bin):
                python_bin = sys.executable
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
                'sqlalchemy':'sqlalchemy','pymongo':'pymongo','redis':'redis','pydantic':'pydantic',
                'tgcalls':'py-tgcalls','py_tgcalls':'py-tgcalls',
            }
            for imp in re.findall(r'(?:from\s+(\w+)|import\s+(\w+))', content):
                mod = imp[0] or imp[1]
                pkg = pkg_map.get(mod)
                if pkg and pkg not in installed and pkg not in new:
                    try:
                        r = subprocess.run([python_bin, '-m', 'pip', 'install', '--quiet', pkg],
                                           capture_output=True, text=True, timeout=60, env=get_user_env(uid))
                        if r.returncode == 0: msgs.append(f"✅ {pkg}"); new.add(pkg)
                        else: msgs.append(f"❌ {pkg}")
                    except: msgs.append(f"⚠️ {pkg}")
            req_file = os.path.join(folder, 'requirements.txt')
            if os.path.exists(req_file):
                r = subprocess.run([python_bin, '-m', 'pip', 'install', '--quiet', '-r', req_file],
                                   capture_output=True, text=True, timeout=120, env=get_user_env(uid))
                if r.returncode == 0: msgs.append("✅ requirements.txt installed")
                else: msgs.append("⚠️ requirements.txt failed")
        elif ext in ('.js', '.mjs', '.cjs'):
            pjson = os.path.join(folder, 'package.json')
            if not os.path.exists(pjson):
                with open(pjson,'w') as f: json.dump({"name":"script","version":"1.0.0"},f)
            with open(file_path,'r',encoding='utf-8') as f: content = f.read()
            node_map = {'express':'express','axios':'axios','lodash':'lodash',
                        'moment':'moment','dotenv':'dotenv','ws':'ws',
                        'mongoose':'mongoose','mysql':'mysql','pg':'pg'}
            for mod in re.findall(r"require\(['\"]([^'\"]+)['\"]\)", content):
                base = mod.split('/')[0]
                pkg = node_map.get(base)
                if pkg and pkg not in installed and pkg not in new:
                    try:
                        r = subprocess.run(['npm','install','--silent',pkg],
                                           cwd=folder, capture_output=True, text=True, timeout=30, env=get_user_env(uid))
                        if r.returncode == 0: msgs.append(f"✅ {pkg}"); new.add(pkg)
                        else: msgs.append(f"❌ {pkg}")
                    except: msgs.append(f"⚠️ {pkg}")
    except: pass
    return msgs, new

# ==================== FILE TYPE SETS ====================
EXECUTABLE_EXTS = {
    '.py','.pyw','.js','.mjs','.cjs','.ts','.tsx',
    '.sh','.bash','.zsh','.fish',
    '.java','.c','.cpp','.cc','.cxx',
    '.go','.rs','.rb','.php','.lua',
    '.pl','.pm','.r','.R','.swift','.kt','.scala',
    '.ex','.exs','.hs','.bat','.cmd','.ps1',
}

STATIC_EXTS = {
    '.html','.htm','.css','.txt','.md','.rst','.rtf',
    '.json','.jsonl','.xml','.yaml','.yml','.toml','.ini','.cfg','.conf',
    '.csv','.tsv','.sql',
    '.jpg','.jpeg','.png','.gif','.webp','.svg','.ico','.bmp','.tiff',
    '.mp4','.webm','.mkv','.avi','.mov','.mp3','.wav','.ogg','.flac','.aac',
    '.pdf','.tar','.gz','.bz2',
    '.ttf','.woff','.woff2',
}

LANG_MAP = {
    '.py':('Python','🐍'),'.pyw':('Python','🐍'),
    '.js':('JavaScript','🟨'),'.mjs':('JavaScript','🟨'),'.cjs':('JavaScript','🟨'),
    '.ts':('TypeScript','🔷'),'.tsx':('TypeScript','🔷'),
    '.java':('Java','☕'),
    '.cpp':('C++','🔧'),'.cc':('C++','🔧'),'.cxx':('C++','🔧'),'.c':('C','🔧'),
    '.sh':('Shell','🖥️'),'.bash':('Shell','🖥️'),'.zsh':('Shell','🖥️'),'.fish':('Shell','🖥️'),
    '.rb':('Ruby','💎'),'.go':('Go','🐹'),'.rs':('Rust','🦀'),
    '.php':('PHP','🐘'),'.lua':('Lua','🌙'),
    '.pl':('Perl','🐪'),'.pm':('Perl','🐪'),
    '.r':('R','📊'),'.R':('R','📊'),
    '.swift':('Swift','🍎'),'.kt':('Kotlin','🟣'),'.scala':('Scala','🔴'),
    '.ex':('Elixir','💜'),'.exs':('Elixir','💜'),'.hs':('Haskell','🔵'),
    '.bat':('Batch','🖥️'),'.cmd':('Batch','🖥️'),'.ps1':('PowerShell','🔵'),
}

# ==================== ZIP WEBSITE HANDLER ====================
def handle_zip_website(zip_path, uid, zip_name, msg=None):
    existing = site_slugs.get(uid, {}).get(zip_name)
    if existing:
        slug = existing
    else:
        base = os.path.splitext(zip_name)[0]
        slug = re.sub(r'[^a-z0-9\-]', '-', base.lower()).strip('-') or \
               hashlib.md5(f"{uid}_{zip_name}".encode()).hexdigest()[:8]
        orig = slug; counter = 1
        while slug_exists(slug, uid, zip_name):
            slug = f"{orig}-{counter}"; counter += 1
        save_slug(uid, zip_name, slug)

    site_dir = os.path.join(SITES_DIR, slug)
    if os.path.exists(site_dir): shutil.rmtree(site_dir)
    os.makedirs(site_dir)
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(site_dir)
    entries = os.listdir(site_dir)
    if len(entries) == 1 and os.path.isdir(os.path.join(site_dir, entries[0])):
        sub = os.path.join(site_dir, entries[0])
        for item in os.listdir(sub):
            shutil.move(os.path.join(sub, item), site_dir)
        os.rmdir(sub)

    url = get_site_url(slug)
    if msg:
        mk = types.InlineKeyboardMarkup()
        if url: mk.add(types.InlineKeyboardButton("🌐 Open Website", url=url))
        mk.add(types.InlineKeyboardButton("🔗 Set Custom Slug", callback_data=f"setslug_{uid}_{zip_name}"))
        safe_edit(msg.chat.id, msg.message_id,
                 f"🌐 *Website Hosted*\n`{zip_name}`\n\nSlug: `{slug}`\nURL: `{url or 'Set HOST_URL env var'}`",
                 'Markdown', mk)
    return True, url or slug

# ==================== ZIP CODE HANDLER ====================
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

        inner_name = os.path.basename(main_file)
        inner_ext  = os.path.splitext(main_file)[1].lower()
        key        = f"{uid}_{zip_name}" if zip_name else f"{uid}_{inner_name}"
        return _do_execute(uid, main_file, msg, extract_to, inner_name, inner_ext, key, zip_name)

    except zipfile.BadZipFile: return False, "Invalid ZIP file"
    except Exception as e: return False, f"ZIP error: {e}"

# ==================== CRASH MONITOR ====================
def monitor_script(uid, key, name, process, log_path, msg_chat_id=None, msg_id=None):
    try:
        process.wait()
        rc = process.returncode
        if key not in scripts: return
        if scripts[key].get('stopped_intentionally'): return

        scripts[key]['running'] = False
        scripts[key]['code'] = rc

        if msg_chat_id and msg_id:
            try:
                mk = build_control_markup(uid, name, 'executable')
                if rc in (0, None):
                    safe_edit(msg_chat_id, msg_id, f"✅ *Finished* — `{name}`\nExit: `{rc}`", 'Markdown', mk)
                else:
                    safe_edit(msg_chat_id, msg_id, f"❌ *Crashed* — `{name}`\nExit: `{rc}`", 'Markdown', mk)
            except: pass

        if rc is not None and rc not in (0, -1, -9):
            snippet = _read_crash_snippet(key, log_path)
            text = (f"⚠️ <b>Script Crashed</b>\n"
                    f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
                    f"📄 <code>{name}</code>\n"
                    f"❌ Exit code: <code>{rc}</code>")
            if snippet:
                if len(snippet) > 1500: snippet = "..." + snippet[-1500:]
                text += f"\n\n<pre>{snippet}</pre>"
            try: safe_send(uid, text, parse='HTML')
            except: pass
    except: pass

def _read_crash_snippet(key, log_path):
    try:
        info = scripts.get(key, {})
        stderr_path = info.get('stderr_log')
        read_path = (stderr_path if stderr_path and os.path.exists(stderr_path)
                     and os.path.getsize(stderr_path) > 0 else log_path)
        if not read_path or not os.path.exists(read_path): return ""
        with open(read_path, 'r', errors='ignore') as f: content = f.read()
        filtered = "\n".join([
            l for l in content.splitlines()
            if not re.match(r'^(INFO|DEBUG|WARNING):(httpx|urllib3|requests|telebot|apscheduler)', l)
            and 'HTTP Request:' not in l and 'HTTP/1.' not in l and 'getUpdates' not in l
        ])
        tb = re.search(r'(Traceback \(most recent call last\).*)', filtered, re.DOTALL)
        if tb: return tb.group(1).strip()
        lines = filtered.splitlines()
        return "\n".join(lines[-30:] if len(lines) > 30 else lines).strip()
    except: return ""

# ==================== MID-RUN TRACEBACK WATCHER ====================
def tail_stderr_for_tracebacks(uid, key, name, stderr_path, process):
    NOISE = re.compile(
        r'^(INFO|DEBUG|WARNING):(httpx|urllib3|requests|telebot|apscheduler)|'
        r'HTTP Request:|HTTP/1\.|getUpdates'
    )
    sent_hashes = {}
    COOLDOWN    = 60

    def _hash(tb_text):
        lines = [l for l in tb_text.splitlines() if l.strip()]
        return hashlib.md5('\n'.join(lines[:4]).encode()).hexdigest()

    for _ in range(30):
        if os.path.exists(stderr_path): break
        time.sleep(0.2)

    buffer = ""
    try:
        with open(stderr_path, 'r', errors='ignore') as f:
            while True:
                if process.poll() is not None: break
                if key not in scripts: break
                if scripts[key].get('stopped_intentionally'): break

                chunk = f.read(8192)
                if chunk:
                    buffer += chunk
                    while True:
                        start = buffer.find('Traceback (most recent call last)')
                        if start == -1: break
                        rest  = buffer[start:]
                        lines = rest.split('\n')
                        end_idx = None
                        for i, line in enumerate(lines[1:], 1):
                            if line and not line.startswith((' ', '\t')):
                                end_idx = i + 1
                                break
                        if end_idx is None: break

                        tb_raw  = '\n'.join(lines[:end_idx]).strip()
                        tb_clean = '\n'.join(l for l in tb_raw.splitlines() if not NOISE.search(l)).strip()

                        if tb_clean:
                            h = _hash(tb_clean)
                            now = time.time()
                            if now - sent_hashes.get(h, 0) >= COOLDOWN:
                                sent_hashes[h] = now
                                snippet = tb_clean if len(tb_clean) <= 1500 else "..." + tb_clean[-1500:]
                                text = (f"⚠️ <b>Runtime Error in {name}</b>\n"
                                        f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
                                        f"<pre>{snippet}</pre>")
                                try: safe_send(uid, text, parse='HTML')
                                except: pass

                        buffer = buffer[start + len('\n'.join(lines[:end_idx])):]
                else:
                    time.sleep(0.5)
    except: pass

# ==================== SCRIPT EXECUTOR ====================
def execute_script(uid, file_path, msg=None, work_dir=None, zip_name=None):
    name = os.path.basename(file_path)
    ext  = os.path.splitext(file_path)[1].lower()
    key  = f"{uid}_{zip_name}" if zip_name else f"{uid}_{name}"
    with exec_locks_mutex:
        if exec_locks.get(key):
            if msg:
                try: safe_edit(msg.chat.id, msg.message_id,
                               f"⚠️ `{zip_name or name}` is already being started", 'Markdown')
                except: pass
            return False, "Already starting"
        exec_locks[key] = True
    try:
        return _do_execute(uid, file_path, msg, work_dir, name, ext, key, zip_name)
    finally:
        with exec_locks_mutex:
            exec_locks.pop(key, None)

def _do_execute(uid, file_path, msg, work_dir, name, ext, key, zip_name=None):
    display_name = zip_name if zip_name else name

    if ext in STATIC_EXTS:
        url = get_file_url(uid, name)
        if msg:
            mk = types.InlineKeyboardMarkup()
            if url: mk.add(types.InlineKeyboardButton("🔗 View File", url=url))
            safe_edit(msg.chat.id, msg.message_id, f"✅ *Hosted*\n`{name}`", 'Markdown', mk if url else None)
        return True, "Hosted"

    if ext == '.zip':
        return handle_zip(file_path, uid,
                          os.path.join(EXTRACT_DIR, f"{uid}_{int(time.time())}"),
                          msg, name)

    if ext not in LANG_MAP:
        if msg: safe_edit(msg.chat.id, msg.message_id, f"❌ Unsupported type: `{ext}`", 'Markdown')
        return False, "Unsupported"

    lang, icon = LANG_MAP[ext]
    folder = get_user_folder(uid)

    try:
        if msg: safe_edit(msg.chat.id, msg.message_id,
                          f"{icon} *{lang}* — `{display_name}`\n⚙️ Starting...", 'Markdown')

        installed = set()
        deps, new = install_deps(file_path, ext, folder, uid, display_name)
        installed.update(new)
        if deps and msg:
            dep_text = "\n".join(deps[:4]) + (f"\n+{len(deps)-4} more" if len(deps) > 4 else "")
            safe_edit(msg.chat.id, msg.message_id,
                      f"{icon} *{lang}* — `{display_name}`\n📦 Deps:\n{dep_text}", 'Markdown')

        env = get_user_env(uid, name)
        if ext in ('.py', '.pyw'):
            home = get_user_home(uid)
            python_bin = os.path.join(home, '.pyenv', 'shims', 'python')
            if not os.path.exists(python_bin):
                python_bin = sys.executable
            cmd = [python_bin, file_path]
        elif ext in ('.js', '.mjs', '.cjs'):
            cmd = ['node', file_path]
        elif ext == '.java':
            classname = os.path.splitext(name)[0]
            compile_dir = os.path.join(TEMP_DIR, f"{uid}_{display_name}")
            os.makedirs(compile_dir, exist_ok=True)
            r = subprocess.run(['javac', '-d', compile_dir, file_path], capture_output=True, text=True, timeout=60, env=env)
            if r.returncode != 0:
                if msg: safe_edit(msg.chat.id, msg.message_id,
                                  f"❌ *Java compile failed*\n```\n{r.stderr[:400]}\n```", 'Markdown')
                return False, "Java compile failed"
            cmd = ['java', '-cp', compile_dir, classname]
        elif ext in ('.cpp', '.cc', '.cxx', '.c'):
            out  = os.path.join(TEMP_DIR, f"{uid}_{display_name}.out")
            comp = 'g++' if ext in ('.cpp', '.cc', '.cxx') else 'gcc'
            r = subprocess.run([comp, file_path, '-o', out], capture_output=True, text=True, timeout=60, env=env)
            if r.returncode != 0:
                if msg: safe_edit(msg.chat.id, msg.message_id,
                                  f"❌ *Compile failed*\n```\n{r.stderr[:400]}\n```", 'Markdown')
                return False, "Compile failed"
            cmd = [out]
        elif ext == '.go':
            cmd = ['go', 'run', file_path]
        elif ext == '.rs':
            out = os.path.join(TEMP_DIR, f"{uid}_{display_name}.out")
            r = subprocess.run(['rustc', file_path, '-o', out], capture_output=True, text=True, timeout=60, env=env)
            if r.returncode != 0:
                if msg: safe_edit(msg.chat.id, msg.message_id,
                                  f"❌ *Rust compile failed*\n```\n{r.stderr[:400]}\n```", 'Markdown')
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
            cmd = [ext.lstrip('.') if ext != '.sh' else 'bash', file_path]
        elif ext in ('.ts', '.tsx'):
            js = file_path.rsplit('.', 1)[0] + '.js'
            r = subprocess.run(['tsc', file_path, '--outDir', os.path.dirname(file_path)],
                               capture_output=True, text=True, timeout=60, env=env)
            if r.returncode != 0:
                if msg: safe_edit(msg.chat.id, msg.message_id,
                                  f"❌ *TS compile failed*\n```\n{r.stderr[:400]}\n```", 'Markdown')
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
            jar = os.path.join(TEMP_DIR, f"{uid}_{display_name}.jar")
            r = subprocess.run(['kotlinc', file_path, '-include-runtime', '-d', jar],
                               capture_output=True, text=True, timeout=120, env=env)
            if r.returncode != 0:
                if msg: safe_edit(msg.chat.id, msg.message_id,
                                  f"❌ *Kotlin compile failed*\n```\n{r.stderr[:400]}\n```", 'Markdown')
                return False, "Kotlin compile failed"
            cmd = ['java', '-jar', jar]
        elif ext == '.scala':
            compile_dir = os.path.join(TEMP_DIR, f"{uid}_{display_name}")
            os.makedirs(compile_dir, exist_ok=True)
            r = subprocess.run(['scalac', '-d', compile_dir, file_path],
                               capture_output=True, text=True, timeout=120, env=env)
            if r.returncode != 0:
                if msg: safe_edit(msg.chat.id, msg.message_id,
                                  f"❌ *Scala compile failed*\n```\n{r.stderr[:400]}\n```", 'Markdown')
                return False, "Scala compile failed"
            cmd = ['scala', '-cp', compile_dir, os.path.splitext(name)[0]]
        elif ext in ('.ex', '.exs'):
            cmd = ['elixir', file_path]
        elif ext == '.hs':
            out = os.path.join(TEMP_DIR, f"{uid}_{display_name}.out")
            r = subprocess.run(['ghc', file_path, '-o', out],
                               capture_output=True, text=True, timeout=120, env=env)
            if r.returncode != 0:
                if msg: safe_edit(msg.chat.id, msg.message_id,
                                  f"❌ *Haskell compile failed*\n```\n{r.stderr[:400]}\n```", 'Markdown')
                return False, "Haskell compile failed"
            cmd = [out]
        else:
            cmd = [file_path]

        safe_name   = re.sub(r'[^\w]', '_', display_name)
        log_path    = os.path.join(LOGS_DIR, f"{uid}_{safe_name}.log")
        stderr_path = os.path.join(LOGS_DIR, f"{uid}_{safe_name}.err")
        cwd = work_dir or os.path.dirname(file_path)

        for attempt in range(1, 11):
            if attempt > 1 and msg:
                safe_edit(msg.chat.id, msg.message_id,
                          f"{icon} *{lang}* — `{display_name}`\n🔄 Retry {attempt}...", 'Markdown')
            try:
                res = subprocess.run(cmd, capture_output=True, text=True,
                                     timeout=30, cwd=cwd, env=env,
                                     preexec_fn=resource_limits(uid))

                if res.returncode != 0 and "ModuleNotFoundError" in res.stderr:
                    match = re.search(r"No module named '(\w+)'", res.stderr)
                    if match:
                        mod = match.group(1)
                        aliases = {
                            'telethon':'telethon','cryptg':'cryptg',
                            'telebot':'pyTelegramBotAPI','telegram':'python-telegram-bot',
                            'cv2':'opencv-python','PIL':'Pillow','bs4':'beautifulsoup4',
                            'yaml':'pyyaml','dotenv':'python-dotenv','flask':'flask',
                            'django':'django','requests':'requests','numpy':'numpy',
                            'pandas':'pandas','aiohttp':'aiohttp','fastapi':'fastapi',
                            'tgcalls':'py-tgcalls','py_tgcalls':'py-tgcalls',
                        }
                        pkg = aliases.get(mod, mod)
                        if pkg not in installed:
                            if msg: safe_edit(msg.chat.id, msg.message_id,
                                              f"{icon} *{lang}* — `{display_name}`\n📦 Installing `{pkg}`...",
                                              'Markdown')
                            if ext in ('.py', '.pyw'):
                                home = get_user_home(uid)
                                python_bin = os.path.join(home, '.pyenv', 'shims', 'python')
                                if not os.path.exists(python_bin):
                                    python_bin = sys.executable
                                subprocess.run([python_bin, '-m', 'pip', 'install', '--quiet', pkg],
                                               capture_output=True, text=True, timeout=60, env=env)
                            else:
                                subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', pkg],
                                               capture_output=True, text=True, timeout=60, env=env)
                            installed.add(pkg)
                            continue

                with open(log_path, 'w') as lf:
                    if res.stdout: lf.write(res.stdout)
                    if res.stderr: lf.write(res.stderr)
                    lf.write(f"\nExit: {res.returncode}")
                with open(stderr_path, 'w') as ef:
                    if res.stderr: ef.write(res.stderr)

                scripts[key] = {
                    'process': None, 'key': key, 'uid': uid, 'name': display_name,
                    'start': datetime.now(), 'log': log_path, 'stderr_log': stderr_path,
                    'lang': lang, 'icon': icon, 'running': False, 'code': res.returncode
                }

                if msg:
                    mk = build_control_markup(uid, display_name, 'executable')
                    if res.returncode == 0:
                        safe_edit(msg.chat.id, msg.message_id,
                                  f"✅ *{lang}* — `{display_name}`\nExit: `0`", 'Markdown', mk)
                    else:
                        snippet = extract_error_snippet(res.stderr, res.stdout)
                        err_text = f"❌ *{lang}* — `{display_name}`\nExit: `{res.returncode}`"
                        if snippet: err_text += f"\n\n```\n{snippet}\n```"
                        safe_edit(msg.chat.id, msg.message_id, err_text, 'Markdown', mk)

                return True, f"Exit {res.returncode}"

            except subprocess.TimeoutExpired:
                with open(log_path, 'w') as lf, open(stderr_path, 'w') as ef:
                    p = subprocess.Popen(cmd, stdout=lf, stderr=ef, cwd=cwd, env=env,
                                         preexec_fn=resource_limits(uid))

                scripts[key] = {
                    'process': p, 'key': key, 'uid': uid, 'name': display_name,
                    'start': datetime.now(), 'log': log_path, 'stderr_log': stderr_path,
                    'lang': lang, 'icon': icon, 'running': True, 'code': None
                }

                msg_chat_id = msg.chat.id if msg else None
                msg_id_val  = msg.message_id if msg else None

                threading.Thread(
                    target=monitor_script,
                    args=(uid, key, display_name, p, log_path, msg_chat_id, msg_id_val),
                    daemon=True
                ).start()

                threading.Thread(
                    target=tail_stderr_for_tracebacks,
                    args=(uid, key, display_name, stderr_path, p),
                    daemon=True
                ).start()

                if msg:
                    mk = build_control_markup(uid, display_name, 'executable')
                    safe_edit(msg.chat.id, msg.message_id,
                              f"🔄 *{lang}* — `{display_name}`\nPID: `{p.pid}`", 'Markdown', mk)
                return True, f"Background PID {p.pid}"

        return False, "Max retries exceeded"

    except Exception as e:
        logger.error(f"Exec error {key}: {e}", exc_info=True)
        if msg:
            try: safe_edit(msg.chat.id, msg.message_id, f"❌ Error: `{str(e)[:200]}`", 'Markdown')
            except: pass
        return False, str(e)

# ==================== SHELL (REAL PTY) ====================
shell_procs = {}

def _get_or_create_shell(uid):
    """Spawn a real PTY with bash, fully interactive."""
    info = shell_procs.get(uid)
    if info and info['fd'] is not None:
        try:
            os.kill(info['pid'], 0)
            return info
        except OSError:
            # process died, clean up
            shell_procs.pop(uid, None)

    home = setup_user_home(uid)
    bashrc = os.path.join(home, '.bashrc')
    env = get_user_env(uid)

    # Pre‑install Node.js LTS if needed
    nvm_dir = os.path.join(home, '.nvm')
    nvm_script = os.path.join(nvm_dir, 'nvm.sh')
    if os.path.exists(nvm_script):
        node_versions = os.path.join(nvm_dir, 'versions', 'node')
        if not os.path.exists(node_versions) or not os.listdir(node_versions):
            subprocess.run(['bash', '-c', f'source "{nvm_script}" && nvm install --lts'],
                           cwd=home, env=env, capture_output=True, timeout=300)

    # Create PTY
    master_fd, slave_fd = pty.openpty()
    try:
        # Set terminal size
        winsize = struct.pack("HHHH", 80, 24, 0, 0)
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
    except:
        pass

    # Spawn bash with PTY
    pid = os.fork()
    if pid == 0:  # child
        os.setsid()
        os.close(master_fd)
        # Set terminal as controlling tty
        try:
            fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
        except:
            pass
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        os.close(slave_fd)

        # Apply resource limits
        resource_limits(uid)()
        # Change to home directory
        os.chdir(home)
        # Execute bash with rcfile
        os.execvpe('bash', ['bash', '--rcfile', bashrc], env)
        os._exit(1)

    # parent
    os.close(slave_fd)
    info = {
        'pid': pid,
        'fd': master_fd,
        'home': home,
        'lock': threading.Lock(),
        'output_buffer': bytearray(),
        'chat_id': None,
        'status_msg_id': None,
        'last_update': 0,
    }
    shell_procs[uid] = info

    # Start reader thread
    def reader():
        fd = info['fd']
        while True:
            try:
                r, _, _ = select.select([fd], [], [], 1.0)
                if r:
                    data = os.read(fd, 4096)
                    if not data:
                        break
                    with info['lock']:
                        info['output_buffer'].extend(data)
            except:
                break
        # Process died, clean up
        shell_procs.pop(uid, None)
        try:
            os.close(fd)
        except:
            pass
        try:
            os.kill(pid, 9)
        except:
            pass
        # Notify user if we have a status message
        if info.get('chat_id') and info.get('status_msg_id'):
            try:
                mk = types.InlineKeyboardMarkup()
                mk.add(types.InlineKeyboardButton("💻 Reopen Shell", callback_data=f"reopen_shell_{uid}"))
                bot.edit_message_text("💀 *Shell session ended*", info['chat_id'],
                                      info['status_msg_id'], parse_mode='Markdown', reply_markup=mk)
            except:
                pass

    threading.Thread(target=reader, daemon=True).start()
    return info

def _kill_shell(uid):
    info = shell_procs.pop(uid, None)
    if info:
        try:
            os.close(info['fd'])
        except:
            pass
        try:
            os.kill(info['pid'], 9)
        except:
            pass

def _send_pty_output(info, force=False):
    """Send buffered PTY output to Telegram, throttled."""
    now = time.time()
    with info['lock']:
        if not info['output_buffer']:
            return
        if not force and now - info['last_update'] < 0.8:
            return
        data = bytes(info['output_buffer'])
        info['output_buffer'].clear()
        info['last_update'] = now

    if not data:
        return

    text = data.decode('utf-8', errors='replace')
    # Escape for Telegram Markdown (keep it simple)
    if len(text) > 3000:
        text = text[-3000:]
    # Use ``` to preserve formatting
    formatted = f"```\n{text}\n```"

    if info.get('chat_id') and info.get('status_msg_id'):
        try:
            bot.edit_message_text(formatted, info['chat_id'], info['status_msg_id'],
                                  parse_mode='Markdown')
        except Exception as e:
            if "message is not modified" not in str(e):
                logger.warning(f"PTY output edit failed: {e}")

@bot.message_handler(commands=['shell'])
def cmd_shell(message):
    uid = message.from_user.id
    parts = message.text.strip().split(' ', 1)
    if len(parts) > 1 and parts[1].strip():
        # One‑off command: run raw, no PTY overhead
        cmd_text = parts[1].strip()
        home = setup_user_home(uid)
        env = get_user_env(uid)
        # Ensure nvm is available if needed
        nvm_script = os.path.join(home, '.nvm', 'nvm.sh')
        if os.path.exists(nvm_script):
            full_cmd = f'source "{nvm_script}" && {cmd_text}'
        else:
            full_cmd = cmd_text
        try:
            res = subprocess.run(['bash', '-c', full_cmd], capture_output=True, text=True,
                                 timeout=30, cwd=home, env=env, preexec_fn=resource_limits(uid))
            output = res.stdout
            if res.stderr:
                output += "\n" + res.stderr
            if not output.strip():
                output = "(no output)"
            if len(output) > 3500:
                output = output[-3500:]
            safe_reply(message, f"$ `{cmd_text}`\n```\n{output}\n```", 'Markdown')
        except subprocess.TimeoutExpired:
            safe_reply(message, f"$ `{cmd_text}`\n⏱️ *Command timed out*", 'Markdown')
        except Exception as e:
            safe_reply(message, f"❌ `{e}`", 'Markdown')
        return

    # Interactive shell
    shell_sessions[uid] = True
    info = _get_or_create_shell(uid)
    info['chat_id'] = message.chat.id

    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("❌ Exit Shell", callback_data="exit_shell"))

    sent = safe_reply(message, "💻 *Shell Active*\nInitializing PTY...", 'Markdown', mk)
    info['status_msg_id'] = sent.message_id
    # Send initial prompt after a short delay
    time.sleep(0.5)
    _send_pty_output(info, force=True)

@bot.callback_query_handler(func=lambda c: c.data == "exit_shell")
def cb_exit_shell(c):
    uid = c.from_user.id
    shell_sessions.pop(uid, None)
    _kill_shell(uid)
    try:
        safe_edit(c.message.chat.id, c.message.message_id, "💻 *Shell Closed*", 'Markdown')
    except:
        pass
    bot.answer_callback_query(c.id, "Shell closed")

@bot.callback_query_handler(func=lambda c: c.data.startswith('reopen_shell_'))
def cb_reopen_shell(c):
    uid = int(c.data.split('_')[2])
    if c.from_user.id != uid:
        return bot.answer_callback_query(c.id, "Access denied")
    shell_sessions[uid] = True
    info = _get_or_create_shell(uid)
    info['chat_id'] = c.message.chat.id

    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("❌ Exit Shell", callback_data="exit_shell"))

    sent = bot.send_message(c.message.chat.id, "💻 *Shell Active*\nInitializing PTY...",
                            parse_mode='Markdown', reply_markup=mk)
    info['status_msg_id'] = sent.message_id
    time.sleep(0.5)
    _send_pty_output(info, force=True)
    bot.answer_callback_query(c.id)

# ==================== SHELL SESSION INTERCEPT ====================
@bot.message_handler(func=lambda m: m.from_user and shell_sessions.get(m.from_user.id) and m.text)
def shell_session_input(m):
    uid = m.from_user.id
    text = m.text
    if text.lower() in ('exit', 'quit', 'q'):
        shell_sessions.pop(uid, None)
        _kill_shell(uid)
        safe_reply(m, "💻 *Shell closed*", 'Markdown')
        return

    info = shell_procs.get(uid)
    if not info:
        safe_reply(m, "⚠️ Shell session not active. Use /shell to start one.", 'Markdown')
        shell_sessions.pop(uid, None)
        return

    # Send input to PTY
    try:
        os.write(info['fd'], (text + '\n').encode())
    except:
        shell_sessions.pop(uid, None)
        _kill_shell(uid)
        safe_reply(m, "❌ Shell died. Send /shell to reopen.", 'Markdown')
        return

    # Give the command a moment to produce output, then flush
    time.sleep(0.3)
    _send_pty_output(info, force=True)

# ==================== ENV VAR COMMANDS ====================
def _env_file_picker(uid, chat_id, action, msg_id=None):
    files = [(n, t) for n, t in user_files.get(uid, []) if t == 'executable']
    if not files:
        safe_send(chat_id, "❌ No executable files. Upload a script first.", 'Markdown')
        return
    mk = types.InlineKeyboardMarkup(row_width=1)
    for n, _ in files:
        mk.add(types.InlineKeyboardButton(f"📄 {n}", callback_data=f"envpick_{action}_{uid}_{n}"))
    if msg_id:
        safe_edit(chat_id, msg_id, "📂 *Pick a file:*", 'Markdown', mk)
    else:
        safe_send(chat_id, "📂 *Pick a file:*", 'Markdown', mk)

@bot.message_handler(commands=['setenv'])
def cmd_setenv(message):
    _env_file_picker(message.from_user.id, message.chat.id, 'set')

@bot.message_handler(commands=['listenv'])
def cmd_listenv(message):
    _env_file_picker(message.from_user.id, message.chat.id, 'list')

@bot.message_handler(commands=['delenv'])
def cmd_delenv(message):
    _env_file_picker(message.from_user.id, message.chat.id, 'del')

@bot.callback_query_handler(func=lambda c: c.data.startswith('envpick_'))
def cb_envpick(c):
    parts  = c.data.split('_', 3)
    action = parts[1]; uid = int(parts[2]); filename = parts[3]
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "Access denied")

    if action == 'set':
        waiting_env[uid] = {'step': 'key', 'name': filename,
                            'chat_id': c.message.chat.id, 'msg_id': c.message.message_id}
        safe_edit(c.message.chat.id, c.message.message_id,
                  f"🔑 *Set env var for* `{filename}`\n\nSend the variable name (e.g. `BOT_TOKEN`):",
                  'Markdown')
    elif action == 'list':
        envs = user_envs.get(uid, {}).get(filename, {})
        if not envs:
            safe_edit(c.message.chat.id, c.message.message_id,
                      f"📋 No env vars set for `{filename}`", 'Markdown')
        else:
            text = f"📋 *Env vars for* `{filename}`\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
            for k, v in envs.items():
                masked = (v[:2] + '*' * max(0, len(v)-4) + v[-2:]) if len(v) > 4 else '****'
                text += f"`{k}` = `{masked}`\n"
            mk = types.InlineKeyboardMarkup()
            mk.add(types.InlineKeyboardButton("➕ Add Var", callback_data=f"envpick_set_{uid}_{filename}"))
            mk.add(types.InlineKeyboardButton("🗑️ Clear All", callback_data=f"clearenv_{uid}_{filename}"))
            safe_edit(c.message.chat.id, c.message.message_id, text, 'Markdown', mk)
    elif action == 'del':
        envs = user_envs.get(uid, {}).get(filename, {})
        if not envs:
            safe_edit(c.message.chat.id, c.message.message_id,
                      f"📋 No env vars set for `{filename}`", 'Markdown')
        else:
            mk = types.InlineKeyboardMarkup(row_width=1)
            for k in envs:
                mk.add(types.InlineKeyboardButton(f"🗑️ {k}", callback_data=f"deloneenv_{uid}_{filename}_{k}"))
            mk.add(types.InlineKeyboardButton("🗑️ Clear All", callback_data=f"clearenv_{uid}_{filename}"))
            safe_edit(c.message.chat.id, c.message.message_id,
                      f"🗑️ *Delete env var from* `{filename}`\n\nPick a key:", 'Markdown', mk)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith('deloneenv_'))
def cb_deloneenv(c):
    parts = c.data.split('_', 3); uid = int(parts[1]); filename = parts[2]; key = parts[3]
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "Access denied")
    delete_env_var(uid, filename, key)
    envs = user_envs.get(uid, {}).get(filename, {})
    if not envs:
        safe_edit(c.message.chat.id, c.message.message_id,
                  f"✅ Deleted `{key}` — no more env vars for `{filename}`", 'Markdown')
    else:
        mk = types.InlineKeyboardMarkup(row_width=1)
        for k in envs:
            mk.add(types.InlineKeyboardButton(f"🗑️ {k}", callback_data=f"deloneenv_{uid}_{filename}_{k}"))
        mk.add(types.InlineKeyboardButton("🗑️ Clear All", callback_data=f"clearenv_{uid}_{filename}"))
        safe_edit(c.message.chat.id, c.message.message_id,
                  f"✅ Deleted `{key}`\n\n🗑️ *Delete another from* `{filename}`:", 'Markdown', mk)
    bot.answer_callback_query(c.id, f"Deleted {key}")

@bot.callback_query_handler(func=lambda c: c.data.startswith('clearenv_'))
def cb_clearenv(c):
    parts = c.data.split('_', 2); uid, filename = int(parts[1]), parts[2]
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "Access denied")
    user_envs.get(uid, {}).pop(filename, None)
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('DELETE FROM user_envs WHERE uid=? AND filename=?', (uid, filename))
        conn.commit(); conn.close()
    except: pass
    safe_edit(c.message.chat.id, c.message.message_id,
              f"✅ *Cleared all env vars* for `{filename}`", 'Markdown')
    bot.answer_callback_query(c.id, "Cleared")

# ==================== SLUG COMMAND ====================
@bot.callback_query_handler(func=lambda c: c.data.startswith('setslug_'))
def cb_setslug(c):
    parts = c.data.split('_', 2); uid, filename = int(parts[1]), parts[2]
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "Access denied")
    waiting_slug[uid] = {'name': filename, 'uid': uid}
    safe_send(c.message.chat.id,
              f"🔗 *Set custom slug for* `{filename}`\n\n"
              f"Send your slug (letters, numbers, hyphens):\n"
              f"URL: `{HOST_URL or 'https://your-app.com'}/s/<slug>/`", 'Markdown')
    bot.answer_callback_query(c.id)

# ==================== BUILD KEYBOARD ====================
def build_main_keyboard(uid):
    is_admin = uid in admins
    is_owner = uid == OWNER_ID
    mk = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    mk.row(types.KeyboardButton("📂 Files"), types.KeyboardButton("👤 Profile"))
    mk.row(types.KeyboardButton("📊 Stats"), types.KeyboardButton("❓ Help"))
    mk.row(types.KeyboardButton("📢 Channel"), types.KeyboardButton("📞 Contact"))
    mk.row(types.KeyboardButton("💻 Shell"), types.KeyboardButton("🤖 Clone"))
    if is_admin:
        mk.row(types.KeyboardButton("🟢 Running"), types.KeyboardButton("💳 Subs"))
        mk.row(types.KeyboardButton("⏳ Pending"), types.KeyboardButton("🤖 Clones"))
        mk.row(types.KeyboardButton("👑 Admin"))
        if is_owner:
            mk.row(types.KeyboardButton("🔒 Lock"), types.KeyboardButton("📁 All Files"))
            mk.row(types.KeyboardButton("📜 Bot Logs"))
    return mk

# ==================== COMMANDS ====================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    uid = message.from_user.id
    if uid in banned_users:
        return safe_reply(message, "🚫 *You are banned from using this bot*", 'Markdown')
    active_users.add(uid)
    update_user_info(message)
    name = message.from_user.first_name or "User"

    sub_badge = ""
    if uid in subscriptions and subscriptions[uid]['expiry'] > datetime.now():
        diff = subscriptions[uid]['expiry'] - datetime.now()
        d = diff.days; h = diff.seconds // 3600; m = (diff.seconds % 3600) // 60
        sub_badge = f"  ⭐ {d}d {h}h {m}m" if d > 0 else f"  ⭐ {h}h {m}m"

    role    = get_user_tier(uid).capitalize()
    lim     = get_user_limit(uid)
    lim_txt = "∞" if lim == float('inf') else str(lim)
    welcome = (f"👋 *{name}*{sub_badge}\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
               f"{role}  •  `{get_user_count(uid)}/{lim_txt}` files\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
               f"Send a file to upload and host it")
    safe_send(message.chat.id, welcome, 'Markdown', build_main_keyboard(uid))

def get_help_text(section, uid):
    if section == 'general':
        return (
            "📖 *General Help*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
            "`/start` – Main menu\n"
            "`/help` – Show this help\n"
            "`/shell [cmd]` – Open private VPS shell\n"
            "`/git <url>` – Host from GitHub\n"
            "`/setenv`, `/listenv`, `/delenv` – Manage env vars\n"
            "`/clone` – Clone this bot\n"
            "\n*Features*\n"
            "• Upload any file to host it\n"
            "• 30+ languages auto‑detected\n"
            "• Websites from ZIP files\n"
            "• Per‑user isolated environment"
        )
    else:  # advanced
        tier = get_user_tier(uid)
        ram = get_user_ram_limit(uid)
        ram_str = "Unlimited" if ram is None else f"{ram//(1024**3)} GB"
        if tier == 'free':
            nproc = 128
            nofile = 4096
        elif tier == 'premium':
            nproc = 256
            nofile = 8192
        elif tier == 'admin':
            nproc = 512
            nofile = 16384
        else:
            nproc = "Unlimited"
            nofile = "Unlimited"
        return (
            "⚙️ *Advanced Help*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
            "*Your Private VPS*\n"
            f"• Tier: `{tier.capitalize()}`\n"
            f"• RAM limit: `{ram_str}`\n"
            f"• CPU limit: `1 hour` per process\n"
            f"• File size limit: `100 MB`\n"
            f"• Max processes: `{nproc}`\n"
            f"• Open files: `{nofile}`\n\n"
            "*Inside your shell*\n"
            "• `pyenv install 3.10.11` – install any Python\n"
            "• `pyenv global 3.10.11` – switch version\n"
            "• `nvm install 18` – install Node.js\n"
            "• `pip install ...`, `npm install ...` – freely\n"
            "\n*Resource Limits*\n"
            "Free: 1 GB / 128 procs | Premium: 2 GB / 256 procs | Admin: 4 GB / 512 procs | Owner: Unlimited"
        )

@bot.message_handler(commands=['help'])
def cmd_help(message):
    mk = types.InlineKeyboardMarkup()
    mk.row(types.InlineKeyboardButton("📖 General", callback_data="help_general"),
           types.InlineKeyboardButton("⚙️ Advanced", callback_data="help_advanced"))
    text = get_help_text('general', message.from_user.id)
    safe_reply(message, text, 'Markdown', mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith('help_'))
def cb_help(c):
    section = c.data[5:]
    text = get_help_text(section, c.from_user.id)
    mk = types.InlineKeyboardMarkup()
    mk.row(types.InlineKeyboardButton("📖 General", callback_data="help_general"),
           types.InlineKeyboardButton("⚙️ Advanced", callback_data="help_advanced"))
    safe_edit(c.message.chat.id, c.message.message_id, text, 'Markdown', mk)
    bot.answer_callback_query(c.id)

# ==================== GITHUB CLONING ====================
def clone_github_repo(url, uid):
    temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
    repo_name = url.rstrip('/').split('/')[-1].replace('.git', '') or "repo"
    try:
        subprocess.run(['git', 'clone', '--depth', '1', url, repo_name],
                       cwd=temp_dir, check=True, capture_output=True, timeout=60,
                       env=get_user_env(uid))
        repo_path = os.path.join(temp_dir, repo_name)
        zip_name = f"{repo_name}.zip"
        zip_path = os.path.join(temp_dir, zip_name)
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(repo_path):
                for file in files:
                    full_path = os.path.join(root, file)
                    arcname = os.path.relpath(full_path, repo_path)
                    zf.write(full_path, arcname)
        return zip_path, repo_name, temp_dir
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise e

@bot.message_handler(commands=['git'])
def cmd_git(message):
    uid = message.from_user.id
    try:
        url = message.text.split(' ', 1)[1].strip()
    except:
        return safe_reply(message, "❌ Usage: `/git <github_url>`", 'Markdown')
    process_github_url(message, url)

def process_github_url(message, url):
    uid = message.from_user.id
    if uid in banned_users:
        return safe_reply(message, "🚫 *You are banned from using this bot*", 'Markdown')
    if bot_locked and uid not in admins:
        return safe_reply(message, "🔒 *Bot Locked*\nUploads disabled temporarily", 'Markdown')
    if get_user_count(uid) >= get_user_limit(uid) and uid != OWNER_ID:
        return safe_reply(message, f"❌ *Limit reached* — max {get_user_limit(uid)} files", 'Markdown')

    status = safe_reply(message, f"⏳ *Cloning from GitHub*\n`{url}`", 'Markdown')
    try:
        zip_path, repo_name, temp_dir = clone_github_repo(url, uid)
        if is_website_zip(zip_path):
            ftype = 'site'
            name = f"{repo_name}.zip"
        else:
            ftype = 'executable'
            name = f"{repo_name}.zip"
        folder = get_user_folder(uid)
        final_path = os.path.join(folder, name)
        if os.path.exists(final_path):
            stop_script(uid, name)
            os.remove(final_path)
        shutil.move(zip_path, final_path)
        shutil.rmtree(temp_dir, ignore_errors=True)
        user_files.setdefault(uid, [])
        user_files[uid] = [(n, t) for n, t in user_files[uid] if n != name]
        user_files[uid].append((name, ftype))
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT OR REPLACE INTO files VALUES (?,?,?)', (uid, name, ftype))
        conn.commit(); conn.close()
        if ftype == 'site':
            safe_edit(status.chat.id, status.message_id, f"🌐 *Extracting website...*\n`{name}`", 'Markdown')
            handle_zip_website(final_path, uid, name, status)
        else:
            safe_edit(status.chat.id, status.message_id, f"🚀 *Launching*\n`{name}`", 'Markdown')
            execute_script(uid, final_path, status)
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else str(e)
        safe_edit(status.chat.id, status.message_id, f"❌ *Git clone failed*\n`{error_msg[:200]}`", 'Markdown')
    except Exception as e:
        logger.error(f"Git clone error: {e}", exc_info=True)
        safe_edit(status.chat.id, status.message_id, f"❌ *Error*\n`{str(e)[:200]}`", 'Markdown')

@bot.message_handler(func=lambda m: m.text and re.search(r'https?://(?:www\.)?github\.com/[^\s]+', m.text))
def handle_github_url(message):
    url = re.search(r'https?://(?:www\.)?github\.com/[^\s]+', message.text).group()
    process_github_url(message, url)

# ==================== BOT LOGS (OWNER ONLY) ====================
def get_bot_log_content(max_chars=3500):
    log_path = os.path.join(LOGS_DIR, 'bot.log')
    if not os.path.exists(log_path): return ""
    try:
        with open(log_path, 'r', errors='ignore') as f:
            content = f.read().strip()
        if len(content) > max_chars: content = "…" + content[-max_chars:]
        return content
    except: return ""

@bot.message_handler(commands=['botlogs'])
def cmd_botlogs(message):
    if message.from_user.id != OWNER_ID:
        return safe_reply(message, "🚫 *Owner Only*", 'Markdown')
    content = get_bot_log_content()
    display = content if content else "(no output yet)"
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton("🔄 Refresh", callback_data="refresh_botlogs"),
           types.InlineKeyboardButton("🛠️ Get txt", callback_data="getbotlogtxt"))
    safe_reply(message, f"📜 *Bot Logs*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n```\n{display}\n```", 'Markdown', mk)

@bot.message_handler(func=lambda m: m.text == "📜 Bot Logs")
def btn_botlogs(m):
    if m.from_user.id != OWNER_ID: return safe_reply(m, "🚫 *Owner Only*", 'Markdown')
    cmd_botlogs(m)

@bot.callback_query_handler(func=lambda c: c.data == "refresh_botlogs")
def cb_refresh_botlogs(c):
    if c.from_user.id != OWNER_ID: return bot.answer_callback_query(c.id, "Owner only")
    content = get_bot_log_content()
    display = content if content else "(no output yet)"
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton("🔄 Refresh", callback_data="refresh_botlogs"),
           types.InlineKeyboardButton("🛠️ Get txt", callback_data="getbotlogtxt"))
    safe_edit(c.message.chat.id, c.message.message_id,
              f"📜 *Bot Logs*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n```\n{display}\n```", 'Markdown', mk)
    bot.answer_callback_query(c.id, "Refreshed")

@bot.callback_query_handler(func=lambda c: c.data == "getbotlogtxt")
def cb_getbotlogtxt(c):
    if c.from_user.id != OWNER_ID: return bot.answer_callback_query(c.id, "Owner only")
    log_path = os.path.join(LOGS_DIR, 'bot.log')
    if not os.path.exists(log_path): return bot.answer_callback_query(c.id, "Log file missing")
    try:
        with open(log_path, 'r', errors='ignore') as f: content = f.read()
        if not content.strip():
            safe_send(c.message.chat.id, "📭 *No log output yet*", 'Markdown')
            return bot.answer_callback_query(c.id, "Empty log")
        MAX_BYTES = 49_500_000
        if len(content.encode('utf-8')) > MAX_BYTES:
            content = content.encode('utf-8')[-MAX_BYTES:].decode('utf-8', errors='ignore')
        temp_path = os.path.join(LOGS_DIR, "bot_full.log")
        with open(temp_path, 'w', encoding='utf-8') as f: f.write(content)
        with open(temp_path, 'rb') as f: bot.send_document(c.message.chat.id, f)
        os.remove(temp_path)
        bot.answer_callback_query(c.id, "Log sent")
    except Exception as e:
        logger.error(f"Failed to send bot log: {e}")
        bot.answer_callback_query(c.id, f"Error: {str(e)[:40]}")

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
        try: bot.send_message(target, "👑 *You are now an admin*\n\nSend /start to refresh.", 'Markdown')
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
        try: bot.send_message(target, "👤 *You are no longer an admin*\n\nSend /start to refresh.", 'Markdown')
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
        try: bot.send_message(target, f"🎉 *Subscription active* — {days}d until `{expiry.strftime('%Y-%m-%d')}`", 'Markdown')
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
            diff = exp - now
            status_str = (f"✅ Active — {diff.days}d {diff.seconds//3600}h left"
                          if exp > now else "❌ Expired")
            text = f"👤 `{target}`\n{status_str}\nExpires: `{exp.strftime('%Y-%m-%d %H:%M')}`"
        else:
            text = f"👤 `{target}`\n❌ No subscription"
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
    mk.add(*[types.InlineKeyboardButton(f"{d}d", callback_data=f"subdays_{target}_{d}")
              for d in [7,15,30,60,90,180,365]])
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
    safe_reply(message,
               "🤖 *Clone This Bot*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
               "1\\. Create a bot via @BotFather\n"
               "2\\. Copy your token\n"
               "3\\. Send `/settoken YOUR\\_TOKEN`\n\n"
               "You become the owner with full access\\.", 'MarkdownV2')

@bot.message_handler(commands=['settoken'])
def cmd_settoken(message):
    uid = message.from_user.id
    try: token = message.text.split()[1]
    except: return safe_reply(message, "❌ Usage: `/settoken YOUR_TOKEN`", 'Markdown')
    if len(token) < 35 or ':' not in token:
        return safe_reply(message, "❌ *Invalid token format*", 'Markdown')

    wait = safe_reply(message, "⏳ *Validating token...*", 'Markdown')
    try:
        info = telebot.TeleBot(token).get_me()
    except Exception as e:
        safe_edit(wait.chat.id, wait.message_id, f"❌ *Invalid token*\n`{str(e)[:100]}`", 'Markdown')
        return

    safe_edit(wait.chat.id, wait.message_id,
              f"✅ *Token valid* — @{info.username}\n⏳ Creating clone...", 'Markdown')
    try:
        clone_dir  = os.path.join(BASE_DIR, f'clone_{uid}')
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
        }
        safe_edit(wait.chat.id, wait.message_id,
                  f"✅ *Clone Running*\n@{info.username}\nYou are the owner", 'Markdown')
    except Exception as e:
        safe_edit(wait.chat.id, wait.message_id, f"❌ *Error*\n`{str(e)[:200]}`", 'Markdown')

@bot.message_handler(commands=['rmclone'])
def cmd_rmclone(message):
    uid = message.from_user.id; key = f"clone_{uid}"
    if key not in scripts: return safe_reply(message, "❌ *No clone found*", 'Markdown')
    mk = types.InlineKeyboardMarkup()
    mk.row(types.InlineKeyboardButton("✅ Remove", callback_data=f"rmclone_{uid}"),
           types.InlineKeyboardButton("❌ Cancel", callback_data="del_msg"))
    safe_reply(message, f"⚠️ Remove clone @{scripts[key].get('bot','?')}?", 'Markdown', mk)

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
    scripts[key].update({'process': proc, 'running': True, 'start': datetime.now()})
    bot.answer_callback_query(c.id, "Restarted")
    safe_edit(c.message.chat.id, c.message.message_id,
              f"🔄 *Clone restarted*\n@{info.get('bot','?')}\nPID: `{proc.pid}`", 'Markdown',
              _clone_remote_markup(uid, scripts[key]))

def _clone_remote_markup(uid, info):
    mk   = types.InlineKeyboardMarkup()
    alive = info.get('process') and info['process'].poll() is None
    if alive:
        mk.row(types.InlineKeyboardButton("⏹ Stop", callback_data=f"clone_stop_{uid}"),
               types.InlineKeyboardButton("🔄 Restart", callback_data=f"clone_restart_{uid}"))
    else:
        mk.add(types.InlineKeyboardButton("🔄 Restart", callback_data=f"clone_restart_{uid}"))
    mk.add(types.InlineKeyboardButton("🗑️ Remove", callback_data=f"rmclone_{uid}"))
    return mk

# ==================== MODERATION ====================
@bot.message_handler(commands=['ban'])
def cmd_ban(message):
    if message.from_user.id not in admins:
        return safe_reply(message, "🚫 *Admin Only*", 'Markdown')
    try:
        target = int(message.text.split()[1])
        if target == OWNER_ID:
            return safe_reply(message, "❌ Cannot ban owner", 'Markdown')
        banned_users.add(target)
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute('INSERT OR IGNORE INTO banned VALUES (?)', (target,))
            conn.commit(); conn.close()
        except: pass
        safe_reply(message, f"🚫 *Banned:* `{target}`", 'Markdown')
        try: bot.send_message(target, "🚫 *You have been banned from this bot*", 'Markdown')
        except: pass
    except:
        safe_reply(message, "❌ Usage: `/ban <uid>`", 'Markdown')

@bot.message_handler(commands=['unban'])
def cmd_unban(message):
    if message.from_user.id not in admins:
        return safe_reply(message, "🚫 *Admin Only*", 'Markdown')
    try:
        target = int(message.text.split()[1])
        banned_users.discard(target)
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute('DELETE FROM banned WHERE uid=?', (target,))
            conn.commit(); conn.close()
        except: pass
        safe_reply(message, f"✅ *Unbanned:* `{target}`", 'Markdown')
        try: bot.send_message(target, "✅ *Your ban has been lifted*", 'Markdown')
        except: pass
    except:
        safe_reply(message, "❌ Usage: `/unban <uid>`", 'Markdown')

@bot.message_handler(commands=['delete'])
def cmd_delete_file(message):
    if message.from_user.id not in admins:
        return safe_reply(message, "🚫 *Admin Only*", 'Markdown')
    try:
        parts = message.text.strip().split(None, 2)
        if len(parts) < 3:
            return safe_reply(message, "❌ Usage: `/delete <uid> <filename>`", 'Markdown')
        target_uid = int(parts[1]); fname = parts[2].strip()
        key = f"{target_uid}_{fname}"
        if key in scripts: scripts[key]['stopped_intentionally'] = True
        stop_script(target_uid, fname)
        path = os.path.join(get_user_folder(target_uid), fname)
        if os.path.exists(path): os.remove(path)
        slug = site_slugs.get(target_uid, {}).get(fname)
        if slug:
            sd = os.path.join(SITES_DIR, slug)
            if os.path.exists(sd): shutil.rmtree(sd, ignore_errors=True)
            site_slugs.get(target_uid, {}).pop(fname, None)
            try:
                conn = sqlite3.connect(DB_PATH)
                conn.execute('DELETE FROM site_slugs WHERE uid=? AND filename=?', (target_uid, fname))
                conn.commit(); conn.close()
            except: pass
        if target_uid in user_files:
            user_files[target_uid] = [(n, t) for n, t in user_files[target_uid] if n != fname]
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute('DELETE FROM files WHERE uid=? AND name=?', (target_uid, fname))
            conn.commit(); conn.close()
        except: pass
        if key in scripts: del scripts[key]
        safe_reply(message, f"✅ *Deleted* `{fname}` from uid `{target_uid}`", 'Markdown')
        try: bot.send_message(target_uid, f"🗑️ *File removed by admin:* `{fname}`", 'Markdown')
        except: pass
    except Exception as e:
        safe_reply(message, f"❌ Error: `{e}`\nUsage: `/delete <uid> <filename>`", 'Markdown')

@bot.message_handler(commands=['get'])
def cmd_get_file(message):
    if message.from_user.id not in admins:
        return safe_reply(message, "🚫 *Admin Only*", 'Markdown')
    try:
        parts = message.text.strip().split(None, 2)
        if len(parts) < 3:
            return safe_reply(message, "❌ Usage: `/get <uid> <filename>`", 'Markdown')
        target_uid = int(parts[1]); fname = parts[2].strip()
        path = os.path.join(get_user_folder(target_uid), fname)
        if not os.path.exists(path):
            return safe_reply(message, f"❌ File not found: `{fname}` for uid `{target_uid}`", 'Markdown')
        with open(path, 'rb') as f:
            bot.send_document(message.chat.id, f,
                              caption=f"📄 `{fname}`\nFrom uid: `{target_uid}`",
                              parse_mode='Markdown')
    except Exception as e:
        safe_reply(message, f"❌ Error: `{e}`\nUsage: `/get <uid> <filename>`", 'Markdown')

# ==================== RESTART ====================
@bot.message_handler(commands=['restart'])
def cmd_restart(message):
    if message.from_user.id != OWNER_ID:
        return safe_reply(message, "🚫 *Owner Only*", 'Markdown')
    mk = types.InlineKeyboardMarkup()
    mk.row(types.InlineKeyboardButton("✅ Yes, restart", callback_data="confirm_restart"),
           types.InlineKeyboardButton("❌ Cancel", callback_data="del_msg"))
    safe_reply(message,
               "⚠️ *Restart Bot*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
               "Kills all scripts, deletes all files, clears data.\n"
               "Subscriptions and admins are preserved.",
               'Markdown', mk)

@bot.callback_query_handler(func=lambda c: c.data == "confirm_restart")
def cb_confirm_restart(c):
    if c.from_user.id != OWNER_ID: return bot.answer_callback_query(c.id, "Owner only")
    bot.answer_callback_query(c.id, "Restarting...")
    safe_edit(c.message.chat.id, c.message.message_id, "🔄 *Restarting...*\nClearing data and restarting.", 'Markdown')
    chat_id = c.message.chat.id
    msg_id  = c.message.message_id
    def _do():
        for uid in list(active_users):
            try: bot.send_message(uid, "🔄 Bot restarting — all files cleared. Please re-upload.")
            except: pass
            time.sleep(0.05)
        time.sleep(1)
        clear_old_data()
        try:
            marker = os.path.join(DB_DIR, 'restart_marker.json')
            with open(marker, 'w') as f:
                json.dump({'chat_id': chat_id, 'msg_id': msg_id}, f)
        except: pass
        os.execv(sys.executable, ['python'] + sys.argv)
    threading.Thread(target=_do, daemon=False).start()

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
        try: bot.send_message(target_uid, text, 'Markdown'); sent += 1; time.sleep(0.05)
        except: failed += 1
    safe_edit(c.message.chat.id, c.message.message_id,
              f"📢 *Done*\n✅ {sent} sent  •  ❌ {failed} failed", 'Markdown')

# ==================== UPLOAD HANDLER ====================
@bot.message_handler(content_types=['document'])
def handle_upload(message):
    uid = message.from_user.id
    update_user_info(message)
    if uid in banned_users:
        return safe_reply(message, "🚫 *You are banned from using this bot*", 'Markdown')
    if bot_locked and uid not in admins:
        return safe_reply(message, "🔒 *Bot Locked*\nUploads disabled temporarily", 'Markdown')
    if get_user_count(uid) >= get_user_limit(uid) and uid != OWNER_ID:
        return safe_reply(message, f"❌ *Limit reached* — max {get_user_limit(uid)} files", 'Markdown')

    file_info = bot.get_file(message.document.file_id)
    name = message.document.file_name or f"file_{int(time.time())}"
    ext  = os.path.splitext(name)[1].lower()

    if message.document.file_size > 20*1024*1024:
        return safe_reply(message, "❌ *File too large* — max 20MB", 'Markdown')

    status = safe_reply(message, f"📥 *Uploading*\n`{name}`", 'Markdown')
    try:
        data   = bot.download_file(file_info.file_path)
        folder = get_user_folder(uid)
        uid_s  = message.document.file_unique_id
        temp   = os.path.join(folder, f"temp_{uid_s}_{name}")
        with open(temp, 'wb') as f: f.write(data)

        old_path = os.path.join(folder, name)
        if os.path.exists(old_path):
            if hashlib.md5(open(old_path,'rb').read()).hexdigest() == hashlib.md5(data).hexdigest():
                os.remove(temp)
                safe_edit(status.chat.id, status.message_id,
                         "⚠️ *Same file detected*\n`" + name + "`\n\n"
                         "Telegram served a cached copy — no changes found.\n"
                         "Rename the file slightly and re-upload.", 'Markdown')
                return
            old_key = f"{uid}_{name}"
            if old_key in scripts:
                scripts[old_key]['stopped_intentionally'] = True
            stop_script(uid, name)
            for d in os.listdir(EXTRACT_DIR):
                if d.startswith(f"{uid}_"):
                    shutil.rmtree(os.path.join(EXTRACT_DIR, d), ignore_errors=True)
            if old_key in scripts:
                del scripts[old_key]
            time.sleep(1)
            try: os.remove(old_path)
            except Exception as e: logger.warning(f"Could not remove old file {old_path}: {e}")

        if uid == OWNER_ID or uid in admins:
            safe_file, scan = True, "Trusted"
        elif ext == '.zip':
            safe_file, scan = scan_zip_contents(temp)
        else:
            safe_file, scan = check_malicious(temp)

        if not safe_file:
            fhash = hashlib.md5(f"{uid}_{name}_{time.time()}".encode()).hexdigest()
            pending_path = os.path.join(PENDING_DIR, name)
            if os.path.exists(pending_path):
                base, ext_ = os.path.splitext(name)
                pending_path = os.path.join(PENDING_DIR, f"{base}_{fhash[:6]}{ext_}")
            shutil.move(temp, pending_path)
            pending[fhash] = {'uid': uid, 'name': name, 'path': pending_path}
            conn = sqlite3.connect(DB_PATH)
            conn.execute('INSERT INTO pending VALUES (?,?,?,?,?)',
                         (fhash, uid, name, pending_path, datetime.now().isoformat()))
            conn.commit(); conn.close()
            block_mk = types.InlineKeyboardMarkup()
            block_mk.add(types.InlineKeyboardButton("💳 Buy Premium to bypass", url=OWNER_TG))
            safe_edit(status.chat.id, status.message_id,
                     f"🚫 *Blocked*\n`{name}`\n⚠️ {scan}\n\nSent to owner for review.",
                     'Markdown', block_mk)
            mk = types.InlineKeyboardMarkup()
            mk.row(types.InlineKeyboardButton("✅ Approve", callback_data=f"app_{fhash}"),
                   types.InlineKeyboardButton("❌ Reject", callback_data=f"rej_{fhash}"))
            user_parts = [f"User: `{uid}`"]
            if message.from_user.username: user_parts.append(f"@{message.from_user.username}")
            fn = ((message.from_user.first_name or "") +
                  (" " + message.from_user.last_name if message.from_user.last_name else "")).strip()
            if fn: user_parts.append(f"Name: {fn}")
            try:
                with open(pending_path, 'rb') as f:
                    bot.send_document(OWNER_ID, f,
                                      caption=f"🚨 *Pending*\n📄 `{name}`\n{chr(10).join(user_parts)}\n⚠️ {scan}",
                                      parse_mode='Markdown', reply_markup=mk)
            except:
                bot.send_message(OWNER_ID,
                                 f"🚨 *Pending*\n📄 `{name}`\n{chr(10).join(user_parts)}\n⚠️ {scan}\n🆔 `{fhash}`",
                                 parse_mode='Markdown', reply_markup=mk)
            return

        final = os.path.join(folder, name)
        shutil.move(temp, final)

        if ext == '.zip' and is_website_zip(final):
            ftype = 'site'
            user_files.setdefault(uid, [])
            user_files[uid] = [(n, t) for n, t in user_files[uid] if n != name]
            user_files[uid].append((name, ftype))
            conn = sqlite3.connect(DB_PATH)
            conn.execute('INSERT OR REPLACE INTO files VALUES (?,?,?)', (uid, name, ftype))
            conn.commit(); conn.close()
            if uid != OWNER_ID: _forward_to_owner(message, final, name, 'site')
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

        if uid != OWNER_ID: _forward_to_owner(message, final, name, ftype)

        if ftype == 'executable':
            safe_edit(status.chat.id, status.message_id, f"🚀 *Launching*\n`{name}`", 'Markdown')
            execute_script(uid, final, status)
        else:
            url = get_file_url(uid, name)
            mk = types.InlineKeyboardMarkup()
            if url: mk.add(types.InlineKeyboardButton("🔗 View File", url=url))
            safe_edit(status.chat.id, status.message_id, f"✅ *Hosted*\n`{name}`",
                      'Markdown', mk if url else None)

    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        try: safe_edit(status.chat.id, status.message_id, f"❌ *Upload failed*\n`{str(e)[:200]}`", 'Markdown')
        except: pass

def _forward_to_owner(message, path, name, ftype):
    uid = message.from_user.id
    parts = [f"User: `{uid}`"]
    if message.from_user.username: parts.append(f"@{message.from_user.username}")
    fn = ((message.from_user.first_name or "") +
          (" " + message.from_user.last_name if message.from_user.last_name else "")).strip()
    if fn: parts.append(f"Name: {fn}")
    try:
        with open(path, 'rb') as f:
            bot.send_document(OWNER_ID, f,
                              caption=f"📨 *New Upload*\n📄 `{name}`\n{chr(10).join(parts)}\nType: `{ftype}`",
                              parse_mode='Markdown')
    except Exception as e: logger.error(f"Forward failed: {e}")

# ==================== APPROVAL CALLBACKS ====================
@bot.callback_query_handler(func=lambda c: c.data.startswith('app_'))
def cb_approve(c):
    if c.from_user.id != OWNER_ID: return bot.answer_callback_query(c.id, "Owner only")
    fhash = c.data[4:]
    if fhash not in pending:
        bot.answer_callback_query(c.id, "Expired")
        try: bot.delete_message(c.message.chat.id, c.message.message_id)
        except: pass
        return
    info = pending[fhash]; uid, name, path = info['uid'], info['name'], info['path']
    if not os.path.exists(path): return bot.answer_callback_query(c.id, "File missing")
    folder = get_user_folder(uid); dest = os.path.join(folder, name)
    if os.path.exists(dest): stop_script(uid, name); os.remove(dest)
    shutil.move(path, dest)
    ext   = os.path.splitext(name)[1].lower()
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
        bot.edit_message_caption(caption=f"✅ *Approved*\n`{name}`", chat_id=c.message.chat.id,
                                 message_id=c.message.message_id, parse_mode='Markdown', reply_markup=None)
    except:
        try: safe_edit(c.message.chat.id, c.message.message_id, f"✅ *Approved*\n`{name}`", 'Markdown')
        except: pass
    bot.answer_callback_query(c.id, "Approved ✅")

@bot.callback_query_handler(func=lambda c: c.data.startswith('rej_'))
def cb_reject(c):
    if c.from_user.id != OWNER_ID: return bot.answer_callback_query(c.id, "Owner only")
    fhash = c.data[4:]
    if fhash not in pending:
        bot.answer_callback_query(c.id, "Expired")
        try: bot.delete_message(c.message.chat.id, c.message.message_id)
        except: pass
        return
    info = pending[fhash]; uid, name, path = info['uid'], info['name'], info['path']
    if os.path.exists(path): os.remove(path)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('DELETE FROM pending WHERE hash=?', (fhash,))
    conn.commit(); conn.close()
    del pending[fhash]
    try: bot.send_message(uid, f"❌ *File Rejected*\n`{name}`", 'Markdown')
    except: pass
    try:
        bot.edit_message_caption(caption=f"❌ *Rejected*\n`{name}`", chat_id=c.message.chat.id,
                                 message_id=c.message.message_id, parse_mode='Markdown', reply_markup=None)
    except:
        try: safe_edit(c.message.chat.id, c.message.message_id, f"❌ *Rejected*\n`{name}`", 'Markdown')
        except: pass
    bot.answer_callback_query(c.id, "Rejected ❌")

# ==================== CONTROL MARKUP ====================
def build_control_markup(uid, name, ftype):
    mk = types.InlineKeyboardMarkup(row_width=2)
    if ftype == 'executable':
        if is_running(uid, name):
            mk.add(types.InlineKeyboardButton("⏹ Stop",    callback_data=f"stop_{uid}_{name}"),
                   types.InlineKeyboardButton("🔄 Restart", callback_data=f"restart_{uid}_{name}"))
            mk.add(types.InlineKeyboardButton("📜 Logs",   callback_data=f"logs_{uid}_{name}"))
        else:
            mk.add(types.InlineKeyboardButton("▶️ Start",  callback_data=f"start_{uid}_{name}"),
                   types.InlineKeyboardButton("📜 Logs",   callback_data=f"logs_{uid}_{name}"))
    elif ftype == 'site':
        slug = site_slugs.get(uid, {}).get(name)
        url  = get_site_url(slug) if slug else None
        if url: mk.add(types.InlineKeyboardButton("🌐 Open Website", url=url))
        mk.add(types.InlineKeyboardButton("🔗 Set Slug", callback_data=f"setslug_{uid}_{name}"))
    else:
        url = get_file_url(uid, name)
        if url: mk.add(types.InlineKeyboardButton("🔗 View File", url=url))
    mk.add(types.InlineKeyboardButton("🗑️ Delete", callback_data=f"del_{uid}_{name}"),
           types.InlineKeyboardButton("🔙 Back",   callback_data=f"back_{uid}"))
    return mk

# ==================== FILE CONTROL CALLBACKS ====================
def get_script_logs(key, max_chars=3500):
    if key not in scripts: return ""
    info  = scripts[key]
    parts = []
    for pk in ('log', 'stderr_log'):
        p = info.get(pk)
        if p and os.path.exists(p):
            try:
                with open(p, 'r', errors='ignore') as f: txt = f.read().strip()
                if txt: parts.append(txt)
            except: pass
    content = "\n".join(parts).strip()
    return ("…" + content[-max_chars:]) if len(content) > max_chars else content

def file_exists_check(uid, name, callback_query):
    files = user_files.get(uid, [])
    exists = any(n == name for n, _ in files)
    if not exists:
        safe_edit(callback_query.message.chat.id, callback_query.message.message_id,
                  f"🗑️ *File has been deleted*\n`{name}`", 'Markdown')
        bot.answer_callback_query(callback_query.id, "File deleted")
        return False
    return True

@bot.callback_query_handler(func=lambda c: c.data.startswith('file_'))
def cb_file(c):
    parts = c.data.split('_')
    if len(parts) == 3:
        uid = int(parts[1])
        idx = int(parts[2])
        files = user_files.get(uid, [])
        if idx >= len(files):
            return bot.answer_callback_query(c.id, "❌ File not found")
        name, ftype = files[idx]
    else:
        return bot.answer_callback_query(c.id, "❌ Invalid callback, please refresh")

    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "❌ Access denied")
    if not file_exists_check(uid, name, c): return
    path = os.path.join(get_user_folder(uid), name)
    size = fmt_size(os.path.getsize(path)) if os.path.exists(path) else "?"
    if ftype == 'executable':
        running = is_running(uid, name)
        status_txt = "🟢 Running" if running else "⭕ Stopped"
        uptime_txt = ""
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
        status_txt = f"🌐 Website — slug: `{slug}`"; uptime_txt = ""
    else:
        status_txt = "📁 Hosted"; uptime_txt = ""
    env_count = len(user_envs.get(uid, {}).get(name, {}))
    env_line  = f"\nEnv vars: `{env_count}`" if env_count else ""
    text = f"📄 `{name}`\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\nSize: `{size}`  •  {status_txt}{uptime_txt}{env_line}"
    safe_edit(c.message.chat.id, c.message.message_id, text, 'Markdown',
              build_control_markup(uid, name, ftype))
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith('start_'))
def cb_start(c):
    parts = c.data.split('_', 2); uid, name = int(parts[1]), parts[2]
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "❌ Access denied")
    if not file_exists_check(uid, name, c): return
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
    if not file_exists_check(uid, name, c): return
    if stop_script(uid, name):
        safe_edit(c.message.chat.id, c.message.message_id,
                  f"⏹ *Stopped* `{name}`", 'Markdown', build_control_markup(uid, name, 'executable'))
        bot.answer_callback_query(c.id, "Stopped")
    else:
        bot.answer_callback_query(c.id, "⚠️ Not running")

@bot.callback_query_handler(func=lambda c: c.data.startswith('restart_'))
def cb_restart(c):
    parts = c.data.split('_', 2); uid, name = int(parts[1]), parts[2]
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "❌ Access denied")
    if not file_exists_check(uid, name, c): return
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
    if not file_exists_check(uid, name, c): return
    key = f"{uid}_{name}"
    if key not in scripts: return bot.answer_callback_query(c.id, "📭 No logs yet")
    content    = get_script_logs(key)
    running    = scripts[key].get('running', False)
    code       = scripts[key].get('code')
    status_txt = "🟢 Running" if running else (f"⭕ Stopped (exit {code})" if code is not None else "⭕ Stopped")
    display    = content if content else "(no output yet)"
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{uid}_{name}"),
           types.InlineKeyboardButton("🛠️ Get txt", callback_data=f"getlogtxt_{uid}_{name}"))
    bot.send_message(c.message.chat.id,
                     f"📜 *Logs:* `{name}`\n{status_txt}\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n```\n{display}\n```",
                     parse_mode='Markdown', reply_markup=mk)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith('getlogtxt_'))
def cb_getlogtxt(c):
    parts = c.data.split('_', 2)
    uid, name = int(parts[1]), parts[2]
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "❌ Access denied")
    if not file_exists_check(uid, name, c): return
    key = f"{uid}_{name}"
    if key not in scripts:
        return bot.answer_callback_query(c.id, "No logs")
    info = scripts[key]
    combined = ""
    for log_key in ('log', 'stderr_log'):
        path = info.get(log_key)
        if path and os.path.exists(path):
            try:
                with open(path, 'r', errors='ignore') as f:
                    content = f.read()
                    if content:
                        combined += content
            except Exception as e:
                logger.warning(f"Failed to read {path}: {e}")

    if not combined.strip():
        safe_send(c.message.chat.id, f"📭 *No log output yet* for `{name}`", 'Markdown')
        return bot.answer_callback_query(c.id, "Empty log")

    MAX_BYTES = 49_500_000
    if len(combined.encode('utf-8')) > MAX_BYTES:
        combined = combined.encode('utf-8')[-MAX_BYTES:].decode('utf-8', errors='ignore')

    log_filename = f"{name}.log"
    temp_path = os.path.join(LOGS_DIR, log_filename)
    try:
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(combined)
        with open(temp_path, 'rb') as f:
            bot.send_document(c.message.chat.id, f)
        bot.answer_callback_query(c.id, "Log sent")
    except Exception as e:
        logger.error(f"Document send failed: {e}")
        bot.answer_callback_query(c.id, f"Error: {str(e)[:40]}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@bot.callback_query_handler(func=lambda c: c.data.startswith('refresh_'))
def cb_refresh(c):
    parts = c.data.split('_', 2); uid, name = int(parts[1]), parts[2]
    if not file_exists_check(uid, name, c): return
    key = f"{uid}_{name}"
    if key not in scripts: return bot.answer_callback_query(c.id, "📭 No logs")
    content    = get_script_logs(key)
    running    = scripts[key].get('running', False)
    code       = scripts[key].get('code')
    status_txt = "🟢 Running" if running else (f"⭕ Stopped (exit {code})" if code is not None else "⭕ Stopped")
    display    = content if content else "(no output yet)"
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{uid}_{name}"),
           types.InlineKeyboardButton("🛠️ Get txt", callback_data=f"getlogtxt_{uid}_{name}"))
    safe_edit(c.message.chat.id, c.message.message_id,
              f"📜 *Logs:* `{name}`\n{status_txt}\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n```\n{display}\n```",
              'Markdown', mk)
    bot.answer_callback_query(c.id, "Refreshed")

@bot.callback_query_handler(func=lambda c: c.data.startswith('del_') and not c.data.startswith('del_msg'))
def cb_delete(c):
    parts = c.data.split('_', 2); uid, name = int(parts[1]), parts[2]
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "❌ Access denied")
    if not file_exists_check(uid, name, c): return
    key = f"{uid}_{name}"
    if key in scripts: scripts[key]['stopped_intentionally'] = True
    stop_script(uid, name)

    path = os.path.join(get_user_folder(uid), name)
    if os.path.exists(path):
        try: os.remove(path)
        except: pass

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

    if uid in user_files:
        user_files[uid] = [(n, t) for n, t in user_files[uid] if n != name]
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('DELETE FROM files WHERE uid=? AND name=?', (uid, name))
        conn.commit(); conn.close()
    except: pass

    if key in scripts:
        for lk in ('log', 'stderr_log'):
            lp = scripts[key].get(lk)
            if lp and os.path.exists(lp):
                try: os.remove(lp)
                except: pass
        del scripts[key]

    bot.answer_callback_query(c.id, "✅ Deleted")
    files = user_files.get(uid, [])
    if not files:
        safe_edit(c.message.chat.id, c.message.message_id,
                  "📂 *No files*\nSend a file to upload it", 'Markdown'); return
    text = f"📂 *Files* ({len(files)})\n"
    mk = types.InlineKeyboardMarkup(row_width=1)
    for i, (n, t) in enumerate(files):
        dot  = "🟢" if t == 'executable' and is_running(uid, n) else ("🌐" if t == 'site' else "⚪")
        icon = "🚀" if t == 'executable' else ("🌐" if t == 'site' else "📄")
        dn   = n if len(n) < 30 else n[:27] + "..."
        mk.add(types.InlineKeyboardButton(f"{dot} {icon} {dn}", callback_data=f"file_{uid}_{i}"))
    safe_edit(c.message.chat.id, c.message.message_id, text, 'Markdown', mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith('back_'))
def cb_back(c):
    uid   = int(c.data.split('_')[1])
    files = user_files.get(uid, [])
    if not files:
        safe_edit(c.message.chat.id, c.message.message_id, "📂 *No files*", 'Markdown')
        return bot.answer_callback_query(c.id)
    text = f"📂 *Files* ({len(files)})\n"
    mk   = types.InlineKeyboardMarkup(row_width=1)
    for i, (n, t) in enumerate(files):
        dot  = "🟢" if t == 'executable' and is_running(uid, n) else ("🌐" if t == 'site' else "⚪")
        icon = "🚀" if t == 'executable' else ("🌐" if t == 'site' else "📄")
        dn   = n if len(n) < 30 else n[:27] + "..."
        mk.add(types.InlineKeyboardButton(f"{dot} {icon} {dn}", callback_data=f"file_{uid}_{i}"))
    safe_edit(c.message.chat.id, c.message.message_id, text, 'Markdown', mk)
    bot.answer_callback_query(c.id)

# ==================== BUTTON HANDLERS ====================
def exit_shell_if_active(uid):
    shell_sessions.pop(uid, None)
    waiting_env.pop(uid, None)
    waiting_slug.pop(uid, None)

@bot.message_handler(func=lambda m: m.text == "📂 Files")
def btn_files(m):
    uid = m.from_user.id; exit_shell_if_active(uid)
    files = user_files.get(uid, [])
    if not files: return safe_reply(m, "📂 *No files*\nSend a file to upload it", 'Markdown')
    text = f"📂 *Files* ({len(files)})\n"
    mk   = types.InlineKeyboardMarkup(row_width=1)
    for i, (n, t) in enumerate(files):
        dot  = "🟢" if t == 'executable' and is_running(uid, n) else ("🌐" if t == 'site' else "⚪")
        icon = "🚀" if t == 'executable' else ("🌐" if t == 'site' else "📄")
        dn   = n if len(n) < 30 else n[:27] + "..."
        mk.add(types.InlineKeyboardButton(f"{dot} {icon} {dn}", callback_data=f"file_{uid}_{i}"))
    safe_reply(m, text, 'Markdown', mk)

@bot.message_handler(func=lambda m: m.text == "👤 Profile")
def btn_profile(m):
    uid = m.from_user.id; exit_shell_if_active(uid)
    tier    = get_user_tier(uid).capitalize()
    lim     = get_user_limit(uid); lim_txt = "∞" if lim == float('inf') else str(lim)
    count   = get_user_count(uid)
    joined  = get_user_first_seen(uid)
    sub_line = ""
    if uid in subscriptions:
        exp = subscriptions[uid]['expiry']
        if exp > datetime.now():
            days = (exp - datetime.now()).days
            sub_line = f"\nSub expires: `{exp.strftime('%Y-%m-%d')}` ({days}d)"
        else: sub_line = "\nSub: `Expired`"
    elif uid not in admins: sub_line = "\nSub: `None`"
    running_count = len([s for s in scripts.values()
                         if s.get('uid') == uid and s.get('running')
                         and not s['key'].startswith('clone_')])
    text = (f"👤 *Profile*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
            f"ID: `{uid}`\nTier: {tier}\nFiles: `{count}/{lim_txt}`\n"
            f"Running: `{running_count}`\nJoined: `{joined}`{sub_line}")
    mk = types.InlineKeyboardMarkup()
    if uid not in admins and uid != OWNER_ID:
        mk.add(types.InlineKeyboardButton("💳 Buy Premium", url=OWNER_TG))
    safe_reply(m, text, 'Markdown', mk)

@bot.message_handler(func=lambda m: m.text == "📊 Stats")
def btn_stats(m):
    uid = m.from_user.id; exit_shell_if_active(uid)
    running = len([s for s in scripts.values()
                   if s.get('running') and not s['key'].startswith('clone_')])
    lim     = get_user_limit(uid); lim_txt = "∞" if lim == float('inf') else str(lim)
    try:
        cpu = psutil.cpu_percent(interval=0.5); mem = psutil.virtual_memory()
        sys_line = f"\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\nCPU: `{cpu}%`  •  RAM: `{mem.used/(1024**3):.1f}/{mem.total/(1024**3):.1f}GB`"
    except: sys_line = ""
    platform_line = f"\nPlatform: `{HOST_URL}`" if HOST_URL else ""
    text = (f"📊 *Stats*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
            f"👥 Users: `{len(active_users)}`\n📁 Files: `{sum(len(f) for f in user_files.values())}`\n"
            f"🚀 Running: `{running}`\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
            f"Your files: `{get_user_count(uid)}/{lim_txt}`{platform_line}{sys_line}")
    safe_reply(m, text, 'Markdown')

@bot.message_handler(func=lambda m: m.text == "❓ Help")
def btn_help(m):
    exit_shell_if_active(m.from_user.id); cmd_help(m)

@bot.message_handler(func=lambda m: m.text == "📢 Channel")
def btn_channel(m):
    exit_shell_if_active(m.from_user.id)
    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("📢 Join @BlacScriptz", url=UPDATE_CHANNEL))
    safe_reply(m,
               "📢 *BlacScriptz*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
               "Free source codes, bots, tools — regularly updated.\n\nJoin to stay ahead 🚀",
               'Markdown', mk)

@bot.message_handler(func=lambda m: m.text == "📞 Contact")
def btn_contact(m):
    exit_shell_if_active(m.from_user.id)
    mk = types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton("💳 Buy Premium", url=OWNER_TG))
    mk.add(types.InlineKeyboardButton("🐛 Report a Bug", url=OWNER_TG))
    mk.add(types.InlineKeyboardButton("📢 Channel", url=UPDATE_CHANNEL))
    safe_reply(m, "📞 *Contact & Support*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\nReach out via the buttons below.", 'Markdown', mk)

@bot.message_handler(func=lambda m: m.text == "💳 Subs")
def btn_subs(m):
    if m.from_user.id not in admins: return
    exit_shell_if_active(m.from_user.id)
    active = [(uid, sub) for uid, sub in subscriptions.items() if sub['expiry'] > datetime.now()]
    if not active: return safe_reply(m, "💳 *Subscriptions*\nNone active", 'Markdown')
    text = f"💳 *Subscriptions* ({len(active)} active)\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
    for uid, sub in active:
        text += f"`{uid}` — {(sub['expiry'] - datetime.now()).days}d\n"
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
        cpu_s, mem_s = get_process_stats(s['process'].pid) if s.get('process') else ("?","?")
        text += f"{s['icon']} `{s['name']}`\nuid `{s['uid']}`  •  {uptime}  •  CPU {cpu_s}  •  RAM {mem_s}\n\n"
    safe_reply(m, text, 'Markdown')

@bot.message_handler(func=lambda m: m.text == "⏳ Pending")
def btn_pending(m):
    if m.from_user.id not in admins: return
    exit_shell_if_active(m.from_user.id)
    if not pending: return safe_reply(m, "⏳ *No pending approvals*", 'Markdown')
    for fhash, info in list(pending.items()):
        mk = types.InlineKeyboardMarkup()
        mk.row(types.InlineKeyboardButton("✅ Approve", callback_data=f"app_{fhash}"),
               types.InlineKeyboardButton("❌ Reject",  callback_data=f"rej_{fhash}"))
        path = info.get('path', '')
        try:
            if os.path.exists(path):
                with open(path, 'rb') as f:
                    bot.send_document(m.chat.id, f,
                                      caption=f"📄 `{info['name']}`\nUser: `{info['uid']}`",
                                      parse_mode='Markdown', reply_markup=mk)
            else:
                safe_send(m.chat.id, f"📄 `{info['name']}`\nUser: `{info['uid']}`\n⚠️ File missing",
                          'Markdown', mk)
        except: pass

@bot.message_handler(func=lambda m: m.text == "🤖 Clones")
def btn_clones(m):
    if m.from_user.id not in admins: return
    exit_shell_if_active(m.from_user.id)
    clones = {k: v for k, v in scripts.items() if k.startswith('clone_')}
    if not clones: return safe_reply(m, "🤖 *No active clones*", 'Markdown')
    for key, s in clones.items():
        secs  = int((datetime.now() - s['start']).total_seconds())
        h, r  = divmod(secs, 3600); mins, sec = divmod(r, 60)
        alive = "🟢" if s.get('process') and s['process'].poll() is None else "🔴"
        pid   = s['process'].pid if s.get('process') else "?"
        cpu_s, mem_s = (get_process_stats(s['process'].pid)
                        if s.get('process') and s['process'].poll() is None else ("?","?"))
        uid_c = s['uid']
        text  = (f"🤖 *Clone*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
                 f"{alive} @{s.get('bot','?')}\n"
                 f"Owner: `{uid_c}`  •  PID: `{pid}`\n"
                 f"Uptime: `{h}h {mins}m`\n"
                 f"CPU: `{cpu_s}`  •  RAM: `{mem_s}`")
        safe_reply(m, text, 'Markdown', _clone_remote_markup(uid_c, s))

@bot.message_handler(func=lambda m: m.text == "👑 Admin")
def btn_admin(m):
    if m.from_user.id not in admins: return
    exit_shell_if_active(m.from_user.id)
    total_running = len([s for s in scripts.values()
                         if s.get('running') and not s['key'].startswith('clone_')])
    clones = len([s for s in scripts.values() if s['key'].startswith('clone_')])
    try:
        cpu = psutil.cpu_percent(interval=0.3); mem = psutil.virtual_memory()
        sys_info = f"\nCPU: `{cpu}%`  •  RAM: `{mem.percent}%`"
    except: sys_info = ""
    text = (f"👑 *Admin Panel*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
            f"Users: `{len(active_users)}`  •  Files: `{sum(len(f) for f in user_files.values())}`\n"
            f"Running: `{total_running}`  •  Pending: `{len(pending)}`  •  Clones: `{clones}`{sys_info}\n"
            f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
            f"`/shell`  `/broadcast`  `/restart`\n`/addadmin`  `/removeadmin`\n`/addsub`  `/checksub`  `/botlogs`  `/git`")
    safe_reply(m, text, 'Markdown')

@bot.message_handler(func=lambda m: m.text == "💻 Shell")
def btn_shell(m):
    uid = m.from_user.id
    shell_sessions[uid] = True
    info = _get_or_create_shell(uid)
    info['chat_id'] = m.chat.id
    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("❌ Exit Shell", callback_data="exit_shell"))
    sent = safe_reply(m, "💻 *Shell Active*\nInitializing PTY...", 'Markdown', mk)
    info['status_msg_id'] = sent.message_id
    time.sleep(0.5)
    _send_pty_output(info, force=True)

@bot.message_handler(func=lambda m: m.text == "📁 All Files")
def btn_all_files(m):
    if m.from_user.id != OWNER_ID: return
    exit_shell_if_active(m.from_user.id)
    if not user_files: return safe_reply(m, "📁 *No files uploaded yet*", 'Markdown')
    text = "📁 *All User Files*\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
    for uid, files in user_files.items():
        if not files: continue
        ck = f"clone_{uid}"
        clone_tag = f" 🤖 (@{scripts[ck]['bot']})" if ck in scripts else ""
        text += f"👤 `{uid}`{clone_tag} — {len(files)} file(s)\n"
        for n, t in files:
            icon = "🚀" if t == 'executable' else ("🌐" if t == 'site' else "📄")
            dot  = "🟢 " if t == 'executable' and is_running(uid, n) else ""
            text += f"  {dot}{icon} `{n}`\n"
        text += "\n"
        if len(text) > 3500:
            safe_reply(m, text, 'Markdown'); text = ""
    if text.strip(): safe_reply(m, text, 'Markdown')

@bot.message_handler(func=lambda m: m.text == "🤖 Clone")
def btn_clone(m):
    exit_shell_if_active(m.from_user.id); cmd_clone(m)

# ==================== ENV & SLUG CONVERSATION ====================
@bot.message_handler(func=lambda m: m.from_user and m.from_user.id in waiting_env and m.text)
def env_conversation(m):
    uid   = m.from_user.id; state = waiting_env[uid]; text = m.text.strip()
    if state['step'] == 'key':
        if not re.match(r'^[A-Z_][A-Z0-9_]*$', text.upper()):
            return safe_reply(m, "❌ Invalid name. Use uppercase letters, numbers, underscores only.\nTry again:", 'Markdown')
        waiting_env[uid] = {'step': 'val', 'name': state['name'], 'key': text.upper(),
                            'chat_id': state['chat_id'], 'msg_id': state['msg_id']}
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
    waiting_env[uid] = {'step': 'key', 'name': filename,
                        'chat_id': c.message.chat.id, 'msg_id': c.message.message_id}
    safe_edit(c.message.chat.id, c.message.message_id,
              f"🔑 Send the next variable *name* for `{filename}`:", 'Markdown')
    bot.answer_callback_query(c.id)

@bot.message_handler(func=lambda m: m.from_user and m.from_user.id in waiting_slug and m.text)
def slug_conversation(m):
    uid = m.from_user.id; state = waiting_slug[uid]; filename = state['name']
    slug = m.text.strip().lower()
    if not re.match(r'^[a-z0-9][a-z0-9\-]{0,48}[a-z0-9]$', slug):
        return safe_reply(m, "❌ Invalid slug (2-50 chars, letters/numbers/hyphens, no leading/trailing hyphen).\nTry again:", 'Markdown')
    if slug_exists(slug, uid, filename):
        return safe_reply(m, f"❌ Slug `{slug}` is taken. Try another:", 'Markdown')
    old_slug = site_slugs.get(uid, {}).get(filename)
    if old_slug and old_slug != slug:
        old_dir = os.path.join(SITES_DIR, old_slug)
        new_dir = os.path.join(SITES_DIR, slug)
        if os.path.exists(old_dir): shutil.move(old_dir, new_dir)
    save_slug(uid, filename, slug)
    del waiting_slug[uid]
    url = get_site_url(slug)
    mk  = types.InlineKeyboardMarkup()
    if url: mk.add(types.InlineKeyboardButton("🌐 Open Website", url=url))
    safe_reply(m, f"✅ *Slug set*\n`{slug}`\nURL: `{url or 'Set HOST_URL first'}`", 'Markdown', mk)

# ==================== FALLBACK ====================
@bot.message_handler(func=lambda m: True)
def fallback(m):
    pass

# ==================== CLEANUP ====================
def cleanup():
    for uid, info in list(shell_procs.items()):
        _kill_shell(uid)
    for info in scripts.values():
        if info.get('process') and info['process'].poll() is None:
            try: kill_process_tree(info['process'].pid)
            except: pass

atexit.register(cleanup)

# ==================== AUTO-BROADCAST ON START ====================
def broadcast_restart():
    time.sleep(3)
    try:
        marker = os.path.join(DB_DIR, 'restart_marker.json')
        if os.path.exists(marker):
            with open(marker, 'r') as f:
                data = json.load(f)
            os.remove(marker)
            try:
                safe_edit(data['chat_id'], data['msg_id'],
                          "✅ *Bot restarted successfully*\nAll data has been cleared.", 'Markdown')
            except: pass
    except: pass
    sent = 0
    for uid in list(active_users):
        try:
            bot.send_message(uid,
                "🔄 Bot Restarted\n\nAll previously running scripts have been cleared.\n"
                "Re-upload your files to run them again.")
            sent += 1; time.sleep(0.05)
        except: pass
    logger.info(f"Restart broadcast: {sent} users")

# ==================== MAIN ====================
if __name__ == "__main__":
    init_db()
    clear_old_data()
    load_data()
    keep_alive()

    print(f"\n{'='*50}")
    print(f"  HostingBot — by Blac (@NottBlac)")
    print(f"  Owner ID : {OWNER_ID}")
    print(f"  Platform : {HOST_URL or 'local'}")
    try: print(f"  Bot      : @{bot.get_me().username}")
    except: pass
    print(f"{'='*50}\n")

    logger.info(f"Started — Owner: {OWNER_ID} — Platform: {HOST_URL or 'local'}")

    threading.Thread(target=broadcast_restart, daemon=True).start()

    try: bot.send_chat_action(OWNER_ID, 'typing')
    except: pass

    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        logger.error(f"Fatal: {e}")
        sys.exit(1)