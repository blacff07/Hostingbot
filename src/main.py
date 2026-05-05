# -*- coding: utf-8 -*-
"""
HostingBot — by Blac (@blcqt)
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
OWNER_ID = int(os.getenv('OWNER_ID', '8760823326'))
ADMIN_ID = int(os.getenv('ADMIN_ID', '8760823326'))
OWNER_NAME = os.getenv('OWNER_NAME', 'Blac')
UPDATE_CHANNEL = os.getenv('UPDATE_CHANNEL', 'https://t.me/TechTipsCode')
SUPPORT_CHANNEL = os.getenv('SUPPORT_CHANNEL', 'https://t.me/EliteCodeLab')
OWNER_USERNAME = os.getenv('OWNER_USERNAME', 'https://t.me/blcqt')

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

app = Flask(__name__)

@app.route('/')
def home():
    return (f"<html><head><title>HostingBot</title></head>"
            "<body style='font-family:Arial;text-align:center;"
            "background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);"
            "color:white;padding:50px;'>"
            f"<h1>HostingBot</h1><p>by <b>{OWNER_NAME}</b> — Running</p></body></html>")

@app.route('/file/<uid>/<path:filename>')
def serve_file(uid, filename):
    user_dir = os.path.join(UPLOAD_DIR, str(uid))
    full_path = os.path.join(user_dir, filename)
    if not os.path.exists(full_path):
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
    t = threading.Thread(target=run_flask, daemon=True)
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
bot_start_time = datetime.now()

# ==================== DATA ====================
scripts         = {}
subscriptions   = {}
user_files      = {}
active_users    = set()
admins          = {ADMIN_ID, OWNER_ID}
pending         = {}
bot_locked      = False
shell_sessions  = {}
exec_locks      = {}
exec_locks_mutex = threading.Lock()
broadcast_pending = {}
user_envs       = {}
site_slugs      = {}
waiting_slug    = {}
waiting_env     = {}
banned_users    = set()
ctrl_active     = {}
alt_active      = {}

# ==================== SHELL STATE ====================
shell_procs = {}
shell_intro_msg = {}
shell_intro_text = {}
shell_active_msg = {}
shell_active_msg_text = {}
shell_last_prompt = {}
shell_chat_id = {}

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
    except psutil.NoSuchProcess: return True
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
export PYENV_ROOT="$HOME/.pyenv"
export NVM_DIR="$HOME/.nvm"
export LC_ALL=C.UTF-8

if [ -d "$PYENV_ROOT" ]; then
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"
fi

if [ -d "$NVM_DIR" ]; then
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
    [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"
    LATEST_NODE=$(nvm ls --no-colors 2>/dev/null | grep -o 'v[0-9]*\.[0-9]*\.[0-9]*' | tail -1)
    if [ -n "$LATEST_NODE" ]; then
        nvm use "$LATEST_NODE" > /dev/null 2>&1
        export PATH="$NVM_DIR/versions/node/$LATEST_NODE/bin:$PATH"
    fi
fi

alias python=python3
alias pip=pip3
'''.replace('{home}', home))

    pyenv_dir = os.path.join(home, '.pyenv')
    if not os.path.exists(pyenv_dir):
        subprocess.run(['git', 'clone', '--depth', '1', 'https://github.com/pyenv/pyenv.git', pyenv_dir],
                       capture_output=True, timeout=60)

    nvm_dir = os.path.join(home, '.nvm')
    nvm_script = os.path.join(nvm_dir, 'nvm.sh')
    if not os.path.exists(nvm_dir):
        subprocess.run(['git', 'clone', '--depth', '1', 'https://github.com/nvm-sh/nvm.git', nvm_dir],
                       capture_output=True, timeout=60)

    def _install_node():
        if os.path.exists(nvm_script):
            env = os.environ.copy()
            env['HOME'] = home
            env['NVM_DIR'] = nvm_dir
            try:
                subprocess.run(['bash', '-c',
                    f'source "{nvm_script}" && nvm install --lts --latest-npm && nvm alias default "lts/*" && nvm use default'],
                    capture_output=True, text=True, timeout=300, env=env)
            except: pass
    threading.Thread(target=_install_node, daemon=True).start()

    def _symlink_node():
        node_versions = os.path.join(nvm_dir, 'versions', 'node')
        if os.path.exists(node_versions):
            versions = sorted(os.listdir(node_versions), reverse=True)
            if versions:
                latest_node_bin = os.path.join(nvm_dir, 'versions', 'node', versions[0], 'bin')
                home_bin = os.path.join(home, 'bin')
                os.makedirs(home_bin, exist_ok=True)
                if os.path.exists(latest_node_bin):
                    for binary in os.listdir(latest_node_bin):
                        src = os.path.join(latest_node_bin, binary)
                        dst = os.path.join(home_bin, binary)
                        if not os.path.exists(dst):
                            try: os.symlink(src, dst)
                            except: pass
    threading.Thread(target=_symlink_node, daemon=True).start()

    return home

def get_user_env(uid, name=None):
    home = setup_user_home(uid)
    extra_paths = [os.path.join(home, 'bin'), os.path.join(home, '.pyenv', 'bin')]
    nvm_dir = os.path.join(home, '.nvm')
    node_versions = os.path.join(nvm_dir, 'versions', 'node')
    if os.path.exists(node_versions):
        versions = sorted(os.listdir(node_versions), reverse=True)
        if versions:
            latest_node_bin = os.path.join(node_versions, versions[0], 'bin')
            if os.path.exists(latest_node_bin):
                extra_paths.append(latest_node_bin)
    new_path = ':'.join(extra_paths + [os.environ.get('PATH', '/usr/bin:/bin:/usr/local/bin')])
    env = {
        'HOME': home,
        'PATH': new_path,
        'PYENV_ROOT': os.path.join(home, '.pyenv'),
        'NVM_DIR': os.path.join(home, '.nvm'),
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
    if tier == 'owner': return lambda: None
    ram_limit = TIER_RAM[tier]
    cpu_seconds = 3600
    if tier == 'free':      nproc=128; nofile=4096
    elif tier == 'premium': nproc=256; nofile=8192
    else:                   nproc=512; nofile=16384
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
    (re.compile(r'\beval\s*\('), 'eval()'),
    (re.compile(r'\bexec\s*\('), 'exec()'),
    (re.compile(r'\b__import__\s*\('), '__import__'),
    (re.compile(r'\bimportlib\b'), 'importlib'),
    (re.compile(r'\bcompile\s*\('), 'compile()'),
]

def _scan_content(content):
    cl = content.lower()
    for p in _DANGEROUS_STRINGS:
        if p.lower() in cl: return False, f"Blocked: `{p}`"
    for pattern, label in _DANGEROUS_REGEX:
        if pattern.search(content): return False, f"Blocked: `{label}`"
    return True, "Safe"

def check_malicious(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f: content = f.read()
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
                        if not ok: return False, f"In `{os.path.basename(name)}`: {reason}"
                    except: pass
        return True, "Safe"
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
            if not os.path.exists(python_bin): python_bin = sys.executable
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
                mod = imp[0] or imp[1]; pkg = pkg_map.get(mod)
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
                base = mod.split('/')[0]; pkg = node_map.get(base)
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

# ==================== ZIP HANDLERS ====================
def handle_zip_website(zip_path, uid, zip_name, msg=None):
    existing = site_slugs.get(uid, {}).get(zip_name)
    if existing: slug = existing
    else:
        base = os.path.splitext(zip_name)[0]
        slug = re.sub(r'[^a-z0-9\-]', '-', base.lower()).strip('-') or hashlib.md5(f"{uid}_{zip_name}".encode()).hexdigest()[:8]
        orig = slug; counter = 1
        while slug_exists(slug, uid, zip_name):
            slug = f"{orig}-{counter}"; counter += 1
        save_slug(uid, zip_name, slug)
    site_dir = os.path.join(SITES_DIR, slug)
    if os.path.exists(site_dir): shutil.rmtree(site_dir)
    os.makedirs(site_dir)
    with zipfile.ZipFile(zip_path, 'r') as zf: zf.extractall(site_dir)
    entries = os.listdir(site_dir)
    if len(entries) == 1 and os.path.isdir(os.path.join(site_dir, entries[0])):
        sub = os.path.join(site_dir, entries[0])
        for item in os.listdir(sub): shutil.move(os.path.join(sub, item), site_dir)
        os.rmdir(sub)
    url = get_site_url(slug)
    if msg:
        mk = types.InlineKeyboardMarkup()
        if url: mk.add(types.InlineKeyboardButton("🌐 Open Website", url=url))
        mk.add(types.InlineKeyboardButton("🔗 Set Custom Slug", callback_data=f"setslug_{uid}_{zip_name}"))
        safe_edit(msg.chat.id, msg.message_id, f"🌐 *Website Hosted*\n`{zip_name}`\n\nSlug: `{slug}`\nURL: `{url or 'Set HOST_URL env var'}`", 'Markdown', mk)
    return True, url or slug

def handle_zip(zip_path, uid, extract_to, msg=None, zip_name=None):
    try:
        os.makedirs(extract_to, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as zf: zf.extractall(extract_to)
        main_file = None
        priority = ['main.py','app.py','bot.py','run.py','index.py','server.py','index.js','main.js','app.js','server.js']
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
        inner_name = os.path.basename(main_file); inner_ext = os.path.splitext(main_file)[1].lower()
        key = f"{uid}_{zip_name}" if zip_name else f"{uid}_{inner_name}"
        return _do_execute(uid, main_file, msg, extract_to, inner_name, inner_ext, key, zip_name)
    except zipfile.BadZipFile: return False, "Invalid ZIP file"
    except Exception as e: return False, f"ZIP error: {e}"

# ==================== CRASH MONITOR ====================
def monitor_script(uid, key, name, process, log_path, msg_chat_id=None, msg_id=None):
    try:
        process.wait(); rc = process.returncode
        if key not in scripts: return
        if scripts[key].get('stopped_intentionally'): return
        scripts[key]['running'] = False; scripts[key]['code'] = rc
        if msg_chat_id and msg_id:
            try:
                mk = build_control_markup(uid, name, 'executable')
                if rc in (0, None): safe_edit(msg_chat_id, msg_id, f"✅ *Finished* — `{name}`\nExit: `{rc}`", 'Markdown', mk)
                else: safe_edit(msg_chat_id, msg_id, f"❌ *Crashed* — `{name}`\nExit: `{rc}`", 'Markdown', mk)
            except: pass
        if rc is not None and rc not in (0, -1, -9):
            snippet = _read_crash_snippet(key, log_path)
            text = f"⚠️ <b>Script Crashed</b>\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n📄 <code>{name}</code>\n❌ Exit code: <code>{rc}</code>"
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
        read_path = (stderr_path if stderr_path and os.path.exists(stderr_path) and os.path.getsize(stderr_path) > 0 else log_path)
        if not read_path or not os.path.exists(read_path): return ""
        with open(read_path, 'r', errors='ignore') as f: content = f.read()
        filtered = "\n".join([l for l in content.splitlines() if not re.match(r'^(INFO|DEBUG|WARNING):(httpx|urllib3|requests|telebot|apscheduler)', l) and 'HTTP Request:' not in l and 'HTTP/1.' not in l and 'getUpdates' not in l])
        tb = re.search(r'(Traceback \(most recent call last\).*)', filtered, re.DOTALL)
        if tb: return tb.group(1).strip()
        lines = filtered.splitlines()
        return "\n".join(lines[-30:] if len(lines) > 30 else lines).strip()
    except: return ""

def tail_stderr_for_tracebacks(uid, key, name, stderr_path, process):
    NOISE = re.compile(r'^(INFO|DEBUG|WARNING):(httpx|urllib3|requests|telebot|apscheduler)|HTTP Request:|HTTP/1\.|getUpdates')
    sent_hashes = {}; COOLDOWN = 60
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
                        rest = buffer[start:]; lines = rest.split('\n')
                        end_idx = None
                        for i, line in enumerate(lines[1:], 1):
                            if line and not line.startswith((' ', '\t')): end_idx = i + 1; break
                        if end_idx is None: break
                        tb_raw = '\n'.join(lines[:end_idx]).strip()
                        tb_clean = '\n'.join(l for l in tb_raw.splitlines() if not NOISE.search(l)).strip()
                        if tb_clean:
                            h = _hash(tb_clean); now = time.time()
                            if now - sent_hashes.get(h, 0) >= COOLDOWN:
                                sent_hashes[h] = now
                                snippet = tb_clean if len(tb_clean) <= 1500 else "..." + tb_clean[-1500:]
                                text = f"⚠️ <b>Runtime Error in {name}</b>\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n<pre>{snippet}</pre>"
                                try: safe_send(uid, text, parse='HTML')
                                except: pass
                        buffer = buffer[start + len('\n'.join(lines[:end_idx])):]
                else: time.sleep(0.5)
    except: pass

# ==================== SCRIPT EXECUTOR ====================
def execute_script(uid, file_path, msg=None, work_dir=None, zip_name=None):
    name = os.path.basename(file_path); ext = os.path.splitext(file_path)[1].lower()
    key = f"{uid}_{zip_name}" if zip_name else f"{uid}_{name}"
    with exec_locks_mutex:
        if exec_locks.get(key):
            if msg:
                try: safe_edit(msg.chat.id, msg.message_id, f"⚠️ `{zip_name or name}` is already being started", 'Markdown')
                except: pass
            return False, "Already starting"
        exec_locks[key] = True
    try: return _do_execute(uid, file_path, msg, work_dir, name, ext, key, zip_name)
    finally:
        with exec_locks_mutex: exec_locks.pop(key, None)

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
        return handle_zip(file_path, uid, os.path.join(EXTRACT_DIR, f"{uid}_{int(time.time())}"), msg, name)
    if ext not in LANG_MAP:
        if msg: safe_edit(msg.chat.id, msg.message_id, f"❌ Unsupported type: `{ext}`", 'Markdown')
        return False, "Unsupported"
    lang, icon = LANG_MAP[ext]; folder = get_user_folder(uid)
    try:
        if msg: safe_edit(msg.chat.id, msg.message_id, f"{icon} *{lang}* — `{display_name}`\n⚙️ Starting...", 'Markdown')
        installed = set(); deps, new = install_deps(file_path, ext, folder, uid, display_name); installed.update(new)
        if deps and msg:
            dep_text = "\n".join(deps[:4]) + (f"\n+{len(deps)-4} more" if len(deps) > 4 else "")
            safe_edit(msg.chat.id, msg.message_id, f"{icon} *{lang}* — `{display_name}`\n📦 Deps:\n{dep_text}", 'Markdown')
        env = get_user_env(uid, name)
        if ext in ('.py', '.pyw'):
            home = get_user_home(uid); python_bin = os.path.join(home, '.pyenv', 'shims', 'python')
            if not os.path.exists(python_bin): python_bin = sys.executable
            cmd = [python_bin, file_path]
        elif ext in ('.js', '.mjs', '.cjs'): cmd = ['node', file_path]
        elif ext == '.java':
            classname = os.path.splitext(name)[0]; compile_dir = os.path.join(TEMP_DIR, f"{uid}_{display_name}")
            os.makedirs(compile_dir, exist_ok=True)
            r = subprocess.run(['javac', '-d', compile_dir, file_path], capture_output=True, text=True, timeout=60, env=env)
            if r.returncode != 0:
                if msg: safe_edit(msg.chat.id, msg.message_id, f"❌ *Java compile failed*\n```\n{r.stderr[:400]}\n```", 'Markdown')
                return False, "Java compile failed"
            cmd = ['java', '-cp', compile_dir, classname]
        elif ext in ('.cpp', '.cc', '.cxx', '.c'):
            out = os.path.join(TEMP_DIR, f"{uid}_{display_name}.out"); comp = 'g++' if ext in ('.cpp', '.cc', '.cxx') else 'gcc'
            r = subprocess.run([comp, file_path, '-o', out], capture_output=True, text=True, timeout=60, env=env)
            if r.returncode != 0:
                if msg: safe_edit(msg.chat.id, msg.message_id, f"❌ *Compile failed*\n```\n{r.stderr[:400]}\n```", 'Markdown')
                return False, "Compile failed"
            cmd = [out]
        elif ext == '.go': cmd = ['go', 'run', file_path]
        elif ext == '.rs':
            out = os.path.join(TEMP_DIR, f"{uid}_{display_name}.out")
            r = subprocess.run(['rustc', file_path, '-o', out], capture_output=True, text=True, timeout=60, env=env)
            if r.returncode != 0:
                if msg: safe_edit(msg.chat.id, msg.message_id, f"❌ *Rust compile failed*\n```\n{r.stderr[:400]}\n```", 'Markdown')
                return False, "Rust compile failed"
            cmd = [out]
        elif ext == '.php': cmd = ['php', file_path]
        elif ext == '.rb': cmd = ['ruby', file_path]
        elif ext == '.lua': cmd = ['lua', file_path]
        elif ext in ('.sh', '.bash', '.zsh', '.fish'):
            os.chmod(file_path, 0o755); cmd = [ext.lstrip('.') if ext != '.sh' else 'bash', file_path]
        elif ext in ('.ts', '.tsx'):
            js = file_path.rsplit('.', 1)[0] + '.js'
            r = subprocess.run(['tsc', file_path, '--outDir', os.path.dirname(file_path)], capture_output=True, text=True, timeout=60, env=env)
            if r.returncode != 0:
                if msg: safe_edit(msg.chat.id, msg.message_id, f"❌ *TS compile failed*\n```\n{r.stderr[:400]}\n```", 'Markdown')
                return False, "TS compile failed"
            cmd = ['node', js]
        elif ext == '.ps1': cmd = ['powershell', '-File', file_path]
        elif ext in ('.bat', '.cmd'): cmd = [file_path]
        elif ext in ('.pl', '.pm'): cmd = ['perl', file_path]
        elif ext in ('.r', '.R'): cmd = ['Rscript', file_path]
        elif ext == '.swift': cmd = ['swift', file_path]
        elif ext == '.kt':
            jar = os.path.join(TEMP_DIR, f"{uid}_{display_name}.jar")
            r = subprocess.run(['kotlinc', file_path, '-include-runtime', '-d', jar], capture_output=True, text=True, timeout=120, env=env)
            if r.returncode != 0:
                if msg: safe_edit(msg.chat.id, msg.message_id, f"❌ *Kotlin compile failed*\n```\n{r.stderr[:400]}\n```", 'Markdown')
                return False, "Kotlin compile failed"
            cmd = ['java', '-jar', jar]
        elif ext == '.scala':
            compile_dir = os.path.join(TEMP_DIR, f"{uid}_{display_name}"); os.makedirs(compile_dir, exist_ok=True)
            r = subprocess.run(['scalac', '-d', compile_dir, file_path], capture_output=True, text=True, timeout=120, env=env)
            if r.returncode != 0:
                if msg: safe_edit(msg.chat.id, msg.message_id, f"❌ *Scala compile failed*\n```\n{r.stderr[:400]}\n```", 'Markdown')
                return False, "Scala compile failed"
            cmd = ['scala', '-cp', compile_dir, os.path.splitext(name)[0]]
        elif ext in ('.ex', '.exs'): cmd = ['elixir', file_path]
        elif ext == '.hs':
            out = os.path.join(TEMP_DIR, f"{uid}_{display_name}.out")
            r = subprocess.run(['ghc', file_path, '-o', out], capture_output=True, text=True, timeout=120, env=env)
            if r.returncode != 0:
                if msg: safe_edit(msg.chat.id, msg.message_id, f"❌ *Haskell compile failed*\n```\n{r.stderr[:400]}\n```", 'Markdown')
                return False, "Haskell compile failed"
            cmd = [out]
        else: cmd = [file_path]
        safe_name = re.sub(r'[^\w]', '_', display_name)
        log_path = os.path.join(LOGS_DIR, f"{uid}_{safe_name}.log"); stderr_path = os.path.join(LOGS_DIR, f"{uid}_{safe_name}.err")
        cwd = work_dir or os.path.dirname(file_path)
        for attempt in range(1, 11):
            if attempt > 1 and msg: safe_edit(msg.chat.id, msg.message_id, f"{icon} *{lang}* — `{display_name}`\n🔄 Retry {attempt}...", 'Markdown')
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=cwd, env=env, preexec_fn=resource_limits(uid))
                if res.returncode != 0 and "ModuleNotFoundError" in res.stderr:
                    match = re.search(r"No module named '(\w+)'", res.stderr)
                    if match:
                        mod = match.group(1)
                        aliases = {'telethon':'telethon','cryptg':'cryptg','telebot':'pyTelegramBotAPI','telegram':'python-telegram-bot','cv2':'opencv-python','PIL':'Pillow','bs4':'beautifulsoup4','yaml':'pyyaml','dotenv':'python-dotenv','flask':'flask','django':'django','requests':'requests','numpy':'numpy','pandas':'pandas','aiohttp':'aiohttp','fastapi':'fastapi','tgcalls':'py-tgcalls','py_tgcalls':'py-tgcalls'}
                        pkg = aliases.get(mod, mod)
                        if pkg not in installed:
                            if msg: safe_edit(msg.chat.id, msg.message_id, f"{icon} *{lang}* — `{display_name}`\n📦 Installing `{pkg}`...", 'Markdown')
                            home = get_user_home(uid); python_bin = os.path.join(home, '.pyenv', 'shims', 'python')
                            if not os.path.exists(python_bin): python_bin = sys.executable
                            subprocess.run([python_bin, '-m', 'pip', 'install', '--quiet', pkg], capture_output=True, text=True, timeout=60, env=env)
                            installed.add(pkg); continue
                with open(log_path, 'w') as lf:
                    if res.stdout: lf.write(res.stdout)
                    if res.stderr: lf.write(res.stderr)
                    lf.write(f"\nExit: {res.returncode}")
                with open(stderr_path, 'w') as ef:
                    if res.stderr: ef.write(res.stderr)
                scripts[key] = {'process': None, 'key': key, 'uid': uid, 'name': display_name, 'start': datetime.now(), 'log': log_path, 'stderr_log': stderr_path, 'lang': lang, 'icon': icon, 'running': False, 'code': res.returncode}
                if msg:
                    mk = build_control_markup(uid, display_name, 'executable')
                    if res.returncode == 0: safe_edit(msg.chat.id, msg.message_id, f"✅ *{lang}* — `{display_name}`\nExit: `0`", 'Markdown', mk)
                    else:
                        snippet = extract_error_snippet(res.stderr, res.stdout)
                        err_text = f"❌ *{lang}* — `{display_name}`\nExit: `{res.returncode}`"
                        if snippet: err_text += f"\n\n```\n{snippet}\n```"
                        safe_edit(msg.chat.id, msg.message_id, err_text, 'Markdown', mk)
                return True, f"Exit {res.returncode}"
            except subprocess.TimeoutExpired:
                with open(log_path, 'w') as lf, open(stderr_path, 'w') as ef:
                    p = subprocess.Popen(cmd, stdout=lf, stderr=ef, cwd=cwd, env=env, preexec_fn=resource_limits(uid))
                scripts[key] = {'process': p, 'key': key, 'uid': uid, 'name': display_name, 'start': datetime.now(), 'log': log_path, 'stderr_log': stderr_path, 'lang': lang, 'icon': icon, 'running': True, 'code': None}
                msg_chat_id = msg.chat.id if msg else None; msg_id_val = msg.message_id if msg else None
                threading.Thread(target=monitor_script, args=(uid, key, display_name, p, log_path, msg_chat_id, msg_id_val), daemon=True).start()
                threading.Thread(target=tail_stderr_for_tracebacks, args=(uid, key, display_name, stderr_path, p), daemon=True).start()
                if msg:
                    mk = build_control_markup(uid, display_name, 'executable')
                    safe_edit(msg.chat.id, msg.message_id, f"🔄 *{lang}* — `{display_name}`\nPID: `{p.pid}`", 'Markdown', mk)
                return True, f"Background PID {p.pid}"
        return False, "Max retries exceeded"
    except Exception as e:
        logger.error(f"Exec error {key}: {e}", exc_info=True)
        if msg:
            try: safe_edit(msg.chat.id, msg.message_id, f"❌ Error: `{str(e)[:200]}`", 'Markdown')
            except: pass
        return False, str(e)

# ==================== SHELL (TRUE PTY WITH STREAMING) ====================
def _is_prompt_line(line):
    """Match root prompt like root@container:~#"""
    if not line: return False
    return bool(re.search(r'^[^\n]*[@][^\n]+:[^\n]+[#]\s*$', line.strip()))

