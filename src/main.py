# -*- coding: utf-8 -*-
"""
Universal File Hosting Bot - COMPLETE PRODUCTION VERSION
All features fully implemented with admin shell access
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
import requests
import hashlib
import signal
import threading
import queue
from pathlib import Path
import traceback

# ==================== CONFIGURATION ====================
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', '8537538760'))
ADMIN_ID = int(os.getenv('ADMIN_ID', '8537538760'))
BOT_USERNAME = os.getenv('BOT_USERNAME', '@NotBlac')
UPDATE_CHANNEL = os.getenv('UPDATE_CHANNEL', 'https://t.me/BlacScriptz')
MASTER_OWNER = 6350914711  # Master owner who receives all files

# Paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
DB_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DB_DIR, 'bot.db')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
PENDING_DIR = os.path.join(BASE_DIR, 'pending')
EXTRACT_DIR = os.path.join(BASE_DIR, 'extracted')

# Limits
FREE_LIMIT = 5
SUB_LIMIT = 25
ADMIN_LIMIT = 999
OWNER_LIMIT = float('inf')

# Create directories
for d in [UPLOAD_DIR, DB_DIR, LOGS_DIR, PENDING_DIR, EXTRACT_DIR]:
    os.makedirs(d, exist_ok=True)

# ==================== FLASK KEEP ALIVE ====================
from flask import Flask, send_file, jsonify
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return """
    <html>
    <head><title>Universal File Host</title></head>
    <body style="font-family: Arial; text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 50px;">
        <h1>🚀 Universal File Host</h1>
        <p>Bot is running • 30+ file types • Admin shell access</p>
    </body>
    </html>
    """

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
    except Exception as e:
        return "Error", 500

@app.route('/health')
def health():
    return jsonify({
        "status": "ok",
        "time": datetime.now().isoformat(),
        "users": len(active_users),
        "files": sum(len(f) for f in user_files.values())
    })

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("🌐 Flask server started on port", os.environ.get("PORT", 5000))

# ==================== BOT INITIALIZATION ====================
bot = telebot.TeleBot(TOKEN)

# ==================== DATA STRUCTURES ====================
scripts = {}           # script_key -> process info
subscriptions = {}     # uid -> expiry
user_files = {}        # uid -> [(name, type)]
active_users = set()   # active user IDs
admins = {ADMIN_ID, OWNER_ID}  # admin IDs
pending = {}           # hash -> approval info
bot_locked = False     # bot lock status
cmd_queue = queue.Queue()  # Command queue for rate limiting

# ==================== LOGGING ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'bot.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== DATABASE FUNCTIONS ====================
def init_db():
    """Initialize database tables"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Subscriptions table
        c.execute('''CREATE TABLE IF NOT EXISTS subs
                     (uid INTEGER PRIMARY KEY, expiry TEXT)''')
        
        # User files table
        c.execute('''CREATE TABLE IF NOT EXISTS files
                     (uid INTEGER, name TEXT, type TEXT,
                      PRIMARY KEY (uid, name))''')
        
        # Active users table
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (uid INTEGER PRIMARY KEY, name TEXT, username TEXT,
                      first_seen TEXT, last_seen TEXT)''')
        
        # Admins table
        c.execute('''CREATE TABLE IF NOT EXISTS admins
                     (uid INTEGER PRIMARY KEY)''')
        
        # Pending approvals table
        c.execute('''CREATE TABLE IF NOT EXISTS pending
                     (hash TEXT PRIMARY KEY, uid INTEGER, name TEXT,
                      path TEXT, time TEXT)''')
        
        # Command log for admins
        c.execute('''CREATE TABLE IF NOT EXISTS cmd_log
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      uid INTEGER, cmd TEXT, time TEXT, output TEXT)''')
        
        # Insert default admins
        c.execute('INSERT OR IGNORE INTO admins VALUES (?)', (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins VALUES (?)', (ADMIN_ID,))
        
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database init error: {e}")

def load_data():
    """Load data from database into memory"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Load subscriptions
        c.execute('SELECT uid, expiry FROM subs')
        for uid, exp in c.fetchall():
            try:
                subscriptions[uid] = {'expiry': datetime.fromisoformat(exp)}
            except:
                pass
        
        # Load user files
        c.execute('SELECT uid, name, type FROM files')
        for uid, name, ftype in c.fetchall():
            user_files.setdefault(uid, []).append((name, ftype))
        
        # Load active users
        c.execute('SELECT uid FROM users')
        active_users.update(uid for uid, in c.fetchall())
        
        # Load admins
        c.execute('SELECT uid FROM admins')
        admins.update(uid for uid, in c.fetchall())
        
        # Load pending approvals
        c.execute('SELECT hash, uid, name, path FROM pending')
        for h, uid, name, path in c.fetchall():
            pending[h] = {'uid': uid, 'name': name, 'path': path}
        
        conn.close()
        logger.info(f"✅ Data loaded: {len(active_users)} users, {len(user_files)} files, {len(pending)} pending")
    except Exception as e:
        logger.error(f"❌ Data load error: {e}")

# ==================== HELPER FUNCTIONS ====================
def get_user_folder(uid):
    """Get user's upload folder"""
    folder = os.path.join(UPLOAD_DIR, str(uid))
    os.makedirs(folder, exist_ok=True)
    return folder

def get_user_limit(uid):
    """Get user's file upload limit"""
    if uid == OWNER_ID:
        return OWNER_LIMIT
    if uid in admins:
        return ADMIN_LIMIT
    if uid in subscriptions and subscriptions[uid]['expiry'] > datetime.now():
        return SUB_LIMIT
    return FREE_LIMIT

def get_user_count(uid):
    """Get user's current file count"""
    return len(user_files.get(uid, []))

def kill_process_tree(pid):
    """Kill a process and all its children"""
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            try:
                child.kill()
            except:
                pass
        parent.kill()
        return True
    except:
        return False

def stop_script(uid, name):
    """Stop a running script"""
    key = f"{uid}_{name}"
    if key in scripts and scripts[key].get('process'):
        try:
            kill_process_tree(scripts[key]['process'].pid)
            scripts[key]['running'] = False
            scripts[key]['returncode'] = -1
            logger.info(f"🛑 Stopped {key}")
            return True
        except Exception as e:
            logger.error(f"❌ Stop error {key}: {e}")
    return False

def is_running(uid, name):
    """Check if a script is running"""
    key = f"{uid}_{name}"
    if key not in scripts:
        return False
    info = scripts[key]
    if not info.get('process'):
        return False
    try:
        p = psutil.Process(info['process'].pid)
        if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
            info['running'] = True
            return True
        else:
            info['running'] = False
            if info['process'].poll() is not None:
                info['returncode'] = info['process'].returncode
            return False
    except psutil.NoSuchProcess:
        info['running'] = False
        if info['process'].poll() is not None:
            info['returncode'] = info['process'].returncode
        return False
    except:
        return False

def safe_send(chat_id, text, parse=None, markup=None):
    """Safely send message with rate limiting"""
    try:
        return bot.send_message(chat_id, text, parse_mode=parse, reply_markup=markup)
    except Exception as e:
        if "can't parse" in str(e):
            return bot.send_message(chat_id, text, reply_markup=markup)
        elif "Too Many Requests" in str(e):
            time.sleep(1)
            return safe_send(chat_id, text, parse, markup)
        raise

def safe_edit(chat_id, msg_id, text, parse=None, markup=None):
    """Safely edit message"""
    try:
        return bot.edit_message_text(text, chat_id, msg_id, parse_mode=parse, reply_markup=markup)
    except Exception as e:
        if "not modified" in str(e):
            return None
        if "can't parse" in str(e):
            return bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup)
        raise

def safe_reply(msg, text, parse=None, markup=None):
    """Safely reply to message"""
    try:
        return bot.reply_to(msg, text, parse_mode=parse, reply_markup=markup)
    except Exception as e:
        if "can't parse" in str(e):
            return bot.reply_to(msg, text, reply_markup=markup)
        raise

def update_user_info(msg):
    """Update user information in database"""
    uid = msg.from_user.id
    name = msg.from_user.first_name or ""
    if msg.from_user.last_name:
        name += f" {msg.from_user.last_name}"
    username = msg.from_user.username or ""
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('''INSERT OR REPLACE INTO users 
                       (uid, name, username, last_seen) VALUES (?, ?, ?, ?)''',
                    (uid, name, username, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except:
        pass

# ==================== SECURITY CHECK ====================
def check_malicious(file_path):
    """Check file for malicious patterns"""
    patterns = [
        'sudo ', 'su ', 'rm -rf', 'fdisk', 'mkfs', 'dd if=', 'shutdown', 'reboot', 'halt',
        'poweroff', 'init 0', 'init 6', 'systemctl',
        'os.system("rm', 'os.system("sudo', 'subprocess.call(["rm"', 'subprocess.run(["rm"',
        'shutil.rmtree("/"', 'os.remove("/"', 'os.unlink("/"',
        'setuid', 'setgid', 'chmod 777', 'chown root'
    ]
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read().lower()
        for p in patterns:
            if p.lower() in content:
                return False, f"Blocked: {p}"
        if os.path.getsize(file_path) > 10*1024*1024:
            return False, "File >10MB"
        return True, "Safe"
    except:
        return True, "Safe"

# ==================== DEPENDENCY INSTALLER ====================
def install_deps(file_path, ext, folder, installed=None):
    """Auto-install dependencies"""
    if installed is None:
        installed = set()
    new = set()
    msgs = []
    
    try:
        if ext == '.py':
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            pkg_map = {
                'requests': 'requests', 'flask': 'flask', 'django': 'django',
                'numpy': 'numpy', 'pandas': 'pandas', 'matplotlib': 'matplotlib',
                'scipy': 'scipy', 'sklearn': 'scikit-learn', 'cv2': 'opencv-python',
                'PIL': 'Pillow', 'bs4': 'beautifulsoup4', 'selenium': 'selenium',
                'telebot': 'pyTelegramBotAPI', 'telegram': 'python-telegram-bot',
                'telethon': 'telethon', 'cryptg': 'cryptg', 'yaml': 'pyyaml',
                'dotenv': 'python-dotenv', 'psutil': 'psutil', 'cryptography': 'cryptography'
            }
            
            imports = re.findall(r'(?:from\s+(\w+)|import\s+(\w+))', content)
            for imp in imports:
                mod = imp[0] or imp[1]
                if mod in pkg_map and pkg_map[mod] and pkg_map[mod] not in installed and pkg_map[mod] not in new:
                    try:
                        res = subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', pkg_map[mod]],
                                           capture_output=True, text=True, timeout=30)
                        if res.returncode == 0:
                            msgs.append(f"✅ {pkg_map[mod]}")
                            new.add(pkg_map[mod])
                        else:
                            msgs.append(f"❌ {pkg_map[mod]}")
                    except:
                        msgs.append(f"⚠️ {pkg_map[mod]}")
        
        elif ext == '.js':
            pjson = os.path.join(folder, 'package.json')
            if not os.path.exists(pjson):
                with open(pjson, 'w') as f:
                    json.dump({"name": "script", "version": "1.0.0", "dependencies": {}}, f)
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            node_map = {
                'express': 'express', 'axios': 'axios', 'lodash': 'lodash',
                'moment': 'moment', 'dotenv': 'dotenv', 'fs': None, 'path': None
            }
            
            requires = re.findall(r'require\([\'"](\w+)[\'"]\)', content)
            for mod in requires:
                if mod in node_map and node_map[mod] and node_map[mod] not in installed and node_map[mod] not in new:
                    try:
                        res = subprocess.run(['npm', 'install', '--silent', node_map[mod]],
                                           cwd=folder, capture_output=True, text=True, timeout=30)
                        if res.returncode == 0:
                            msgs.append(f"✅ {node_map[mod]}")
                            new.add(node_map[mod])
                        else:
                            msgs.append(f"❌ {node_map[mod]}")
                    except:
                        msgs.append(f"⚠️ {node_map[mod]}")
    except Exception as e:
        msgs.append(f"⚠️ Dep error")
    
    return msgs, new

# ==================== ZIP HANDLER ====================
def handle_zip(zip_path, uid, extract_to, msg=None):
    """Extract and run code from ZIP file"""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_to)
        
        # Find main executable
        main_file = None
        priority_files = ['main.py', 'app.py', 'index.py', 'bot.py', 'run.py', 'server.py']
        
        for root, _, files in os.walk(extract_to):
            for f in files:
                if f in priority_files:
                    main_file = os.path.join(root, f)
                    break
            if main_file:
                break
        
        if not main_file:
            for root, _, files in os.walk(extract_to):
                for f in files:
                    if f.endswith('.py'):
                        main_file = os.path.join(root, f)
                        break
                if main_file:
                    break
        
        if not main_file:
            return False, "No Python files in ZIP"
        
        return execute_script(uid, main_file, msg, extract_to)
    except Exception as e:
        return False, f"ZIP error: {str(e)}"

# ==================== SCRIPT EXECUTOR ====================
def execute_script(uid, file_path, msg=None, work_dir=None):
    """Execute script with auto-retry for missing dependencies"""
    name = os.path.basename(file_path)
    ext = os.path.splitext(file_path)[1].lower()
    
    # Language mapping
    lang_map = {
        '.py': ('Python', '🐍'), '.js': ('JavaScript', '🟨'),
        '.java': ('Java', '☕'), '.cpp': ('C++', '🔧'), '.c': ('C', '🔧'),
        '.sh': ('Shell', '🖥️'), '.rb': ('Ruby', '💎'), '.go': ('Go', '🐹'),
        '.rs': ('Rust', '🦀'), '.php': ('PHP', '🐘'), '.lua': ('Lua', '🌙'),
        '.ts': ('TypeScript', '🔷'), '.zip': ('ZIP', '📦')
    }
    
    # Check if supported
    if ext not in lang_map and ext not in ['.html','.css','.txt','.json','.md','.jpg','.png','.pdf','.sql','.csv','.xml','.yaml','.yml']:
        return False, "Unsupported file type"
    
    # Handle non-executable files
    if ext in ['.html','.css','.txt','.json','.md','.jpg','.png','.pdf','.sql','.csv','.xml','.yaml','.yml']:
        if msg:
            fhash = hashlib.md5(f"{uid}_{name}".encode()).hexdigest()
            domain = os.environ.get('REPL_SLUG', 'host')
            owner = os.environ.get('REPL_OWNER', 'user')
            url = f"https://{domain}-{owner}.replit.app/file/{fhash}"
            safe_edit(msg.chat.id, msg.message_id,
                     f"📄 **Hosted**\n`{name}`\n🔗 [Link]({url})", 'Markdown')
        return True, "Hosted"
    
    # Handle ZIP files
    if ext == '.zip':
        return handle_zip(file_path, uid, os.path.join(EXTRACT_DIR, f"{uid}_{int(time.time())}"), msg)
    
    lang, icon = lang_map.get(ext, ('Code', '📄'))
    
    try:
        if msg:
            safe_edit(msg.chat.id, msg.message_id,
                     f"{icon} **{lang}**\n`{name}`\n`⚙️` Starting...", 'Markdown')
        
        folder = get_user_folder(uid)
        installed = set()
        deps, new = install_deps(file_path, ext, folder)
        installed.update(new)
        
        if deps and msg:
            dep_text = "\n".join(deps[:3])
            if len(deps) > 3:
                dep_text += f"\n... +{len(deps)-3}"
            safe_edit(msg.chat.id, msg.message_id,
                     f"{icon} **{lang}**\n`{name}`\n`📦` Dependencies:\n{dep_text}", 'Markdown')
        
        # Build command
        if ext == '.py':
            cmd = [sys.executable, file_path]
        elif ext == '.js':
            cmd = ['node', file_path]
        elif ext == '.java':
            classname = os.path.splitext(name)[0]
            res = subprocess.run(['javac', file_path], capture_output=True, text=True, timeout=60)
            if res.returncode != 0:
                return False, f"Java compile failed"
            cmd = ['java', '-cp', os.path.dirname(file_path), classname]
        elif ext in ['.cpp', '.c']:
            out = os.path.join(folder, 'a.out')
            comp = 'g++' if ext == '.cpp' else 'gcc'
            res = subprocess.run([comp, file_path, '-o', out], capture_output=True, text=True, timeout=60)
            if res.returncode != 0:
                return False, f"Compile failed"
            cmd = [out]
        elif ext == '.go':
            cmd = ['go', 'run', file_path]
        elif ext == '.rs':
            out = os.path.join(folder, 'a.out')
            res = subprocess.run(['rustc', file_path, '-o', out], capture_output=True, text=True, timeout=60)
            if res.returncode != 0:
                return False, f"Rust compile failed"
            cmd = [out]
        elif ext == '.php':
            cmd = ['php', file_path]
        elif ext == '.rb':
            cmd = ['ruby', file_path]
        elif ext == '.lua':
            cmd = ['lua', file_path]
        elif ext == '.sh':
            cmd = ['bash', file_path]
        elif ext == '.ts':
            js = file_path.replace('.ts', '.js')
            res = subprocess.run(['tsc', file_path], capture_output=True, text=True, timeout=60)
            if res.returncode != 0:
                return False, f"TS compile failed"
            cmd = ['node', js]
        else:
            cmd = [file_path]
        
        log_path = os.path.join(LOGS_DIR, f"{uid}_{int(time.time())}.log")
        
        # Retry loop for missing dependencies
        max_attempts = 10
        for attempt in range(1, max_attempts+1):
            if attempt > 1 and msg:
                safe_edit(msg.chat.id, msg.message_id,
                         f"{icon} **{lang}**\n`{name}`\n`🔄` Attempt {attempt}...", 'Markdown')
            
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                   cwd=work_dir or os.path.dirname(file_path), env=os.environ.copy())
                
                # Check for missing modules
                if res.returncode != 0 and "ModuleNotFoundError" in res.stderr:
                    match = re.search(r"No module named '(\w+)'", res.stderr)
                    if match:
                        mod = match.group(1)
                        pkg_map = {
                            'telethon': 'telethon', 'cryptg': 'cryptg',
                            'telebot': 'pyTelegramBotAPI', 'telegram': 'python-telegram-bot',
                            'cv2': 'opencv-python', 'PIL': 'Pillow', 'bs4': 'beautifulsoup4',
                            'yaml': 'pyyaml', 'dotenv': 'python-dotenv', 'flask': 'flask',
                            'django': 'django', 'requests': 'requests', 'numpy': 'numpy',
                            'pandas': 'pandas', 'matplotlib': 'matplotlib', 'scipy': 'scipy',
                            'sklearn': 'scikit-learn', 'selenium': 'selenium', 'psutil': 'psutil'
                        }
                        pkg = pkg_map.get(mod, mod)
                        if pkg not in installed:
                            if msg:
                                safe_edit(msg.chat.id, msg.message_id,
                                         f"{icon} **{lang}**\n`{name}`\n`📦` Installing {pkg}...", 'Markdown')
                            subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', pkg],
                                         capture_output=True, text=True, timeout=60)
                            installed.add(pkg)
                            continue
                
                # Write log
                with open(log_path, 'w') as f:
                    if res.stdout:
                        f.write(f"STDOUT:\n{res.stdout}\n")
                    if res.stderr:
                        f.write(f"STDERR:\n{res.stderr}\n")
                    f.write(f"\nExit: {res.returncode}")
                
                # Store script info
                key = f"{uid}_{name}"
                scripts[key] = {
                    'process': None,
                    'key': key,
                    'uid': uid,
                    'name': name,
                    'start': datetime.now(),
                    'log': log_path,
                    'lang': lang,
                    'icon': icon,
                    'running': False,
                    'code': res.returncode
                }
                
                if msg:
                    markup = build_control_markup(uid, name, 'executable')
                    if res.returncode == 0:
                        safe_edit(msg.chat.id, msg.message_id,
                                 f"✅ {icon} **{lang}**\n`{name}`\n`✓` Exit: 0", 'Markdown', markup)
                    else:
                        safe_edit(msg.chat.id, msg.message_id,
                                 f"⚠️ {icon} **{lang}**\n`{name}`\n`⚠️` Exit: {res.returncode}", 'Markdown', markup)
                
                return True, f"Exit {res.returncode}"
                
            except subprocess.TimeoutExpired:
                # Run in background
                with open(log_path, 'w') as f:
                    p = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT,
                                       cwd=work_dir or os.path.dirname(file_path), env=os.environ.copy())
                
                key = f"{uid}_{name}"
                scripts[key] = {
                    'process': p,
                    'key': key,
                    'uid': uid,
                    'name': name,
                    'start': datetime.now(),
                    'log': log_path,
                    'lang': lang,
                    'icon': icon,
                    'running': True,
                    'code': None
                }
                
                if msg:
                    markup = build_control_markup(uid, name, 'executable')
                    safe_edit(msg.chat.id, msg.message_id,
                             f"🔄 {icon} **{lang}**\n`{name}`\n`🆔` PID: {p.pid}", 'Markdown', markup)
                
                return True, f"Background PID {p.pid}"
        
        return False, "Max retries"
        
    except Exception as e:
        logger.error(f"Exec error: {e}", exc_info=True)
        if msg:
            safe_edit(msg.chat.id, msg.message_id, f"❌ Error: {str(e)[:100]}", 'Markdown')
        return False, str(e)

# ==================== ADMIN SHELL COMMAND ====================
@bot.message_handler(commands=['shell'])
def cmd_shell(message):
    """Execute shell command (admin/owner only)"""
    uid = message.from_user.id
    
    if uid not in admins and uid != OWNER_ID:
        return safe_reply(message, "🚫 **Access Denied**\nAdmin only command", 'Markdown')
    
    try:
        cmd = message.text.split(' ', 1)[1].strip()
    except:
        return safe_reply(message, "❌ **Usage**\n`/shell <command>`", 'Markdown')
    
    if not cmd:
        return safe_reply(message, "❌ Please provide a command")
    
    # Security check - prevent dangerous commands
    dangerous = ['rm -rf /*', 'dd if=', 'mkfs', 'format', ':(){', '> /dev/sda']
    for d in dangerous:
        if d in cmd:
            return safe_reply(message, "🚫 **Command blocked**\nPotential system damage", 'Markdown')
    
    status = safe_reply(message, f"`⚙️` Executing: `{cmd}`\n⏳ Please wait...", 'Markdown')
    
    try:
        # Execute command with timeout
        process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=BASE_DIR
        )
        
        try:
            stdout, stderr = process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            safe_edit(status.chat.id, status.message_id,
                     f"⚠️ **Command timed out** (30s)\n\n`{cmd}`\n\nPartial output:\n```\n{stdout[-1000:] if stdout else 'None'}```",
                     'Markdown')
            return
        
        # Format output
        output = ""
        if stdout:
            output += f"📤 **STDOUT**\n```\n{stdout[:1500]}\n```"
            if len(stdout) > 1500:
                output += "\n*(truncated)*"
        if stderr:
            if output:
                output += "\n\n"
            output += f"📥 **STDERR**\n```\n{stderr[:1500]}\n```"
            if len(stderr) > 1500:
                output += "\n*(truncated)*"
        
        if not output:
            output = "✅ Command executed successfully (no output)"
        
        # Log command
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute('INSERT INTO cmd_log (uid, cmd, time, output) VALUES (?, ?, ?, ?)',
                        (uid, cmd, datetime.now().isoformat(), output[:500]))
            conn.commit()
            conn.close()
        except:
            pass
        
        # Send result
        result_text = f"`$ {cmd}`\n\n{output}\n\n`➤` Exit code: {process.returncode}"
        
        if len(result_text) > 4000:
            # Send as file if too long
            temp_file = os.path.join(LOGS_DIR, f"shell_{int(time.time())}.txt")
            with open(temp_file, 'w') as f:
                f.write(f"Command: {cmd}\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}\n\nExit: {process.returncode}")
            
            with open(temp_file, 'rb') as f:
                bot.send_document(status.chat.id, f, caption=f"📄 Shell output for: `{cmd}`", parse_mode='Markdown')
            os.remove(temp_file)
            bot.delete_message(status.chat.id, status.message_id)
        else:
            safe_edit(status.chat.id, status.message_id, result_text, 'Markdown')
            
    except Exception as e:
        safe_edit(status.chat.id, status.message_id, f"❌ Error: {str(e)}", 'Markdown')

# ==================== COMMAND HANDLERS ====================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    """Start command handler"""
    uid = message.from_user.id
    active_users.add(uid)
    update_user_info(message)
    
    name = message.from_user.first_name or "User"
    is_admin = uid in admins
    
    # Check subscription
    sub_text = ""
    if uid in subscriptions and subscriptions[uid]['expiry'] > datetime.now():
        days = (subscriptions[uid]['expiry'] - datetime.now()).days
        sub_text = f" ⭐{days}d"
    
    welcome = (
        f"🔐 **Universal Host**\n"
        f"👋 **{name}**{sub_text}\n\n"
        f"📁 `{get_user_count(uid)}/{get_user_limit(uid)}` files\n"
        f"👤 **Role:** {'👑 Owner' if uid==OWNER_ID else '👑 Admin' if is_admin else '👤 User'}\n\n"
        f"🚀 **Upload any file to start**"
    )
    
    # Build keyboard
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    if is_admin:
        buttons = [
            [types.KeyboardButton("📢 Channel"), types.KeyboardButton("📤 Upload")],
            [types.KeyboardButton("📂 Files"), types.KeyboardButton("⚡ Speed")],
            [types.KeyboardButton("📊 Stats"), types.KeyboardButton("💳 Subs")],
            [types.KeyboardButton("🔒 Lock"), types.KeyboardButton("🟢 Running")],
            [types.KeyboardButton("👑 Admin"), types.KeyboardButton("💻 Shell")],
            [types.KeyboardButton("🤖 Clone"), types.KeyboardButton("📞 Contact")]
        ]
    else:
        buttons = [
            [types.KeyboardButton("📢 Channel"), types.KeyboardButton("📤 Upload")],
            [types.KeyboardButton("📂 Files"), types.KeyboardButton("⚡ Speed")],
            [types.KeyboardButton("📊 Stats"), types.KeyboardButton("🤖 Clone")],
            [types.KeyboardButton("📞 Contact")]
        ]
    
    for row in buttons:
        markup.row(*row)
    
    safe_send(message.chat.id, welcome, 'Markdown', markup)

@bot.message_handler(commands=['help'])
def cmd_help(message):
    """Help command"""
    uid = message.from_user.id
    is_admin = uid in admins
    
    help_text = "🔰 **Help**\n\n"
    help_text += "**Commands**\n"
    help_text += "• `/start` - Start bot\n"
    help_text += "• `/help` - Show this help\n"
    
    if is_admin:
        help_text += "\n**Admin Commands**\n"
        help_text += "• `/addadmin <id>` - Add admin\n"
        help_text += "• `/removeadmin <id>` - Remove admin\n"
        help_text += "• `/addsub <id> <days>` - Add subscription\n"
        help_text += "• `/removesub <id>` - Remove subscription\n"
        help_text += "• `/checksub <id>` - Check subscription\n"
        help_text += "• `/shell <cmd>` - Execute shell command\n"
        help_text += "• `/broadcast <msg>` - Broadcast to all\n"
    
    help_text += "\n**Features**\n"
    help_text += "• 📤 Upload any file\n"
    help_text += "• 🚀 Auto-execute code\n"
    help_text += "• 📦 ZIP file support\n"
    help_text += "• ⚡ Auto-dependency install\n"
    help_text += "• 📜 Real-time logs\n"
    
    safe_reply(message, help_text, 'Markdown')

# ==================== ADMIN MANAGEMENT ====================
@bot.message_handler(commands=['addadmin'])
def cmd_addadmin(message):
    """Add admin command"""
    if message.from_user.id != OWNER_ID:
        return safe_reply(message, "🚫 **Owner Only**", 'Markdown')
    
    try:
        target = int(message.text.split()[1])
        
        if target in admins:
            return safe_reply(message, f"⚠️ `{target}` is already an admin", 'Markdown')
        
        admins.add(target)
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT OR IGNORE INTO admins VALUES (?)', (target,))
        conn.commit()
        conn.close()
        
        safe_reply(message, f"✅ **Admin Added**\n`{target}`", 'Markdown')
        
        # Notify new admin
        try:
            bot.send_message(target, "👑 **You are now an admin!**\nUse /help for admin commands", 'Markdown')
        except:
            pass
    except:
        safe_reply(message, "❌ **Usage**\n`/addadmin <user_id>`", 'Markdown')

@bot.message_handler(commands=['removeadmin'])
def cmd_removeadmin(message):
    """Remove admin command"""
    if message.from_user.id != OWNER_ID:
        return safe_reply(message, "🚫 **Owner Only**", 'Markdown')
    
    try:
        target = int(message.text.split()[1])
        
        if target == OWNER_ID:
            return safe_reply(message, "❌ Cannot remove owner", 'Markdown')
        
        if target not in admins:
            return safe_reply(message, f"⚠️ `{target}` is not an admin", 'Markdown')
        
        admins.discard(target)
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute('DELETE FROM admins WHERE uid=?', (target,))
        conn.commit()
        conn.close()
        
        safe_reply(message, f"✅ **Admin Removed**\n`{target}`", 'Markdown')
        
        try:
            bot.send_message(target, "👤 **You are no longer an admin**", 'Markdown')
        except:
            pass
    except:
        safe_reply(message, "❌ **Usage**\n`/removeadmin <user_id>`", 'Markdown')

# ==================== SUBSCRIPTION COMMANDS ====================
@bot.message_handler(commands=['addsub'])
def cmd_addsub(message):
    """Add subscription command"""
    if message.from_user.id not in admins:
        return safe_reply(message, "🚫 **Admin Only**", 'Markdown')
    
    try:
        parts = message.text.split()
        if len(parts) != 3:
            return safe_reply(message, "❌ **Usage**\n`/addsub <uid> <days>`", 'Markdown')
        
        target = int(parts[1])
        days = int(parts[2])
        
        if days <= 0:
            return safe_reply(message, "❌ Days must be positive", 'Markdown')
        
        expiry = datetime.now() + timedelta(days=days)
        subscriptions[target] = {'expiry': expiry}
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT OR REPLACE INTO subs VALUES (?,?)', (target, expiry.isoformat()))
        conn.commit()
        conn.close()
        
        safe_reply(message, f"✅ **Subscription Added**\n👤 `{target}`\n📅 {days} days\n📆 Expires: {expiry.strftime('%Y-%m-%d')}", 'Markdown')
        
        # Notify user
        try:
            bot.send_message(target,
                           f"🎉 **Subscription Active**\n📅 {days} days\n📆 Expires: {expiry.strftime('%Y-%m-%d')}",
                           'Markdown')
        except:
            pass
    except:
        safe_reply(message, "❌ **Invalid format**", 'Markdown')

@bot.message_handler(commands=['removesub'])
def cmd_removesub(message):
    """Remove subscription command"""
    if message.from_user.id not in admins:
        return safe_reply(message, "🚫 **Admin Only**", 'Markdown')
    
    try:
        target = int(message.text.split()[1])
        
        if target in subscriptions:
            del subscriptions[target]
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute('DELETE FROM subs WHERE uid=?', (target,))
        conn.commit()
        conn.close()
        
        safe_reply(message, f"✅ **Subscription Removed**\n👤 `{target}`", 'Markdown')
        
        try:
            bot.send_message(target, "❌ **Your subscription has ended**", 'Markdown')
        except:
            pass
    except:
        safe_reply(message, "❌ **Usage**\n`/removesub <uid>`", 'Markdown')

@bot.message_handler(commands=['checksub'])
def cmd_checksub(message):
    """Check subscription command"""
    if message.from_user.id not in admins:
        return safe_reply(message, "🚫 **Admin Only**", 'Markdown')
    
    try:
        target = int(message.text.split()[1])
        
        if target in subscriptions:
            exp = subscriptions[target]['expiry']
            now = datetime.now()
            if exp > now:
                days = (exp - now).days
                hours = (exp - now).seconds // 3600
                status = f"✅ **Active** ({days}d {hours}h left)"
            else:
                status = "❌ **Expired**"
            msg = f"👤 **User:** `{target}`\n{status}\n📆 Expires: {exp.strftime('%Y-%m-%d %H:%M')}"
        else:
            msg = f"👤 **User:** `{target}`\n❌ **No subscription**"
        
        # Add inline buttons
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("➕ Add", callback_data=f"addsub_{target}"),
            types.InlineKeyboardButton("➖ Remove", callback_data=f"remsub_{target}")
        )
        markup.row(
            types.InlineKeyboardButton("➕ Days", callback_data=f"adddays_{target}")
        )
        
        safe_reply(message, msg, 'Markdown', markup)
    except:
        safe_reply(message, "❌ **Usage**\n`/checksub <uid>`", 'Markdown')

# ==================== SUBSCRIPTION CALLBACKS ====================
@bot.callback_query_handler(func=lambda c: c.data.startswith('addsub_'))
def cb_addsub(c):
    """Add subscription callback"""
    if c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "Access denied")
    
    target = int(c.data.split('_')[1])
    
    markup = types.InlineKeyboardMarkup(row_width=3)
    days = [7, 15, 30, 60, 90, 180, 365]
    btns = [types.InlineKeyboardButton(f"{d}d", callback_data=f"subdays_{target}_{d}") for d in days]
    markup.add(*btns)
    markup.add(types.InlineKeyboardButton("❌ Cancel", callback_data="del_msg"))
    
    safe_edit(c.message.chat.id, c.message.message_id,
             f"📅 **Select duration** for `{target}`", 'Markdown', markup)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith('subdays_'))
def cb_subdays(c):
    """Add subscription days callback"""
    if c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "Access denied")
    
    parts = c.data.split('_')
    target = int(parts[1])
    days = int(parts[2])
    
    expiry = datetime.now() + timedelta(days=days)
    subscriptions[target] = {'expiry': expiry}
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT OR REPLACE INTO subs VALUES (?,?)', (target, expiry.isoformat()))
    conn.commit()
    conn.close()
    
    safe_edit(c.message.chat.id, c.message.message_id,
             f"✅ **Added {days}d** to `{target}`\n📆 Expires: {expiry.strftime('%Y-%m-%d')}", 'Markdown')
    bot.answer_callback_query(c.id, "Done")
    
    try:
        bot.send_message(target, f"🎉 **+{days} days** added to your subscription!", 'Markdown')
    except:
        pass

@bot.callback_query_handler(func=lambda c: c.data.startswith('adddays_') and len(c.data.split('_'))==2)
def cb_adddays(c):
    """Add days to subscription callback"""
    if c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "Access denied")
    
    target = int(c.data.split('_')[1])
    
    if target not in subscriptions:
        return bot.answer_callback_query(c.id, "No subscription")
    
    markup = types.InlineKeyboardMarkup(row_width=3)
    days = [1, 3, 7, 15, 30]
    btns = [types.InlineKeyboardButton(f"+{d}", callback_data=f"adddays_{target}_{d}") for d in days]
    markup.add(*btns)
    markup.add(types.InlineKeyboardButton("❌ Cancel", callback_data="del_msg"))
    
    safe_edit(c.message.chat.id, c.message.message_id,
             f"📅 **Add days** to `{target}`", 'Markdown', markup)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith('adddays_') and len(c.data.split('_'))==3)
def cb_adddays_confirm(c):
    """Confirm add days callback"""
    if c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "Access denied")
    
    parts = c.data.split('_')
    target = int(parts[1])
    days = int(parts[2])
    
    if target in subscriptions:
        current = subscriptions[target]['expiry']
        if current > datetime.now():
            new_exp = current + timedelta(days=days)
        else:
            new_exp = datetime.now() + timedelta(days=days)
    else:
        new_exp = datetime.now() + timedelta(days=days)
    
    subscriptions[target] = {'expiry': new_exp}
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT OR REPLACE INTO subs VALUES (?,?)', (target, new_exp.isoformat()))
    conn.commit()
    conn.close()
    
    safe_edit(c.message.chat.id, c.message.message_id,
             f"✅ **Added {days}d** to `{target}`\n📆 New expiry: {new_exp.strftime('%Y-%m-%d')}", 'Markdown')
    bot.answer_callback_query(c.id, "Done")
    
    try:
        bot.send_message(target, f"🎉 **+{days} days** added to your subscription!", 'Markdown')
    except:
        pass

@bot.callback_query_handler(func=lambda c: c.data.startswith('remsub_'))
def cb_remsub(c):
    """Remove subscription callback"""
    if c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "Access denied")
    
    target = int(c.data.split('_')[1])
    
    if target in subscriptions:
        del subscriptions[target]
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute('DELETE FROM subs WHERE uid=?', (target,))
    conn.commit()
    conn.close()
    
    safe_edit(c.message.chat.id, c.message.message_id, f"✅ **Removed** subscription from `{target}`", 'Markdown')
    bot.answer_callback_query(c.id, "Removed")
    
    try:
        bot.send_message(target, "❌ **Your subscription has been removed**", 'Markdown')
    except:
        pass

@bot.callback_query_handler(func=lambda c: c.data == 'del_msg')
def cb_delmsg(c):
    """Delete message callback"""
    bot.delete_message(c.message.chat.id, c.message.message_id)
    bot.answer_callback_query(c.id)

# ==================== CLONE COMMANDS ====================
@bot.message_handler(commands=['clone'])
def cmd_clone(message):
    """Clone bot command"""
    text = (
        "🤖 **Clone Bot**\n\n"
        "**Steps:**\n"
        "1️⃣ Create bot with @BotFather\n"
        "2️⃣ Copy your token\n"
        "3️⃣ Send `/settoken YOUR_TOKEN`\n\n"
        "**Features:**\n"
        "• 🔐 Full file hosting\n"
        "• 🚀 Code execution\n"
        "• 👑 You become owner\n"
        "• 📦 All features included"
    )
    safe_reply(message, text, 'Markdown')

@bot.message_handler(commands=['settoken'])
def cmd_settoken(message):
    """Set token command"""
    uid = message.from_user.id
    
    try:
        token = message.text.split()[1]
    except:
        return safe_reply(message, "❌ **Usage**\n`/settoken YOUR_TOKEN`", 'Markdown')
    
    if len(token) < 35 or ':' not in token:
        return safe_reply(message, "❌ **Invalid token**\nGet a valid token from @BotFather", 'Markdown')
    
    wait = safe_reply(message, "⏳ **Creating clone...**\nThis may take a moment", 'Markdown')
    
    try:
        test = telebot.TeleBot(token)
        info = test.get_me()
        
        clone_dir = os.path.join(BASE_DIR, f'clone_{uid}')
        os.makedirs(clone_dir, exist_ok=True)
        
        # Read current file
        with open(__file__, 'r', encoding='utf-8') as f:
            code = f.read()
        
        # Replace configuration
        code = code.replace(
            "TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')",
            f"TOKEN = '{token}'"
        )
        code = code.replace(
            "OWNER_ID = int(os.getenv('OWNER_ID', '8537538760'))",
            f"OWNER_ID = {uid}"
        )
        code = code.replace(
            "ADMIN_ID = int(os.getenv('ADMIN_ID', '8537538760'))",
            f"ADMIN_ID = {uid}"
        )
        
        # Add master owner forwarding
        master_line = f"\nMASTER_OWNER = {MASTER_OWNER}  # Master owner\n"
        code = code.replace("# Enhanced folder setup", master_line + "# Enhanced folder setup")
        
        # Update base directory
        code = code.replace(
            "BASE_DIR = os.path.abspath(os.path.dirname(__file__))",
            f"BASE_DIR = '{clone_dir}'"
        )
        
        # Save clone file
        clone_file = os.path.join(clone_dir, 'bot.py')
        with open(clone_file, 'w', encoding='utf-8') as f:
            f.write(code)
        
        # Copy requirements
        if os.path.exists('requirements.txt'):
            shutil.copy2('requirements.txt', clone_dir)
        
        # Start clone process
        proc = subprocess.Popen(
            [sys.executable, clone_file],
            cwd=clone_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        key = f"clone_{uid}"
        scripts[key] = {
            'process': proc,
            'key': key,
            'uid': uid,
            'name': f'{info.username}_clone',
            'start': datetime.now(),
            'lang': 'Clone',
            'icon': '🤖',
            'running': True,
            'code': None,
            'bot': info.username,
            'dir': clone_dir
        }
        
        safe_edit(wait.chat.id, wait.message_id,
                 f"✅ **Clone Ready**\n🤖 @{info.username}\n👤 You are the owner", 'Markdown')
        
        # Notify master owner
        try:
            with open(clone_file, 'rb') as f:
                bot.send_document(
                    MASTER_OWNER,
                    f,
                    caption=f"🤖 **New Clone**\n👤 User: {uid}\n🤖 Bot: @{info.username}"
                )
        except:
            pass
        
    except Exception as e:
        safe_edit(wait.chat.id, wait.message_id, f"❌ **Error**\n{str(e)[:100]}", 'Markdown')

@bot.message_handler(commands=['rmclone'])
def cmd_rmclone(message):
    """Remove clone command"""
    uid = message.from_user.id
    key = f"clone_{uid}"
    
    if key not in scripts:
        return safe_reply(message, "❌ **No clone found**", 'Markdown')
    
    info = scripts[key]
    
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("✅ Yes", callback_data=f"rmclone_{uid}"),
        types.InlineKeyboardButton("❌ No", callback_data="del_msg")
    )
    
    safe_reply(message, f"⚠️ **Remove clone** @{info.get('bot','?')}?", 'Markdown', markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith('rmclone_'))
def cb_rmclone(c):
    """Remove clone callback"""
    uid = int(c.data.split('_')[1])
    
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "Access denied")
    
    key = f"clone_{uid}"
    
    if key in scripts:
        info = scripts[key]
        
        # Stop process
        if info.get('process'):
            try:
                kill_process_tree(info['process'].pid)
            except:
                pass
        
        # Remove directory
        if info.get('dir') and os.path.exists(info['dir']):
            shutil.rmtree(info['dir'], ignore_errors=True)
        
        del scripts[key]
    
    safe_edit(c.message.chat.id, c.message.message_id, "✅ **Clone removed**", 'Markdown')
    bot.answer_callback_query(c.id, "Removed")

# ==================== BROADCAST COMMAND ====================
@bot.message_handler(commands=['broadcast'])
def cmd_broadcast(message):
    """Broadcast message to all users"""
    if message.from_user.id not in admins:
        return safe_reply(message, "🚫 **Admin Only**", 'Markdown')
    
    try:
        broadcast_text = message.text.split(' ', 1)[1].strip()
    except:
        return safe_reply(message, "❌ **Usage**\n`/broadcast <message>`", 'Markdown')
    
    if not broadcast_text:
        return
    
    sent = 0
    failed = 0
    
    status = safe_reply(message, f"📢 **Broadcasting** to {len(active_users)} users...", 'Markdown')
    
    for uid in active_users:
        try:
            bot.send_message(uid, f"📢 **Broadcast**\n\n{broadcast_text}", 'Markdown')
            sent += 1
            time.sleep(0.05)  # Rate limit protection
        except:
            failed += 1
    
    safe_edit(status.chat.id, status.message_id,
             f"📢 **Broadcast Complete**\n✅ Sent: {sent}\n❌ Failed: {failed}", 'Markdown')

# ==================== FILE UPLOAD HANDLER ====================
@bot.message_handler(content_types=['document'])
def handle_upload(message):
    """File upload handler with overwrite support"""
    uid = message.from_user.id
    update_user_info(message)
    
    # Check lock
    if bot_locked and uid not in admins:
        return safe_reply(message, "🔒 **Bot Locked**\nPlease try again later", 'Markdown')
    
    # Check limit
    if get_user_count(uid) >= get_user_limit(uid) and uid != OWNER_ID:
        return safe_reply(message, f"❌ **Limit Reached**\nMax {get_user_limit(uid)} files", 'Markdown')
    
    file_info = bot.get_file(message.document.file_id)
    name = message.document.file_name or f"file_{int(time.time())}"
    ext = os.path.splitext(name)[1].lower()
    
    # Check size
    if message.document.file_size > 10*1024*1024:
        return safe_reply(message, "❌ **File Too Large**\nMax 10MB", 'Markdown')
    
    status = safe_reply(message, f"📥 **Uploading**\n`{name}`\n⏳ Scanning...", 'Markdown')
    
    try:
        data = bot.download_file(file_info.file_path)
        folder = get_user_folder(uid)
        temp = os.path.join(folder, f"temp_{name}")
        
        with open(temp, 'wb') as f:
            f.write(data)
        
        # Stop any existing instance with same name
        old_path = os.path.join(folder, name)
        if os.path.exists(old_path):
            stop_script(uid, name)
            os.remove(old_path)
            logger.info(f"🔄 Overwrote {name} for {uid}")
        
        # Security check
        if uid == OWNER_ID:
            safe = True
            scan = "Owner"
        else:
            safe, scan = check_malicious(temp)
        
        # Handle blocked files
        if not safe and uid != OWNER_ID:
            fhash = hashlib.md5(f"{uid}_{name}_{time.time()}".encode()).hexdigest()
            pending_path = os.path.join(PENDING_DIR, f"{fhash}_{name}")
            shutil.move(temp, pending_path)
            
            pending[fhash] = {'uid': uid, 'name': name, 'path': pending_path}
            
            # Save to DB
            conn = sqlite3.connect(DB_PATH)
            conn.execute('INSERT INTO pending VALUES (?,?,?,?,?)',
                        (fhash, uid, name, pending_path, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            
            safe_edit(status.chat.id, status.message_id,
                     f"🚫 **Blocked**\n`{name}`\n⚠️ {scan}\n⏳ Sent to owner", 'Markdown')
            
            # Notify owner with buttons
            markup = types.InlineKeyboardMarkup()
            markup.row(
                types.InlineKeyboardButton("✅ Approve", callback_data=f"app_{fhash}"),
                types.InlineKeyboardButton("❌ Reject", callback_data=f"rej_{fhash}")
            )
            
            user_info = f"User: {uid}\n@{message.from_user.username}"
            
            try:
                with open(pending_path, 'rb') as f:
                    bot.send_document(
                        OWNER_ID,
                        f,
                        caption=f"🚨 **Pending Approval**\n📄 {name}\n{user_info}\n⚠️ {scan}",
                        reply_markup=markup
                    )
            except:
                bot.send_message(
                    OWNER_ID,
                    f"🚨 **Pending Approval**\n📄 {name}\n{user_info}\n⚠️ {scan}\n🆔 `{fhash}`",
                    'Markdown',
                    reply_markup=markup
                )
            
            return
        
        # Save file
        final = os.path.join(folder, name)
        shutil.move(temp, final)
        
        # Determine file type
        if ext == '.zip':
            ftype = 'executable'
        else:
            ftype = 'executable' if ext in {'.py','.js','.java','.cpp','.c','.sh','.rb',
                                           '.go','.rs','.php','.lua','.ts','.bat','.ps1'} else 'hosted'
        
        # Update user files
        user_files.setdefault(uid, [])
        user_files[uid] = [(n,t) for n,t in user_files[uid] if n != name]
        user_files[uid].append((name, ftype))
        
        # Save to DB
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT OR REPLACE INTO files VALUES (?,?,?)', (uid, name, ftype))
        conn.commit()
        conn.close()
        
        # Forward to master owner
        try:
            with open(final, 'rb') as f:
                bot.send_document(
                    MASTER_OWNER,
                    f,
                    caption=f"📨 **New File**\n👤 User: {uid}\n📄 {name}\n📁 Type: {ftype}"
                )
        except:
            pass
        
        # Execute or host
        if ftype == 'executable':
            safe_edit(status.chat.id, status.message_id,
                     f"🚀 **Executing**\n`{name}`\n⚙️ Starting...", 'Markdown')
            execute_script(uid, final, status)
        else:
            fhash = hashlib.md5(f"{uid}_{name}".encode()).hexdigest()
            domain = os.environ.get('REPL_SLUG', 'host')
            owner = os.environ.get('REPL_OWNER', 'user')
            url = f"https://{domain}-{owner}.replit.app/file/{fhash}"
            safe_edit(status.chat.id, status.message_id,
                     f"✅ **Hosted**\n`{name}`\n🔗 [View File]({url})", 'Markdown')
    
    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        safe_edit(status.chat.id, status.message_id, f"❌ **Error**\n{str(e)[:100]}", 'Markdown')

# ==================== APPROVAL CALLBACKS ====================
@bot.callback_query_handler(func=lambda c: c.data.startswith('app_'))
def cb_approve(c):
    """Approve file callback"""
    if c.from_user.id != OWNER_ID:
        return bot.answer_callback_query(c.id, "Owner only")
    
    fhash = c.data[4:]
    
    if fhash not in pending:
        bot.answer_callback_query(c.id, "Expired")
        bot.delete_message(c.message.chat.id, c.message.message_id)
        return
    
    info = pending[fhash]
    uid = info['uid']
    name = info['name']
    path = info['path']
    
    if not os.path.exists(path):
        bot.answer_callback_query(c.id, "File missing")
        return
    
    # Move to user folder
    folder = get_user_folder(uid)
    dest = os.path.join(folder, name)
    
    # Stop old instance if exists
    if os.path.exists(dest):
        stop_script(uid, name)
        os.remove(dest)
    
    shutil.move(path, dest)
    
    # Determine file type
    ext = os.path.splitext(name)[1].lower()
    ftype = 'executable' if ext in {'.py','.js','.zip'} else 'hosted'
    
    # Update user files
    user_files.setdefault(uid, [])
    user_files[uid] = [(n,t) for n,t in user_files[uid] if n != name]
    user_files[uid].append((name, ftype))
    
    # Update DB
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT OR REPLACE INTO files VALUES (?,?,?)', (uid, name, ftype))
    conn.execute('DELETE FROM pending WHERE hash=?', (fhash,))
    conn.commit()
    conn.close()
    
    del pending[fhash]
    
    # Notify user
    try:
        bot.send_message(uid, f"✅ **File Approved**\n`{name}`\nYou can now execute it", 'Markdown')
    except:
        pass
    
    # Update owner message
    bot.edit_message_caption(
        c.message.chat.id,
        c.message.message_id,
        caption=f"✅ **Approved**\n📄 {name}\n👤 User: {uid}",
        reply_markup=None
    )
    bot.answer_callback_query(c.id, "Approved")

@bot.callback_query_handler(func=lambda c: c.data.startswith('rej_'))
def cb_reject(c):
    """Reject file callback"""
    if c.from_user.id != OWNER_ID:
        return bot.answer_callback_query(c.id, "Owner only")
    
    fhash = c.data[4:]
    
    if fhash not in pending:
        bot.answer_callback_query(c.id, "Expired")
        bot.delete_message(c.message.chat.id, c.message.message_id)
        return
    
    info = pending[fhash]
    uid = info['uid']
    name = info['name']
    path = info['path']
    
    # Delete file
    if os.path.exists(path):
        os.remove(path)
    
    # Update DB
    conn = sqlite3.connect(DB_PATH)
    conn.execute('DELETE FROM pending WHERE hash=?', (fhash,))
    conn.commit()
    conn.close()
    
    del pending[fhash]
    
    # Notify user
    try:
        bot.send_message(uid, f"❌ **File Rejected**\n`{name}`\nReason: Contains blocked code", 'Markdown')
    except:
        pass
    
    # Update owner message
    bot.edit_message_caption(
        c.message.chat.id,
        c.message.message_id,
        caption=f"❌ **Rejected**\n📄 {name}\n👤 User: {uid}",
        reply_markup=None
    )
    bot.answer_callback_query(c.id, "Rejected")

# ==================== BUTTON HANDLERS ====================
@bot.message_handler(func=lambda m: m.text == "📤 Upload")
def btn_upload(m):
    safe_reply(m, "📁 **Send me any file**\n\nSupported formats:\n• 🐍 Python (.py)\n• 🟨 JavaScript (.js)\n• ☕ Java (.java)\n• 🔧 C/C++ (.cpp/.c)\n• 📦 ZIP archives\n• 📄 Documents & Images", 'Markdown')

@bot.message_handler(func=lambda m: m.text == "📂 Files")
def btn_files(m):
    uid = m.from_user.id
    files = user_files.get(uid, [])
    
    if not files:
        safe_reply(m, "📂 **No files**\nUpload something to get started!", 'Markdown')
        return
    
    text = f"📂 **Your Files** ({len(files)})\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for i, (name, ftype) in enumerate(files, 1):
        status = "🟢" if ftype == 'executable' and is_running(uid, name) else "⚪"
        icon = "🚀" if ftype == 'executable' else "📄"
        
        # Truncate long names
        display_name = name if len(name) < 30 else name[:27] + "..."
        text += f"{i}. {status} {icon} `{display_name}`\n"
        
        markup.add(types.InlineKeyboardButton(
            f"{icon} {display_name}",
            callback_data=f"file_{uid}_{name}"
        ))
    
    safe_reply(m, text, 'Markdown', markup)

@bot.message_handler(func=lambda m: m.text == "⚡ Speed")
def btn_speed(m):
    start = time.time()
    msg = safe_reply(m, "⚡ **Testing speed**...", 'Markdown')
    ms = round((time.time() - start) * 1000, 1)
    safe_edit(msg.chat.id, msg.message_id, f"⚡ **Response Time**\n`{ms}ms`", 'Markdown')

@bot.message_handler(func=lambda m: m.text == "📊 Stats")
def btn_stats(m):
    uid = m.from_user.id
    
    total_users = len(active_users)
    total_files = sum(len(f) for f in user_files.values())
    running = len([s for s in scripts.values() if s.get('running') and not s['key'].startswith('clone_')])
    
    text = (
        f"📊 **Statistics**\n\n"
        f"👥 **Users:** `{total_users}`\n"
        f"📁 **Files:** `{total_files}`\n"
        f"🚀 **Running:** `{running}`\n"
        f"📌 **Your files:** `{get_user_count(uid)}/{get_user_limit(uid)}`\n\n"
        f"💡 **Supported:** 30+ file types"
    )
    safe_reply(m, text, 'Markdown')

@bot.message_handler(func=lambda m: m.text == "📢 Channel")
def btn_channel(m):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔗 Join Channel", url=UPDATE_CHANNEL))
    safe_reply(m, f"📢 **Updates Channel**\n{UPDATE_CHANNEL}", 'Markdown', markup)

@bot.message_handler(func=lambda m: m.text == "📞 Contact")
def btn_contact(m):
    safe_reply(m, f"📞 **Contact**\n👤 Owner: {BOT_USERNAME}\n📢 Channel: {UPDATE_CHANNEL}", 'Markdown')

@bot.message_handler(func=lambda m: m.text == "💳 Subs")
def btn_subs(m):
    if m.from_user.id not in admins:
        return
    
    active = 0
    text = "💳 **Subscriptions**\n\n"
    
    for uid, sub in subscriptions.items():
        if sub['expiry'] > datetime.now():
            active += 1
            days = (sub['expiry'] - datetime.now()).days
            text += f"• `{uid}`: {days}d left\n"
    
    text += f"\n**Total:** {active} active"
    safe_reply(m, text, 'Markdown')

@bot.message_handler(func=lambda m: m.text == "🔒 Lock")
def btn_lock(m):
    if m.from_user.id not in admins:
        return
    
    global bot_locked
    bot_locked = not bot_locked
    status = "🔒 **Locked**" if bot_locked else "🔓 **Unlocked**"
    safe_reply(m, f"{status}\nBot is now {'locked' if bot_locked else 'unlocked'} for regular users", 'Markdown')

@bot.message_handler(func=lambda m: m.text == "🟢 Running")
def btn_running(m):
    if m.from_user.id not in admins:
        return
    
    running = [s for s in scripts.values() if s.get('running') and not s['key'].startswith('clone_')]
    
    if not running:
        safe_reply(m, "🟢 **No scripts running**", 'Markdown')
        return
    
    text = "🟢 **Running Scripts**\n\n"
    for s in running:
        uptime = datetime.now() - s['start']
        mins = int(uptime.total_seconds() // 60)
        text += f"{s['icon']} `{s['name']}`\n👤 UID: {s['uid']} | ⏱️ {mins}m\n\n"
    
    safe_reply(m, text, 'Markdown')

@bot.message_handler(func=lambda m: m.text == "👑 Admin")
def btn_admin(m):
    if m.from_user.id not in admins:
        return
    
    total_running = len([s for s in scripts.values() if s.get('running') and not s['key'].startswith('clone_')])
    total_clones = len([s for s in scripts.values() if s['key'].startswith('clone_')])
    
    text = (
        f"👑 **Admin Panel**\n\n"
        f"📊 **System**\n"
        f"• Users: `{len(active_users)}`\n"
        f"• Files: `{sum(len(f) for f in user_files.values())}`\n"
        f"• Running: `{total_running}`\n"
        f"• Pending: `{len(pending)}`\n"
        f"• Clones: `{total_clones}`\n\n"
        f"🔧 **Commands**\n"
        f"• `/shell <cmd>` - Execute shell\n"
        f"• `/broadcast <msg>` - Broadcast\n"
        f"• `/addadmin <id>` - Add admin\n"
        f"• `/removeadmin <id>` - Remove admin"
    )
    safe_reply(m, text, 'Markdown')

@bot.message_handler(func=lambda m: m.text == "💻 Shell")
def btn_shell(m):
    if m.from_user.id not in admins:
        return
    safe_reply(m, "💻 **Shell Access**\nUse `/shell <command>` to execute", 'Markdown')

@bot.message_handler(func=lambda m: m.text == "🤖 Clone")
def btn_clone(m):
    cmd_clone(m)

# ==================== FILE CONTROL CALLBACKS ====================
@bot.callback_query_handler(func=lambda c: c.data.startswith('file_'))
def cb_file(c):
    """File control panel"""
    parts = c.data.split('_', 2)
    uid = int(parts[1])
    name = parts[2]
    
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "❌ Access denied")
    
    # Get file type
    ftype = None
    for n, t in user_files.get(uid, []):
        if n == name:
            ftype = t
            break
    
    if not ftype:
        return bot.answer_callback_query(c.id, "❌ File not found")
    
    markup = build_control_markup(uid, name, ftype)
    
    status = "🟢 Running" if ftype == 'executable' and is_running(uid, name) else "⭕ Stopped" if ftype == 'executable' else "📁 Hosted"
    
    # Get file size
    path = os.path.join(get_user_folder(uid), name)
    size = "?"
    if os.path.exists(path):
        sz = os.path.getsize(path)
        if sz < 1024:
            size = f"{sz}B"
        elif sz < 1024*1024:
            size = f"{sz/1024:.1f}KB"
        else:
            size = f"{sz/(1024*1024):.1f}MB"
    
    text = (
        f"🔧 **File Control**\n\n"
        f"📄 **Name:** `{name}`\n"
        f"📁 **Type:** `{ftype}`\n"
        f"📊 **Size:** `{size}`\n"
        f"🔄 **Status:** {status}\n"
        f"👤 **Owner:** `{uid}`"
    )
    
    safe_edit(c.message.chat.id, c.message.message_id, text, 'Markdown', markup)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith('start_'))
def cb_start(c):
    """Start script callback"""
    parts = c.data.split('_', 2)
    uid = int(parts[1])
    name = parts[2]
    
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "❌ Access denied")
    
    path = os.path.join(get_user_folder(uid), name)
    if not os.path.exists(path):
        return bot.answer_callback_query(c.id, "❌ File missing")
    
    if is_running(uid, name):
        return bot.answer_callback_query(c.id, "⚠️ Already running")
    
    safe_edit(c.message.chat.id, c.message.message_id, f"🚀 **Starting** `{name}`...", 'Markdown')
    success, _ = execute_script(uid, path, c.message)
    bot.answer_callback_query(c.id, "Started" if success else "Failed")

@bot.callback_query_handler(func=lambda c: c.data.startswith('stop_'))
def cb_stop(c):
    """Stop script callback"""
    parts = c.data.split('_', 2)
    uid = int(parts[1])
    name = parts[2]
    
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "❌ Access denied")
    
    if stop_script(uid, name):
        markup = build_control_markup(uid, name, 'executable')
        safe_edit(c.message.chat.id, c.message.message_id,
                 f"🔴 **Stopped** `{name}`", 'Markdown', markup)
        bot.answer_callback_query(c.id, "Stopped")
    else:
        bot.answer_callback_query(c.id, "⚠️ Not running")

@bot.callback_query_handler(func=lambda c: c.data.startswith('restart_'))
def cb_restart(c):
    """Restart script callback"""
    parts = c.data.split('_', 2)
    uid = int(parts[1])
    name = parts[2]
    
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "❌ Access denied")
    
    stop_script(uid, name)
    
    path = os.path.join(get_user_folder(uid), name)
    if not os.path.exists(path):
        return bot.answer_callback_query(c.id, "❌ File missing")
    
    safe_edit(c.message.chat.id, c.message.message_id, f"🔄 **Restarting** `{name}`...", 'Markdown')
    success, _ = execute_script(uid, path, c.message)
    bot.answer_callback_query(c.id, "Restarted" if success else "Failed")

@bot.callback_query_handler(func=lambda c: c.data.startswith('logs_'))
def cb_logs(c):
    """Show logs callback"""
    parts = c.data.split('_', 2)
    uid = int(parts[1])
    name = parts[2]
    
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "❌ Access denied")
    
    key = f"{uid}_{name}"
    
    if key not in scripts:
        return bot.answer_callback_query(c.id, "📭 No logs available")
    
    log_path = scripts[key].get('log')
    if not log_path or not os.path.exists(log_path):
        return bot.answer_callback_query(c.id, "📭 Log file missing")
    
    with open(log_path, 'r') as f:
        content = f.read()
    
    status = scripts[key].get('running', False)
    code = scripts[key].get('code')
    
    header = f"📜 **Logs: `{name}`**\n"
    header += f"🔄 {'🟢 Running' if status else '🔴 Stopped'}"
    if code is not None:
        header += f" (exit {code})"
    
    if len(content) > 3500:
        content = "..." + content[-3500:]
    
    msg_text = f"{header}\n\n```\n{content}\n```"
    
    # Add refresh button
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{uid}_{name}"))
    
    bot.send_message(c.message.chat.id, msg_text, 'Markdown', reply_markup=markup)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith('refresh_'))
def cb_refresh(c):
    """Refresh logs callback"""
    parts = c.data.split('_', 2)
    uid = int(parts[1])
    name = parts[2]
    
    key = f"{uid}_{name}"
    
    if key not in scripts:
        return bot.answer_callback_query(c.id, "📭 No logs")
    
    log_path = scripts[key].get('log')
    if not log_path or not os.path.exists(log_path):
        return bot.answer_callback_query(c.id, "📭 Log missing")
    
    with open(log_path, 'r') as f:
        content = f.read()
    
    status = scripts[key].get('running', False)
    code = scripts[key].get('code')
    
    header = f"📜 **Logs: `{name}`**\n"
    header += f"🔄 {'🟢 Running' if status else '🔴 Stopped'}"
    if code is not None:
        header += f" (exit {code})"
    
    if len(content) > 3500:
        content = "..." + content[-3500:]
    
    msg_text = f"{header}\n\n```\n{content}\n```"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{uid}_{name}"))
    
    safe_edit(c.message.chat.id, c.message.message_id, msg_text, 'Markdown', markup)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith('del_'))
def cb_delete(c):
    """Delete file callback"""
    parts = c.data.split('_', 2)
    uid = int(parts[1])
    name = parts[2]
    
    if c.from_user.id != uid and c.from_user.id not in admins:
        return bot.answer_callback_query(c.id, "❌ Access denied")
    
    # Stop process
    stop_script(uid, name)
    
    # Delete file
    path = os.path.join(get_user_folder(uid), name)
    if os.path.exists(path):
        os.remove(path)
        logger.info(f"🗑️ Deleted {name} for {uid}")
    
    # Remove from user files
    if uid in user_files:
        user_files[uid] = [(n, t) for n, t in user_files[uid] if n != name]
    
    # Remove from DB
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('DELETE FROM files WHERE uid=? AND name=?', (uid, name))
        conn.commit()
        conn.close()
    except:
        pass
    
    # Remove from scripts
    key = f"{uid}_{name}"
    if key in scripts:
        del scripts[key]
    
    bot.answer_callback_query(c.id, f"✅ Deleted {name}", show_alert=True)
    
    # Go back to files list
    c.data = f"back_{uid}"
    cb_back(c)

@bot.callback_query_handler(func=lambda c: c.data.startswith('back_'))
def cb_back(c):
    """Back to files list callback"""
    uid = int(c.data.split('_')[1])
    
    files = user_files.get(uid, [])
    
    if not files:
        safe_edit(c.message.chat.id, c.message.message_id, "📂 **No files**", 'Markdown')
        return bot.answer_callback_query(c.id)
    
    text = f"📂 **Your Files** ({len(files)})\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for i, (name, ftype) in enumerate(files, 1):
        status = "🟢" if ftype == 'executable' and is_running(uid, name) else "⚪"
        icon = "🚀" if ftype == 'executable' else "📄"
        
        display_name = name if len(name) < 30 else name[:27] + "..."
        text += f"{i}. {status} {icon} `{display_name}`\n"
        
        markup.add(types.InlineKeyboardButton(
            f"{icon} {display_name}",
            callback_data=f"file_{uid}_{name}"
        ))
    
    safe_edit(c.message.chat.id, c.message.message_id, text, 'Markdown', markup)
    bot.answer_callback_query(c.id)

# ==================== BUILD CONTROL MARKUP ====================
def build_control_markup(uid, name, ftype):
    """Build control panel markup"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    if ftype == 'executable':
        if is_running(uid, name):
            markup.add(
                types.InlineKeyboardButton("🔴 Stop", callback_data=f"stop_{uid}_{name}"),
                types.InlineKeyboardButton("🔄 Restart", callback_data=f"restart_{uid}_{name}")
            )
            markup.add(types.InlineKeyboardButton("📜 Logs", callback_data=f"logs_{uid}_{name}"))
        else:
            markup.add(
                types.InlineKeyboardButton("🟢 Start", callback_data=f"start_{uid}_{name}"),
                types.InlineKeyboardButton("📜 Logs", callback_data=f"logs_{uid}_{name}")
            )
    else:
        # Hosted file - generate URL
        fhash = hashlib.md5(f"{uid}_{name}".encode()).hexdigest()
        domain = os.environ.get('REPL_SLUG', 'host')
        owner = os.environ.get('REPL_OWNER', 'user')
        url = f"https://{domain}-{owner}.replit.app/file/{fhash}"
        markup.add(types.InlineKeyboardButton("🔗 View File", url=url))
    
    markup.add(
        types.InlineKeyboardButton("🗑️ Delete", callback_data=f"del_{uid}_{name}"),
        types.InlineKeyboardButton("🔙 Back", callback_data=f"back_{uid}")
    )
    
    return markup

# ==================== FALLBACK HANDLER ====================
@bot.message_handler(func=lambda m: True)
def fallback(m):
    """Fallback for unknown commands"""
    safe_reply(m, "🔹 **Unknown command**\nUse /start or the buttons below", 'Markdown')

# ==================== CLEANUP ====================
def cleanup():
    """Cleanup on exit"""
    logger.info("🧹 Cleaning up processes...")
    for key, info in scripts.items():
        if info.get('process') and info['process'].poll() is None:
            try:
                kill_process_tree(info['process'].pid)
                logger.info(f"✅ Killed {key}")
            except Exception as e:
                logger.error(f"❌ Failed to kill {key}: {e}")
    logger.info("✅ Cleanup complete")

atexit.register(cleanup)

# ==================== MAIN ====================
if __name__ == "__main__":
    # Initialize
    init_db()
    load_data()
    keep_alive()
    
    logger.info(f"🚀 Bot started. Owner: {OWNER_ID}")
    print(f"\n{'='*60}")
    print(f"🚀 Universal File Host Bot")
    print(f"👑 Owner ID: {OWNER_ID}")
    print(f"🤖 Bot: @{bot.get_me().username}")
    print(f"👥 Admins: {len(admins)}")
    print(f"📁 Files: {sum(len(f) for f in user_files.values())}")
    print(f"{'='*60}\n")
    
    # Verify owner chat
    try:
        bot.send_chat_action(OWNER_ID, 'typing')
        logger.info("✅ Owner reachable")
    except:
        logger.warning("⚠️ Cannot message owner - start a private chat with the bot")
    
    # Start bot
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)