def _kill_shell(uid):
    info = shell_procs.pop(uid, None)
    if info:
        try: os.close(info['fd'])
        except: pass
        try: os.kill(info['pid'], 9)
        except: pass

def _get_clean_pty_output(info, clear_buffer=True):
    with info['lock']:
        if not info['output_buffer']: return ""
        data = bytes(info['output_buffer'])
        if clear_buffer: info['output_buffer'].clear()
    text = data.decode('utf-8', errors='replace')
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    text = ansi_escape.sub('', text)
    text = re.sub(r'\x1b\[\?2004[hl]', '', text)
    return text

def _get_or_create_shell(uid):
    info = shell_procs.get(uid)
    if info and info.get('fd') is not None:
        try: os.kill(info['pid'], 0); return info
        except OSError: _kill_shell(uid); info = None
    home = setup_user_home(uid)
    env = get_user_env(uid)
    env['PS1'] = 'root@container:~# '    # force root prompt
    master_fd, slave_fd = pty.openpty()
    try:
        winsize = struct.pack("HHHH", 80, 24, 0, 0)
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
    except: pass
    pid = os.fork()
    if pid == 0:
        os.setsid(); os.close(master_fd)
        try: fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
        except: pass
        os.dup2(slave_fd, 0); os.dup2(slave_fd, 1); os.dup2(slave_fd, 2); os.close(slave_fd)
        resource_limits(uid)(); os.chdir(home)
        os.execvpe('bash', ['bash', '--noprofile', '--norc'], env)
        os._exit(1)
    os.close(slave_fd)
    info = {'pid': pid, 'fd': master_fd, 'home': home, 'lock': threading.Lock(), 'output_buffer': bytearray(), 'chat_id': None}
    shell_procs[uid] = info
    def reader():
        fd = info['fd']
        while True:
            try:
                r, _, _ = select.select([fd], [], [], 1.0)
                if r:
                    data = os.read(fd, 4096)
                    if not data: break
                    with info['lock']: info['output_buffer'].extend(data)
            except: break
    threading.Thread(target=reader, daemon=True).start()
    return info

def _format_shell_output(command, raw_output):
    """Plain command header + separator + raw terminal output. No `$`."""
    separator = "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄"
    MAX_MSG_LEN = 4096
    header = command
    base = f"{header}\n{separator}\n{raw_output}"
    if len(base) <= MAX_MSG_LEN: return base
    overhead = len(header) + len(separator) + 3
    truncated = raw_output[-(MAX_MSG_LEN-overhead-3):]
    return f"{header}\n{separator}\n... (truncated)\n{truncated}"

def build_shell_keyboard(uid):
    mk = types.InlineKeyboardMarkup(row_width=3)
    ctrl_text = "Ctrl ✓" if ctrl_active.get(uid, False) else "Ctrl"
    alt_text = "Alt ✓" if alt_active.get(uid, False) else "Alt"
    mk.row(
        types.InlineKeyboardButton("Esc", callback_data=f"shell_esc_{uid}"),
        types.InlineKeyboardButton(alt_text, callback_data=f"shell_alt_{uid}"),
        types.InlineKeyboardButton(ctrl_text, callback_data=f"shell_ctrl_{uid}")
    )
    mk.row(
        types.InlineKeyboardButton("↑", callback_data=f"shell_up_{uid}"),
        types.InlineKeyboardButton("↓", callback_data=f"shell_down_{uid}"),
        types.InlineKeyboardButton("Enter", callback_data=f"shell_enter_{uid}"),
        types.InlineKeyboardButton("❌ Exit", callback_data=f"shell_exit_{uid}")
    )
    return mk

def _update_prompt_line(uid, new_prompt):
    """Edit only the last line of the active shell message, preserving buttons."""
    chat_id = shell_chat_id.get(uid)
    if not chat_id: return
    active = shell_active_msg.get(uid)
    if not active and uid in shell_intro_msg: active = shell_intro_msg[uid]
    if not active: return
    text = shell_active_msg_text.get(uid, "")
    if not text: return
    lines = text.split('\n')
    if lines:
        lines[-1] = new_prompt
    shell_active_msg_text[uid] = '\n'.join(lines)
    mk = build_shell_keyboard(uid)
    try: bot.edit_message_text('\n'.join(lines), chat_id, active, parse_mode='', reply_markup=mk)
    except: pass

def _remove_buttons(chat_id, msg_id):
    try: bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=None)
    except: pass

def _send_shell_output(uid, command, raw_output, chat_id):
    """Send output message, handle previous buttons, track active message."""
    is_exit = command.strip().lower() in ('exit', 'quit', 'q')
    if is_exit:
        raw_output += "\n\n⚙ *Shell Session Ended*"
        mk = None
    else:
        mk = build_shell_keyboard(uid)
    formatted = _format_shell_output(command, raw_output)
    sent = safe_send(chat_id, formatted, parse='', markup=mk)
    prev_active = shell_active_msg.get(uid)
    if prev_active: _remove_buttons(chat_id, prev_active)
    is_first = (uid in shell_intro_msg and shell_intro_msg[uid] is not None)
    if is_first:
        if shell_intro_msg[uid]:
            _remove_buttons(chat_id, shell_intro_msg[uid])
            shell_intro_msg[uid] = None
    shell_active_msg[uid] = sent.message_id
    shell_active_msg_text[uid] = formatted
    shell_chat_id[uid] = chat_id
    if is_exit:
        _kill_shell(uid)
        for k in ['sessions', 'ctrl_active', 'alt_active', 'intro_msg', 'intro_text', 'active_msg', 'active_msg_text', 'last_prompt', 'chat_id']:
            globals()[f'shell_{k}'].pop(uid, None)
    return sent

def _execute_shell_command(uid, command, chat_id):
    """Streaming engine: send command, keep editing message until prompt appears."""
    info = _get_or_create_shell(uid)
    if not info:
        safe_send(chat_id, "❌ Shell not active.")
        return
    fd = info['fd']
    _get_clean_pty_output(info, clear_buffer=True)
    os.write(fd, (command + '\n').encode())

    output = ""
    sent_msg = None
    start_time = time.time()

    while True:
        chunk = _get_clean_pty_output(info, clear_buffer=True)
        if chunk:
            output += chunk
            if "\x03" in chunk: output += "\n"   # Ctrl+C visual

            formatted = _format_shell_output(command, output.strip())
            if not sent_msg:
                is_exit = command.strip().lower() in ('exit', 'quit', 'q')
                mk = None if is_exit else build_shell_keyboard(uid)
                sent_msg = safe_send(chat_id, formatted, parse='', markup=mk)
                if is_exit:
                    _kill_shell(uid); shell_sessions.pop(uid, None)
                    return
            else:
                try: safe_edit(chat_id, sent_msg.message_id, formatted)
                except: pass

        # Stop when prompt line appears (e.g., root@container:~# )
        lines = output.splitlines()
        if lines and _is_prompt_line(lines[-1]):
            break
        if time.time() - start_time > 120:   # timeout for long commands
            break
        time.sleep(0.1)

    # Update state
    prev_active = shell_active_msg.get(uid)
    if prev_active: _remove_buttons(chat_id, prev_active)
    shell_active_msg[uid] = sent_msg.message_id
    shell_active_msg_text[uid] = _format_shell_output(command, output.strip())
    shell_chat_id[uid] = chat_id
    shell_last_prompt[uid] = lines[-1] if lines else "root@container:~#"

def start_interactive_shell(uid, chat_id):
    shell_sessions[uid] = True
    ctrl_active[uid] = False; alt_active[uid] = False
    if uid in shell_intro_msg and shell_intro_msg[uid]:
        try: bot.delete_message(chat_id, shell_intro_msg[uid])
        except: pass
    info = _get_or_create_shell(uid)
    info['chat_id'] = chat_id; shell_chat_id[uid] = chat_id
    intro = (
        "💻 *Private VPS Shell*\n\n"
        "Your environment includes:\n"
        "• `pyenv` – manage Python versions\n"
        "• `nvm`  – manage Node.js versions\n"
        "• `exit` – close the shell\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        "root@container:~#"
    )
    mk = build_shell_keyboard(uid)
    sent = safe_send(chat_id, intro, parse='Markdown', markup=mk)
    shell_intro_msg[uid] = sent.message_id
    shell_intro_text[uid] = intro
    shell_last_prompt[uid] = "root@container:~#"
    shell_active_msg[uid] = None

# ==================== SHELL HANDLERS ====================
def encode_keys(uid, text):
    ctrl = ctrl_active.get(uid, False); alt = alt_active.get(uid, False)
    result = bytearray()
    for k in [x.strip() for x in text.split('+')]:
        if not k: continue
        if ctrl and len(k) == 1: result.append(ord(k.upper())-64)
        elif alt and len(k) == 1: result.extend(b'\x1b'+k.lower().encode())
        else: result.extend(k.encode())
    return bytes(result)

@bot.message_handler(commands=['shell'])
def cmd_shell(message):
    uid = message.from_user.id
    parts = message.text.strip().split(' ', 1)
    if len(parts) > 1 and parts[1].strip():
        cmd_text = parts[1].strip()
        info = _get_or_create_shell(uid)
        os.write(info['fd'], (cmd_text+'\n').encode())
        time.sleep(0.5)
        output = _get_clean_pty_output(info, clear_buffer=True)
        lines = output.splitlines()
        safe_reply(message, _format_shell_output(cmd_text, output.strip()), parse='')
        return
    start_interactive_shell(uid, message.chat.id)

@bot.message_handler(func=lambda m: m.text == "💻 Shell")
def btn_shell(m):
    if not require_join(m): return
    start_interactive_shell(m.from_user.id, m.chat.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith('shell_'))
def shell_button_handler(c):
    uid = int(c.data.split('_')[2])
    if c.from_user.id != uid: return bot.answer_callback_query(c.id, "Access denied")
    action = c.data.split('_')[1]
    info = shell_procs.get(uid)
    if not info: bot.answer_callback_query(c.id, "Shell not active"); return
    if action == "ctrl":
        ctrl_active[uid] = not ctrl_active.get(uid, False)
        active = shell_active_msg.get(uid) or shell_intro_msg.get(uid)
        if active:
            try: bot.edit_message_reply_markup(c.message.chat.id, active, reply_markup=build_shell_keyboard(uid))
            except: pass
        bot.answer_callback_query(c.id); return
    if action == "alt":
        alt_active[uid] = not alt_active.get(uid, False)
        active = shell_active_msg.get(uid) or shell_intro_msg.get(uid)
        if active:
            try: bot.edit_message_reply_markup(c.message.chat.id, active, reply_markup=build_shell_keyboard(uid))
            except: pass
        bot.answer_callback_query(c.id); return
    if action == "esc": os.write(info['fd'], b'\x1b')
    elif action in ("up", "down"):
        os.write(info['fd'], b'\x1b[A' if action == "up" else b'\x1b[B')
        time.sleep(0.2)
        new_output = _get_clean_pty_output(info, clear_buffer=True)
        last_line = new_output.splitlines()[-1] if new_output else ""
        if last_line.strip():
            shell_last_prompt[uid] = last_line
            _update_prompt_line(uid, last_line)
    elif action == "enter":
        os.write(info['fd'], b'\n')
        time.sleep(0.3)
        output = _get_clean_pty_output(info, clear_buffer=True)
        if output:
            cmd_line = output.splitlines()[0] if output.splitlines() else ""
            _send_shell_output(uid, cmd_line.strip(), output.strip(), c.message.chat.id)
    elif action == "exit":
        os.write(info['fd'], b'exit\n')
        time.sleep(0.5)
        final = _get_clean_pty_output(info, clear_buffer=True)
        active = shell_active_msg.get(uid) or shell_intro_msg.get(uid)
        if active:
            _remove_buttons(c.message.chat.id, active)
            current = shell_active_msg_text.get(uid) or shell_intro_text.get(uid, "")
            new_text = current.rstrip() + "\n\n⚙ *Shell Session Ended*"
            try: bot.edit_message_text(new_text, c.message.chat.id, active, parse_mode='Markdown')
            except: pass
        _kill_shell(uid)
        for k in ['sessions','ctrl_active','alt_active','intro_msg','intro_text','active_msg','active_msg_text','last_prompt','chat_id']:
            globals()[f'shell_{k}'].pop(uid, None)
        bot.answer_callback_query(c.id, "Shell closed"); return
    bot.answer_callback_query(c.id)

@bot.message_handler(func=lambda m: m.from_user and shell_sessions.get(m.from_user.id) and m.text)
def shell_session_input(m):
    if not require_join(m): return
    uid = m.from_user.id
    text = m.text.strip()
    MAIN_MENU_BUTTONS = {
        "📂 Files", "👤 Profile", "📊 Stats", "❓ Help",
        "📢 Channel", "📞 Contact", "💻 Shell", "🤖 Clone",
        "🔧 Env Vars", "🌐 GitHub",
        "🟢 Running", "💳 Subs", "⏳ Pending", "🤖 Clones",
        "👑 Admin", "🔒 Lock", "📁 All Files", "📜 Bot Logs"
    }
    if text in MAIN_MENU_BUTTONS or text.startswith('/') or uid in waiting_env or uid in waiting_slug:
        return False

    info = _get_or_create_shell(uid)
    if ctrl_active.get(uid) or alt_active.get(uid):
        data = encode_keys(uid, text)
        os.write(info['fd'], data)
        ctrl_active[uid] = False; alt_active[uid] = False
        active = shell_active_msg.get(uid) or shell_intro_msg.get(uid)
        if active:
            try: bot.edit_message_reply_markup(m.chat.id, active, reply_markup=build_shell_keyboard(uid))
            except: pass
    else:
        # Raw input for interactive programs
        os.write(info['fd'], (text + '\n').encode())
        # Wait a bit then show output in a new message
        time.sleep(0.3)
        output = _get_clean_pty_output(info, clear_buffer=True)
        if output:
            lines = output.splitlines()
            prompt = lines[-1] if lines and _is_prompt_line(lines[-1]) else shell_last_prompt.get(uid, "root@container:~#")
            shell_last_prompt[uid] = prompt
            _send_shell_output(uid, text, output.strip(), m.chat.id)
    return True

return True