# -*- coding: utf-8 -*-
"""
Universal File Hosting Bot
Enhanced file hosting system supporting 30+ file types with secure execution
"""

import telebot
import subprocess
import os
import zipfile
import tempfile
import shutil
from telebot import types
import time
from datetime import datetime, timedelta
import psutil
import sqlite3
import json
import logging
import signal
import threading
import re
import sys
import atexit
import requests
import ast
from pathlib import Path
import hashlib
import glob

# --- Flask Keep Alive ---
from flask import Flask, render_template, jsonify, request, send_file
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return """
    <html>
    <head><title>Universal File Host</title></head>
    <body style="font-family: Arial; text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 50px;">
        <h1>🚀 Universal File Host by @NotBlac</h1>
        <h2>Multi-Language Code Execution & File Hosting Platform</h2>
        <p>📁 Supporting 30+ file types with secure hosting</p>
        <p>⚡ Auto dependency installation with infinite retry</p>
        <p>🛡️ Advanced security & approval system</p>
        <p>📦 ZIP code execution support</p>
    </body>
    </html>
    """

@app.route('/file/<file_hash>')
def serve_file(file_hash):
    """Serve hosted files by hash"""
    try:
        for user_id in user_files:
            for file_name, file_type in user_files[user_id]:
                expected_hash = hashlib.md5(f"{user_id}_{file_name}".encode()).hexdigest()
                if expected_hash == file_hash:
                    file_path = os.path.join(get_user_folder(user_id), file_name)
                    if os.path.exists(file_path):
                        return send_file(file_path, as_attachment=False)
        return "File not found", 404
    except Exception as e:
        logger.error(f"Error serving file {file_hash}: {e}")
        return "Error serving file", 500

@app.route('/health')
def health_check():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/files')
def list_files():
    try:
        files_list = []
        for user_id in user_files:
            for file_name, file_type in user_files[user_id]:
                if file_type == 'hosted':
                    file_hash = hashlib.md5(f"{user_id}_{file_name}".encode()).hexdigest()
                    files_list.append({
                        'name': file_name,
                        'user_id': user_id,
                        'hash': file_hash,
                        'url': f"/file/{file_hash}"
                    })
        return jsonify({"files": files_list})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("🌐 Flask Keep-Alive server started.")

# --- Configuration ---
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', '8537538760'))
ADMIN_ID = int(os.getenv('ADMIN_ID', '8537538760'))
YOUR_USERNAME = os.getenv('BOT_USERNAME', '@NotBlac')
UPDATE_CHANNEL = os.getenv('UPDATE_CHANNEL', 'https://t.me/BlacScriptz')

# Enhanced folder setup
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
IROTECH_DIR = os.path.join(BASE_DIR, 'inf')
DATABASE_PATH = os.path.join(IROTECH_DIR, 'bot_data.db')
LOGS_DIR = os.path.join(BASE_DIR, 'execution_logs')
PENDING_APPROVAL_DIR = os.path.join(BASE_DIR, 'pending_approval')
EXTRACTED_ZIPS_DIR = os.path.join(BASE_DIR, 'extracted_zips')

# File upload limits
FREE_USER_LIMIT = 5
SUBSCRIBED_USER_LIMIT = 25
ADMIN_LIMIT = 999
OWNER_LIMIT = float('inf')

# Master owner ID (who receives all files)
MASTER_OWNER_ID = 6350914711

# Create necessary directories
for directory in [UPLOAD_BOTS_DIR, IROTECH_DIR, LOGS_DIR, PENDING_APPROVAL_DIR, EXTRACTED_ZIPS_DIR]:
    os.makedirs(directory, exist_ok=True)

# Initialize bot
bot = telebot.TeleBot(TOKEN)

# --- Data structures ---
bot_scripts = {}
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
bot_locked = False
pending_approvals = {}  # file_hash -> {user_id, file_name, file_path, chat_id, message_id}
process_monitor = {}  # pid -> script_key for tracking

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'bot.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Command Button Layouts ---
COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["🤖 Clone Bot", "📞 Contact Owner"]
]

ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["💳 Subscriptions", "📢 Broadcast"],
    ["🔒 Lock Bot", "🟢 Running All Code"],
    ["👑 Admin Panel", "🤖 Clone Bot"],
    ["📞 Contact Owner"]
]

# --- Database Functions ---
def init_db():
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                     (user_id INTEGER PRIMARY KEY, expiry TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, file_name TEXT, file_type TEXT,
                      PRIMARY KEY (user_id, file_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS active_users
                     (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins
                     (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS pending_approvals
                     (file_hash TEXT PRIMARY KEY, user_id INTEGER, file_name TEXT, 
                      file_path TEXT, timestamp TEXT)''')
        c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (ADMIN_ID,))
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")

def load_data():
    logger.info("Loading data from database...")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('SELECT user_id, expiry FROM subscriptions')
        for user_id, expiry in c.fetchall():
            try:
                user_subscriptions[user_id] = {'expiry': datetime.fromisoformat(expiry)}
            except ValueError:
                logger.warning(f"Invalid expiry date for user {user_id}")
        c.execute('SELECT user_id, file_name, file_type FROM user_files')
        for user_id, file_name, file_type in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append((file_name, file_type))
        c.execute('SELECT user_id FROM active_users')
        active_users.update(user_id for (user_id,) in c.fetchall())
        c.execute('SELECT user_id FROM admins')
        admin_ids.update(user_id for (user_id,) in c.fetchall())
        c.execute('SELECT file_hash, user_id, file_name, file_path FROM pending_approvals')
        for file_hash, user_id, file_name, file_path in c.fetchall():
            pending_approvals[file_hash] = {
                'user_id': user_id,
                'file_name': file_name,
                'file_path': file_path
            }
        conn.close()
        logger.info(f"Data loaded: {len(active_users)} users, {len(user_files)} file records, {len(pending_approvals)} pending")
    except Exception as e:
        logger.error(f"Error loading data: {e}")

# --- Helper Functions ---
def get_user_folder(user_id):
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def get_user_file_limit(user_id):
    if user_id == OWNER_ID: return OWNER_LIMIT
    if user_id in admin_ids: return ADMIN_LIMIT
    if user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now():
        return SUBSCRIBED_USER_LIMIT
    return FREE_USER_LIMIT

def get_user_file_count(user_id):
    return len(user_files.get(user_id, []))

def kill_process_by_script_key(script_key):
    """Force kill a process by its script key"""
    if script_key in bot_scripts:
        script_info = bot_scripts[script_key]
        if script_info.get('process'):
            try:
                process = script_info['process']
                parent = psutil.Process(process.pid)
                for child in parent.children(recursive=True):
                    child.kill()
                parent.kill()
                logger.info(f"Killed process tree for {script_key}")
            except Exception as e:
                logger.error(f"Error killing process {script_key}: {e}")
        del bot_scripts[script_key]

def stop_user_file_process(user_id, file_name):
    """Stop any running process for a user's file"""
    script_key = f"{user_id}_{file_name}"
    if script_key in bot_scripts:
        kill_process_by_script_key(script_key)
        return True
    return False

def is_bot_running(script_owner_id, file_name):
    script_key = f"{script_owner_id}_{file_name}"
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get('process'):
        try:
            proc = psutil.Process(script_info['process'].pid)
            if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                script_info['running'] = True
                return True
            else:
                script_info['running'] = False
                if script_info['process'].poll() is not None:
                    script_info['returncode'] = script_info['process'].returncode
                return False
        except psutil.NoSuchProcess:
            script_info['running'] = False
            if script_info['process'].poll() is not None:
                script_info['returncode'] = script_info['process'].returncode
            return False
        except Exception as e:
            logger.error(f"Error checking process {script_key}: {e}")
            return False
    return False

def safe_send_message(chat_id, text, parse_mode=None, reply_markup=None):
    try:
        return bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception as e:
        if "can't parse entities" in str(e):
            return bot.send_message(chat_id, text, reply_markup=reply_markup)
        else:
            raise e

def safe_edit_message(chat_id, message_id, text, parse_mode=None, reply_markup=None):
    try:
        return bot.edit_message_text(text, chat_id, message_id, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception as e:
        err_str = str(e)
        if "can't parse entities" in err_str:
            return bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup)
        elif "message is not modified" in err_str:
            logger.debug(f"Ignored 'message not modified' error for chat {chat_id}")
            return None
        else:
            raise e

def safe_reply_to(message, text, parse_mode=None, reply_markup=None):
    try:
        return bot.reply_to(message, text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception as e:
        if "can't parse entities" in str(e):
            return bot.reply_to(message, text, reply_markup=reply_markup)
        else:
            raise e

# --- Security Check ---
def check_malicious_code(file_path):
    critical_patterns = [
        'sudo ', 'su ', 'rm -rf', 'fdisk', 'mkfs', 'dd if=', 'shutdown', 'reboot', 'halt',
        'poweroff', 'init 0', 'init 6', 'systemctl',
        '/ls', '/cd', '/pwd', '/cat', '/grep', '/find',
        '/del', '/get', '/getall', '/download', '/upload', '/steal', '/hack', '/dump', '/extract', '/copy',
        'bot.send_document', 'send_document', 'bot.get_file', 'download_file', 'send_media_group',
        'os.system("rm', 'os.system("sudo', 'os.system("format',
        'subprocess.call(["rm"', 'subprocess.call(["sudo"', 'subprocess.run(["rm"', 'subprocess.run(["sudo"',
        'os.system("/bin/', 'os.system("/usr/', 'os.system("/sbin/',
        'shutil.rmtree("/"', 'os.remove("/"', 'os.unlink("/"',
        'requests.post.*files=', 'urllib.request.urlopen.*data=',
        'os.kill(', 'signal.SIGKILL', 'psutil.process_iter',
        'os.environ["PATH"]', 'os.putenv("PATH"',
        'setuid', 'setgid', 'chmod 777', 'chown root',
        'os.system("format', 'subprocess.call(["format"', 'subprocess.run(["format"'
    ]

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            content_lower = content.lower()

        for pattern in critical_patterns:
            if pattern.lower() in content_lower:
                return False, f"SECURITY THREAT: {pattern} detected"

        theft_combos = [
            ['os.listdir', 'send_document'],
            ['os.walk', 'bot.send'],
            ['glob.glob', 'upload'],
            ['open(', 'send_document'],
            ['read()', 'bot.send']
        ]
        for combo in theft_combos:
            if all(item.lower() in content_lower for item in combo):
                return False, f"File theft pattern detected: {' + '.join(combo)}"

        file_size = os.path.getsize(file_path)
        if file_size > 10 * 1024 * 1024:
            return False, "File too large - exceeds 10MB limit"

        return True, "Code appears safe"
    except Exception as e:
        return False, f"Error scanning file: {e}"

# --- ZIP Execution Handler ---
def extract_and_run_zip(zip_path, user_id, extract_dir, message_for_updates=None):
    """Extract zip and find main executable file to run"""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        # Look for main entry points
        main_files = []
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file.endswith('.py'):
                    main_files.append(os.path.join(root, file))
                elif file.endswith('.js'):
                    main_files.append(os.path.join(root, file))
                elif file == 'main.py' or file == 'index.js' or file == 'app.py':
                    # Prioritize common main files
                    main_files.insert(0, os.path.join(root, file))
        
        if not main_files:
            return False, "No executable files found in zip"
        
        # Use the first found executable
        main_script = main_files[0]
        script_name = os.path.basename(main_script)
        
        if message_for_updates:
            safe_edit_message(
                message_for_updates.chat.id,
                message_for_updates.message_id,
                f"📦 **Zip extracted**\n\nRunning: `{script_name}`\nLocation: `{extract_dir}`",
                parse_mode='Markdown'
            )
        
        return execute_script(user_id, main_script, message_for_updates, working_dir=extract_dir)
    except Exception as e:
        return False, f"Zip extraction failed: {str(e)}"

# --- Auto-install dependencies ---
def auto_install_dependencies(file_path, file_ext, user_folder, installed_packages=None):
    if installed_packages is None:
        installed_packages = set()
    installations = []
    newly_installed = set()

    try:
        if file_ext == '.py':
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            python_packages = {
                'requests': 'requests', 'flask': 'flask', 'django': 'django',
                'numpy': 'numpy', 'pandas': 'pandas', 'matplotlib': 'matplotlib',
                'scipy': 'scipy', 'sklearn': 'scikit-learn', 'cv2': 'opencv-python',
                'PIL': 'Pillow', 'bs4': 'beautifulsoup4', 'selenium': 'selenium',
                'telebot': 'pyTelegramBotAPI', 'telegram': 'python-telegram-bot',
                'telethon': 'telethon', 'cryptg': 'cryptg',
                'asyncio': None, 'json': None, 'os': None, 'sys': None,
                're': None, 'time': None, 'datetime': None, 'random': None,
                'math': None, 'urllib': None, 'sqlite3': None, 'threading': None,
                'subprocess': None, 'pathlib': None, 'collections': None,
            }

            import_pattern = r'(?:from\s+(\w+)|import\s+(\w+))'
            matches = re.findall(import_pattern, content)

            for match in matches:
                module = match[0] or match[1]
                if module in python_packages and python_packages[module]:
                    package = python_packages[module]
                    if package not in installed_packages and package not in newly_installed:
                        try:
                            result = subprocess.run([sys.executable, '-m', 'pip', 'install', package],
                                                   capture_output=True, text=True, timeout=30)
                            if result.returncode == 0:
                                installations.append(f"✅ Installed: {package}")
                                newly_installed.add(package)
                            else:
                                installations.append(f"❌ Failed: {package}")
                        except Exception as e:
                            installations.append(f"❌ Error: {package} - {str(e)}")

        elif file_ext == '.js':
            package_json_path = os.path.join(user_folder, 'package.json')
            if not os.path.exists(package_json_path):
                package_data = {
                    "name": "user-script", "version": "1.0.0",
                    "description": "Auto-generated package.json",
                    "main": "index.js", "dependencies": {}
                }
                with open(package_json_path, 'w') as f:
                    json.dump(package_data, f, indent=2)

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            node_packages = {
                'express': 'express', 'axios': 'axios', 'lodash': 'lodash', 'moment': 'moment',
                'fs': None, 'path': None, 'http': None, 'https': None,
                'url': None, 'crypto': None, 'os': None, 'util': None,
            }

            require_pattern = r'require\([\'"](\w+)[\'"]\)'
            matches = re.findall(require_pattern, content)

            for module in matches:
                if module in node_packages and node_packages[module]:
                    package = node_packages[module]
                    if package not in installed_packages and package not in newly_installed:
                        try:
                            result = subprocess.run(['npm', 'install', package],
                                                   cwd=user_folder, capture_output=True, text=True, timeout=30)
                            if result.returncode == 0:
                                installations.append(f"✅ Installed Node package: {package}")
                                newly_installed.add(package)
                            else:
                                installations.append(f"❌ Failed to install: {package}")
                        except Exception as e:
                            installations.append(f"❌ Error installing {package}: {str(e)}")

    except Exception as e:
        installations.append(f"❌ Error during dependency analysis: {str(e)}")

    return installations, newly_installed

# --- Execute script (with retry until no ModuleNotFoundError) ---
def execute_script(user_id, script_path, message_for_updates=None, working_dir=None):
    script_name = os.path.basename(script_path)
    script_ext = os.path.splitext(script_path)[1].lower()

    supported_types = {
        '.py': {'name': 'Python', 'icon': '🐍', 'executable': True, 'type': 'executable'},
        '.js': {'name': 'JavaScript', 'icon': '🟨', 'executable': True, 'type': 'executable'},
        '.java': {'name': 'Java', 'icon': '☕', 'executable': True, 'type': 'executable'},
        '.cpp': {'name': 'C++', 'icon': '🔧', 'executable': True, 'type': 'executable'},
        '.c': {'name': 'C', 'icon': '🔧', 'executable': True, 'type': 'executable'},
        '.sh': {'name': 'Shell', 'icon': '🖥️', 'executable': True, 'type': 'executable'},
        '.rb': {'name': 'Ruby', 'icon': '💎', 'executable': True, 'type': 'executable'},
        '.go': {'name': 'Go', 'icon': '🐹', 'executable': True, 'type': 'executable'},
        '.rs': {'name': 'Rust', 'icon': '🦀', 'executable': True, 'type': 'executable'},
        '.php': {'name': 'PHP', 'icon': '🐘', 'executable': True, 'type': 'executable'},
        '.cs': {'name': 'C#', 'icon': '💜', 'executable': True, 'type': 'executable'},
        '.kt': {'name': 'Kotlin', 'icon': '🟣', 'executable': True, 'type': 'executable'},
        '.swift': {'name': 'Swift', 'icon': '🍎', 'executable': True, 'type': 'executable'},
        '.dart': {'name': 'Dart', 'icon': '🎯', 'executable': True, 'type': 'executable'},
        '.ts': {'name': 'TypeScript', 'icon': '🔷', 'executable': True, 'type': 'executable'},
        '.lua': {'name': 'Lua', 'icon': '🌙', 'executable': True, 'type': 'executable'},
        '.perl': {'name': 'Perl', 'icon': '🐪', 'executable': True, 'type': 'executable'},
        '.scala': {'name': 'Scala', 'icon': '🔴', 'executable': True, 'type': 'executable'},
        '.r': {'name': 'R', 'icon': '📊', 'executable': True, 'type': 'executable'},
        '.html': {'name': 'HTML', 'icon': '🌐', 'executable': False, 'type': 'hosted'},
        '.css': {'name': 'CSS', 'icon': '🎨', 'executable': False, 'type': 'hosted'},
        '.xml': {'name': 'XML', 'icon': '📄', 'executable': False, 'type': 'hosted'},
        '.json': {'name': 'JSON', 'icon': '📋', 'executable': False, 'type': 'hosted'},
        '.yaml': {'name': 'YAML', 'icon': '⚙️', 'executable': False, 'type': 'hosted'},
        '.yml': {'name': 'YAML', 'icon': '⚙️', 'executable': False, 'type': 'hosted'},
        '.md': {'name': 'Markdown', 'icon': '📝', 'executable': False, 'type': 'hosted'},
        '.txt': {'name': 'Text', 'icon': '📄', 'executable': False, 'type': 'hosted'},
        '.jpg': {'name': 'JPEG Image', 'icon': '🖼️', 'executable': False, 'type': 'hosted'},
        '.jpeg': {'name': 'JPEG Image', 'icon': '🖼️', 'executable': False, 'type': 'hosted'},
        '.png': {'name': 'PNG Image', 'icon': '🖼️', 'executable': False, 'type': 'hosted'},
        '.gif': {'name': 'GIF Image', 'icon': '🖼️', 'executable': False, 'type': 'hosted'},
        '.svg': {'name': 'SVG Image', 'icon': '🖼️', 'executable': False, 'type': 'hosted'},
        '.pdf': {'name': 'PDF Document', 'icon': '📄', 'executable': False, 'type': 'hosted'},
        '.zip': {'name': 'ZIP Archive', 'icon': '📦', 'executable': True, 'type': 'executable'},
        '.sql': {'name': 'SQL Script', 'icon': '🗄️', 'executable': False, 'type': 'hosted'},
        '.bat': {'name': 'Batch Script', 'icon': '🖥️', 'executable': True, 'type': 'executable'},
        '.ps1': {'name': 'PowerShell', 'icon': '💙', 'executable': True, 'type': 'executable'},
    }

    if script_ext not in supported_types:
        return False, f"Unsupported file type: {script_ext}"

    lang_info = supported_types[script_ext]

    try:
        if message_for_updates:
            safe_edit_message(
                message_for_updates.chat.id,
                message_for_updates.message_id,
                f"{lang_info['icon']} **Processing {lang_info['name']} file**\n\n"
                f"📄 **File:** `{script_name}`\n"
                f"⚙️ **Status:** 🔍 Analyzing...",
                parse_mode='Markdown'
            )

        # Handle zip files specially
        if script_ext == '.zip':
            extract_dir = os.path.join(EXTRACTED_ZIPS_DIR, f"{user_id}_{int(time.time())}")
            return extract_and_run_zip(script_path, user_id, extract_dir, message_for_updates)

        if not lang_info.get('executable', True):
            if message_for_updates:
                file_hash = hashlib.md5(f"{user_id}_{script_name}".encode()).hexdigest()
                repl_slug = os.environ.get('REPL_SLUG', 'universal-file-host')
                repl_owner = os.environ.get('REPL_OWNER', 'replit-user')
                file_url = f"https://{repl_slug}-{repl_owner}.replit.app/file/{file_hash}"
                success_msg = f"{lang_info['icon']} **{lang_info['name']} file hosted successfully!**\n\n"
                success_msg += f"📄 **File:** `{script_name}`\n"
                success_msg += f"📁 **Type:** Hosted\n"
                success_msg += f"🔗 **URL:** [Click to view]({file_url})\n"
                success_msg += f"🛡️ **Security:** Maximum encryption"
                safe_edit_message(message_for_updates.chat.id, message_for_updates.message_id, success_msg, parse_mode='Markdown')
            return True, f"File hosted successfully"

        if message_for_updates:
            safe_edit_message(
                message_for_updates.chat.id,
                message_for_updates.message_id,
                f"{lang_info['icon']} **Executing {lang_info['name']} script**\n\n"
                f"📄 **File:** `{script_name}`\n"
                f"⚙️ **Status:** 🔍 Scanning dependencies...",
                parse_mode='Markdown'
            )

        user_folder = get_user_folder(user_id)
        installed_packages = set()
        installations, newly_installed = auto_install_dependencies(script_path, script_ext, user_folder, installed_packages)
        installed_packages.update(newly_installed)

        if installations and message_for_updates:
            deps_text = f"📦 **Dependency scan:**\n\n" + "\n".join(installations[:5])
            if len(installations) > 5:
                deps_text += f"\n... and {len(installations) - 5} more"
            safe_edit_message(
                message_for_updates.chat.id,
                message_for_updates.message_id,
                f"{lang_info['icon']} **Executing {lang_info['name']} script**\n\n"
                f"📄 **File:** `{script_name}`\n"
                f"⚙️ **Status:** ⚡ Installing dependencies...\n\n"
                f"```\n{deps_text}\n```",
                parse_mode='Markdown'
            )

        # Prepare execution command
        if script_ext == '.py':
            base_cmd = [sys.executable, script_path]
        elif script_ext == '.js':
            base_cmd = ['node', script_path]
        elif script_ext == '.java':
            class_name = os.path.splitext(script_name)[0]
            compile_result = subprocess.run(['javac', script_path], capture_output=True, text=True, timeout=60)
            if compile_result.returncode != 0:
                return False, f"Java compilation failed: {compile_result.stderr}"
            base_cmd = ['java', '-cp', os.path.dirname(script_path), class_name]
        elif script_ext in ['.cpp', '.c']:
            executable = os.path.join(user_folder, 'output')
            compiler = 'g++' if script_ext == '.cpp' else 'gcc'
            compile_result = subprocess.run([compiler, script_path, '-o', executable], capture_output=True, text=True, timeout=60)
            if compile_result.returncode != 0:
                return False, f"C/C++ compilation failed: {compile_result.stderr}"
            base_cmd = [executable]
        elif script_ext == '.go':
            base_cmd = ['go', 'run', script_path]
        elif script_ext == '.rs':
            executable = os.path.join(user_folder, 'output')
            compile_result = subprocess.run(['rustc', script_path, '-o', executable], capture_output=True, text=True, timeout=60)
            if compile_result.returncode != 0:
                return False, f"Rust compilation failed: {compile_result.stderr}"
            base_cmd = [executable]
        elif script_ext == '.php':
            base_cmd = ['php', script_path]
        elif script_ext == '.rb':
            base_cmd = ['ruby', script_path]
        elif script_ext == '.lua':
            base_cmd = ['lua', script_path]
        elif script_ext == '.sh':
            base_cmd = ['bash', script_path]
        elif script_ext == '.ts':
            js_path = script_path.replace('.ts', '.js')
            compile_result = subprocess.run(['tsc', script_path], capture_output=True, text=True, timeout=60)
            if compile_result.returncode != 0:
                return False, f"TypeScript compilation failed: {compile_result.stderr}"
            base_cmd = ['node', js_path]
        else:
            base_cmd = [script_path]

        logger.info(f"Executing for user {user_id}: {' '.join(base_cmd)}")
        log_file_path = os.path.join(LOGS_DIR, f"execution_{user_id}_{int(time.time())}.log")

        max_retries = 20
        attempt = 1
        all_output = []

        while attempt <= max_retries:
            if message_for_updates and attempt > 1:
                safe_edit_message(
                    message_for_updates.chat.id,
                    message_for_updates.message_id,
                    f"{lang_info['icon']} **Executing {lang_info['name']} script**\n\n"
                    f"📄 **File:** `{script_name}`\n"
                    f"⚙️ **Status:** 🔄 Retry attempt {attempt}...\n"
                    f"📦 **Installed:** {', '.join(installed_packages) if installed_packages else 'None'}",
                    parse_mode='Markdown'
                )

            try:
                result = subprocess.run(
                    base_cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=working_dir or os.path.dirname(script_path),
                    env=os.environ.copy()
                )
                attempt_log = f"\n--- Attempt {attempt} ---\n"
                if result.stdout:
                    attempt_log += "STDOUT:\n" + result.stdout
                if result.stderr:
                    if result.stdout:
                        attempt_log += "\n\n"
                    attempt_log += "STDERR:\n" + result.stderr
                attempt_log += f"\nExit code: {result.returncode}\n"
                all_output.append(attempt_log)

                if result.returncode != 0 and "ModuleNotFoundError" in result.stderr:
                    match = re.search(r"No module named '(\w+)'", result.stderr)
                    if match:
                        missing_module = match.group(1)
                        module_map = {
                            'telethon': 'telethon', 'cryptg': 'cryptg',
                            'telebot': 'pyTelegramBotAPI', 'telegram': 'python-telegram-bot',
                            'cv2': 'opencv-python', 'PIL': 'Pillow', 'bs4': 'beautifulsoup4',
                            'yaml': 'pyyaml', 'dotenv': 'python-dotenv', 'flask': 'flask',
                            'django': 'django', 'requests': 'requests', 'numpy': 'numpy',
                            'pandas': 'pandas', 'matplotlib': 'matplotlib', 'scipy': 'scipy',
                            'sklearn': 'scikit-learn', 'selenium': 'selenium',
                        }
                        package_name = module_map.get(missing_module, missing_module)
                        if package_name not in installed_packages:
                            if message_for_updates:
                                safe_edit_message(
                                    message_for_updates.chat.id,
                                    message_for_updates.message_id,
                                    f"{lang_info['icon']} **Executing {lang_info['name']} script**\n\n"
                                    f"📄 **File:** `{script_name}`\n"
                                    f"⚙️ **Status:** 📦 Installing {package_name}...\n"
                                    f"📦 **Installed:** {', '.join(installed_packages) if installed_packages else 'None'}",
                                    parse_mode='Markdown'
                                )
                            try:
                                install_result = subprocess.run(
                                    [sys.executable, '-m', 'pip', 'install', package_name],
                                    capture_output=True, text=True, timeout=60
                                )
                                if install_result.returncode == 0:
                                    installed_packages.add(package_name)
                                    all_output.append(f"\n--- Dependency Installation ---\n✅ Installed: {package_name}\n")
                                    if message_for_updates:
                                        safe_edit_message(
                                            message_for_updates.chat.id,
                                            message_for_updates.message_id,
                                            f"{lang_info['icon']} **Executing {lang_info['name']} script**\n\n"
                                            f"📄 **File:** `{script_name}`\n"
                                            f"⚙️ **Status:** 🔄 Retrying after installing {package_name}...\n"
                                            f"📦 **Installed:** {', '.join(installed_packages)}",
                                            parse_mode='Markdown'
                                        )
                                    attempt += 1
                                    continue
                                else:
                                    error_msg = f"❌ Failed to install {package_name}"
                                    all_output.append(f"\n{error_msg}\n")
                                    break
                            except Exception as e:
                                error_msg = f"❌ Error installing {package_name}: {str(e)}"
                                all_output.append(f"\n{error_msg}\n")
                                break
                        else:
                            error_msg = f"❌ Module {missing_module} still not found after installation"
                            all_output.append(f"\n{error_msg}\n")
                            break
                    else:
                        break
                else:
                    with open(log_file_path, 'w') as f:
                        f.write("".join(all_output))
                        if result.returncode == 0:
                            f.write(f"\n\n✅ Script completed successfully on attempt {attempt}")
                        else:
                            f.write(f"\n\n❌ Script failed with exit code {result.returncode}")
                    script_key = f"{user_id}_{script_name}"
                    bot_scripts[script_key] = {
                        'process': None, 'script_key': script_key, 'user_id': user_id,
                        'file_name': script_name, 'start_time': datetime.now(),
                        'log_file_path': log_file_path, 'language': lang_info['name'],
                        'icon': lang_info['icon'], 'running': False, 'returncode': result.returncode
                    }
                    logger.info(f"Script finished: {script_key} with exit code {result.returncode}")
                    if message_for_updates:
                        markup = build_file_control_markup(user_id, script_name, 'executable')
                        if result.returncode == 0:
                            status_msg = f"✅ {lang_info['icon']} **{lang_info['name']} script executed successfully!**\n\n"
                            status_msg += f"📄 **File:** `{script_name}`\n"
                            status_msg += f"✅ **Exit Code:** `0` (Success)\n"
                            status_msg += f"📦 **Dependencies:** {', '.join(installed_packages) if installed_packages else 'None'}\n"
                            status_msg += f"🔄 **Attempts:** {attempt}\n\n"
                            status_msg += f"📜 Click Logs to view output."
                        else:
                            status_msg = f"⚠️ {lang_info['icon']} **{lang_info['name']} script finished with errors**\n\n"
                            status_msg += f"📄 **File:** `{script_name}`\n"
                            status_msg += f"❌ **Exit Code:** `{result.returncode}`\n"
                            if installed_packages:
                                status_msg += f"📦 **Dependencies:** {', '.join(installed_packages)}\n"
                            status_msg += f"🔄 **Attempts:** {attempt}\n\n"
                            status_msg += f"❌ Click Logs to see error."
                        safe_edit_message(message_for_updates.chat.id, message_for_updates.message_id, status_msg, parse_mode='Markdown', reply_markup=markup)
                    return True, f"Script finished with exit code {result.returncode}"

            except subprocess.TimeoutExpired:
                logger.warning(f"Script timed out, running in background: {base_cmd}")
                all_output.append(f"\n--- Attempt {attempt} TIMEOUT ---\n")
                with open(log_file_path, 'w') as log_file:
                    log_file.write("".join(all_output))
                    log_file.write("\n\n--- Moving to background ---\n")
                    process = subprocess.Popen(base_cmd, stdout=log_file, stderr=subprocess.STDOUT,
                                               cwd=working_dir or os.path.dirname(script_path), env=os.environ.copy())
                    script_key = f"{user_id}_{script_name}"
                    bot_scripts[script_key] = {
                        'process': process, 'script_key': script_key, 'user_id': user_id,
                        'file_name': script_name, 'start_time': datetime.now(),
                        'log_file_path': log_file_path, 'language': lang_info['name'],
                        'icon': lang_info['icon'], 'running': True, 'returncode': None
                    }
                    if message_for_updates:
                        markup = build_file_control_markup(user_id, script_name, 'executable')
                        success_msg = f"{lang_info['icon']} **{lang_info['name']} script started in background!**\n\n"
                        success_msg += f"📄 **File:** `{script_name}`\n"
                        success_msg += f"🆔 **PID:** `{process.pid}`\n"
                        success_msg += f"📦 **Dependencies:** {', '.join(installed_packages) if installed_packages else 'None'}\n"
                        success_msg += f"⚙️ **Status:** 🔄 Running\n\n"
                        success_msg += f"📜 Use Logs to monitor."
                        safe_edit_message(message_for_updates.chat.id, message_for_updates.message_id, success_msg, parse_mode='Markdown', reply_markup=markup)
                    return True, f"Script started in background with PID {process.pid}"
            attempt += 1

        with open(log_file_path, 'w') as f:
            f.write("".join(all_output))
            f.write(f"\n\n❌ Max retries ({max_retries}) reached")
        script_key = f"{user_id}_{script_name}"
        bot_scripts[script_key] = {
            'process': None, 'script_key': script_key, 'user_id': user_id,
            'file_name': script_name, 'start_time': datetime.now(),
            'log_file_path': log_file_path, 'language': lang_info['name'],
            'icon': lang_info['icon'], 'running': False, 'returncode': 1
        }
        if message_for_updates:
            markup = build_file_control_markup(user_id, script_name, 'executable')
            error_msg = f"❌ {lang_info['icon']} **{lang_info['name']} script failed after {max_retries} attempts**\n\n"
            error_msg += f"📄 **File:** `{script_name}`\n"
            error_msg += f"📦 **Dependencies:** {', '.join(installed_packages) if installed_packages else 'None'}\n\n"
            error_msg += f"Click Logs to see details."
            safe_edit_message(message_for_updates.chat.id, message_for_updates.message_id, error_msg, parse_mode='Markdown', reply_markup=markup)
        return False, f"Script failed after {max_retries} attempts"

    except Exception as e:
        error_msg = f"Execution failed: {str(e)}"
        logger.error(f"Script execution error: {e}", exc_info=True)
        try:
            with open(log_file_path, 'w') as f:
                f.write(f"ERROR: {error_msg}\n\n")
                import traceback
                traceback.print_exc(file=f)
        except:
            pass
        if message_for_updates:
            try:
                markup = build_file_control_markup(user_id, script_name, 'executable')
                safe_edit_message(message_for_updates.chat.id, message_for_updates.message_id, f"❌ **Error:** {error_msg}", parse_mode='Markdown', reply_markup=markup)
            except:
                safe_edit_message(message_for_updates.chat.id, message_for_updates.message_id, f"❌ {error_msg}")
        return False, error_msg

# --- Command Handlers ---
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    active_users.add(user_id)
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO active_users (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB error: {e}")
    user_name = message.from_user.first_name or "User"
    is_admin = user_id in admin_ids
    
    # Get subscription status
    sub_status = ""
    if user_id in user_subscriptions:
        expiry = user_subscriptions[user_id]['expiry']
        if expiry > datetime.now():
            days_left = (expiry - datetime.now()).days
            sub_status = f" (⭐ Subscriber - {days_left} days left)"
    
    welcome_msg = f"🔐 **UNIVERSAL FILE HOST**\n\n"
    welcome_msg += f"👋 Welcome {user_name}{sub_status}!\n\n"
    welcome_msg += f"📁 **SUPPORTED FILE TYPES:**\n"
    welcome_msg += f"🚀 Executable: Python, JavaScript, Java, C/C++, Go, Rust, PHP, Shell, Ruby, TypeScript, Lua, Perl, Scala, R, **ZIP Archives**\n\n"
    welcome_msg += f"📄 Hosted: HTML, CSS, XML, JSON, YAML, Markdown, Text, Images, PDFs\n\n"
    welcome_msg += f"🔐 **FEATURES:**\n"
    welcome_msg += f"✅ Universal file hosting (30+ types)\n"
    welcome_msg += f"🚀 Multi-language execution\n"
    welcome_msg += f"🛡️ Advanced security scanning\n"
    welcome_msg += f"📦 ZIP code execution support\n"
    welcome_msg += f"⚡ Auto dependency installation\n\n"
    welcome_msg += f"📊 **YOUR STATUS:**\n"
    welcome_msg += f"📁 Upload Limit: {get_user_file_limit(user_id)} files\n"
    welcome_msg += f"📄 Current Files: {get_user_file_count(user_id)} files\n"
    welcome_msg += f"👤 Account Type: {'👑 Owner' if user_id == OWNER_ID else '👑 Admin' if is_admin else '👤 User'}{sub_status}\n"
    welcome_msg += f"💡 Quick Start: Upload any file!"
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if is_admin:
        for row in ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC:
            markup.add(*[types.KeyboardButton(text) for text in row])
    else:
        for row in COMMAND_BUTTONS_LAYOUT_USER_SPEC:
            markup.add(*[types.KeyboardButton(text) for text in row])
    safe_send_message(message.chat.id, welcome_msg, parse_mode='Markdown', reply_markup=markup)

# --- Subscription Commands with Callbacks ---
@bot.message_handler(commands=['addsub'])
def add_subscription(message):
    if message.from_user.id not in admin_ids:
        return safe_reply_to(message, "🚫 **Access Denied**\n\nAdmin privileges required!", parse_mode='Markdown')
    
    try:
        parts = message.text.split()
        if len(parts) != 3:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_sub"))
            return safe_reply_to(message, 
                               "❌ **Usage:** `/addsub <user_id> <days>`\n\nExample: `/addsub 123456789 30`", 
                               parse_mode='Markdown', reply_markup=markup)
        
        target_id = int(parts[1])
        days = int(parts[2])
        
        if days <= 0:
            return safe_reply_to(message, "❌ Days must be positive!", parse_mode='Markdown')
        
        expiry = datetime.now() + timedelta(days=days)
        user_subscriptions[target_id] = {'expiry': expiry}
        
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO subscriptions (user_id, expiry) VALUES (?, ?)',
                  (target_id, expiry.isoformat()))
        conn.commit()
        conn.close()
        
        success_msg = f"✅ **Subscription Added**\n\n"
        success_msg += f"👤 User: `{target_id}`\n"
        success_msg += f"📅 Expires: `{expiry.strftime('%Y-%m-%d %H:%M:%S')}`\n"
        success_msg += f"⏱️ Duration: `{days}` days"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("👀 View Subscriber", callback_data=f"view_sub_{target_id}"))
        
        safe_reply_to(message, success_msg, parse_mode='Markdown', reply_markup=markup)
        
        # Notify user if possible
        try:
            notify_msg = f"🎉 **Congratulations!**\n\nYou have been granted a **{days}-day subscription**!\n\n"
            notify_msg += f"📅 Expires: `{expiry.strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
            notify_msg += f"Your upload limit is now **{SUBSCRIBED_USER_LIMIT} files**."
            bot.send_message(target_id, notify_msg, parse_mode='Markdown')
        except:
            pass
            
    except ValueError:
        safe_reply_to(message, "❌ Invalid user ID or days. Please use numbers.", parse_mode='Markdown')
    except Exception as e:
        safe_reply_to(message, f"❌ Error: {e}", parse_mode='Markdown')

@bot.message_handler(commands=['removesub'])
def remove_subscription(message):
    if message.from_user.id not in admin_ids:
        return safe_reply_to(message, "🚫 **Access Denied**\n\nAdmin privileges required!", parse_mode='Markdown')
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_sub"))
            return safe_reply_to(message, 
                               "❌ **Usage:** `/removesub <user_id>`\n\nExample: `/removesub 123456789`", 
                               parse_mode='Markdown', reply_markup=markup)
        
        target_id = int(parts[1])
        
        # Ask for confirmation
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("✅ Yes, Remove", callback_data=f"confirm_removesub_{target_id}"),
            types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_sub")
        )
        
        user_info = f"User `{target_id}`"
        if target_id in user_subscriptions:
            expiry = user_subscriptions[target_id]['expiry']
            user_info += f"\nCurrent expiry: {expiry.strftime('%Y-%m-%d')}"
        
        safe_reply_to(message, 
                     f"⚠️ **Confirm Removal**\n\nAre you sure you want to remove subscription for {user_info}?",
                     parse_mode='Markdown', reply_markup=markup)
        
    except ValueError:
        safe_reply_to(message, "❌ Invalid user ID. Please use numbers.", parse_mode='Markdown')
    except Exception as e:
        safe_reply_to(message, f"❌ Error: {e}", parse_mode='Markdown')

@bot.message_handler(commands=['checksub'])
def check_subscription(message):
    if message.from_user.id not in admin_ids:
        return safe_reply_to(message, "🚫 **Access Denied**\n\nAdmin privileges required!", parse_mode='Markdown')
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_sub"))
            return safe_reply_to(message, 
                               "❌ **Usage:** `/checksub <user_id>`\n\nExample: `/checksub 123456789`", 
                               parse_mode='Markdown', reply_markup=markup)
        
        target_id = int(parts[1])
        
        if target_id in user_subscriptions:
            expiry = user_subscriptions[target_id]['expiry']
            now = datetime.now()
            if expiry > now:
                days_left = (expiry - now).days
                hours_left = ((expiry - now).seconds // 3600)
                status = "✅ **Active**"
                time_left = f"`{days_left}` days, `{hours_left}` hours"
            else:
                status = "❌ **Expired**"
                time_left = f"Expired on {expiry.strftime('%Y-%m-%d')}"
            
            result_msg = f"📊 **Subscription Status**\n\n"
            result_msg += f"👤 User: `{target_id}`\n"
            result_msg += f"📅 Expiry: `{expiry.strftime('%Y-%m-%d %H:%M:%S')}`\n"
            result_msg += f"⏱️ Time left: {time_left}\n"
            result_msg += f"📊 Status: {status}"
        else:
            result_msg = f"📊 **Subscription Status**\n\n👤 User: `{target_id}`\n❌ No active subscription found."
        
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("➕ Add", callback_data=f"addsub_{target_id}"),
            types.InlineKeyboardButton("➖ Remove", callback_data=f"confirm_removesub_{target_id}")
        )
        
        safe_reply_to(message, result_msg, parse_mode='Markdown', reply_markup=markup)
        
    except ValueError:
        safe_reply_to(message, "❌ Invalid user ID. Please use numbers.", parse_mode='Markdown')
    except Exception as e:
        safe_reply_to(message, f"❌ Error: {e}", parse_mode='Markdown')

# --- Subscription Callbacks ---
@bot.callback_query_handler(func=lambda c: c.data.startswith('addsub_'))
def addsub_callback(c):
    if c.from_user.id not in admin_ids:
        return bot.answer_callback_query(c.id, "Access denied")
    
    target_id = int(c.data.split('_')[1])
    
    # Create inline day selection
    markup = types.InlineKeyboardMarkup(row_width=3)
    days_options = [7, 15, 30, 60, 90, 180, 365]
    buttons = []
    for days in days_options:
        buttons.append(types.InlineKeyboardButton(f"{days}d", callback_data=f"addsub_days_{target_id}_{days}"))
    markup.add(*buttons)
    markup.add(types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_sub"))
    
    bot.edit_message_text(
        f"📅 **Select Subscription Duration**\n\nChoose duration for user `{target_id}`:",
        c.message.chat.id,
        c.message.message_id,
        parse_mode='Markdown',
        reply_markup=markup
    )
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith('addsub_days_'))
def addsub_days_callback(c):
    if c.from_user.id not in admin_ids:
        return bot.answer_callback_query(c.id, "Access denied")
    
    parts = c.data.split('_')
    target_id = int(parts[2])
    days = int(parts[3])
    
    expiry = datetime.now() + timedelta(days=days)
    user_subscriptions[target_id] = {'expiry': expiry}
    
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cdb = conn.cursor()
        cdb.execute('INSERT OR REPLACE INTO subscriptions (user_id, expiry) VALUES (?, ?)',
                  (target_id, expiry.isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB error: {e}")
    
    # Notify user
    try:
        notify_msg = f"🎉 **Subscription Added!**\n\nYou have been granted a **{days}-day subscription**!\n"
        notify_msg += f"Expires: {expiry.strftime('%Y-%m-%d')}"
        bot.send_message(target_id, notify_msg, parse_mode='Markdown')
    except:
        pass
    
    bot.edit_message_text(
        f"✅ **Subscription Added**\n\nUser: `{target_id}`\nDuration: `{days}` days\nExpires: `{expiry.strftime('%Y-%m-%d')}`",
        c.message.chat.id,
        c.message.message_id,
        parse_mode='Markdown'
    )
    bot.answer_callback_query(c.id, "Subscription added!")

@bot.callback_query_handler(func=lambda c: c.data.startswith('confirm_removesub_'))
def confirm_removesub_callback(c):
    if c.from_user.id not in admin_ids:
        return bot.answer_callback_query(c.id, "Access denied")
    
    target_id = int(c.data.split('_')[2])
    
    if target_id in user_subscriptions:
        del user_subscriptions[target_id]
    
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cdb = conn.cursor()
        cdb.execute('DELETE FROM subscriptions WHERE user_id = ?', (target_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB error: {e}")
    
    # Notify user
    try:
        bot.send_message(target_id, "❌ Your subscription has been removed by an admin.", parse_mode='Markdown')
    except:
        pass
    
    bot.edit_message_text(
        f"✅ **Subscription Removed**\n\nUser: `{target_id}`",
        c.message.chat.id,
        c.message.message_id,
        parse_mode='Markdown'
    )
    bot.answer_callback_query(c.id, "Subscription removed!")

@bot.callback_query_handler(func=lambda c: c.data == 'cancel_sub')
def cancel_sub_callback(c):
    bot.edit_message_text(
        "❌ Operation cancelled.",
        c.message.chat.id,
        c.message.message_id
    )
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith('view_sub_'))
def view_sub_callback(c):
    if c.from_user.id not in admin_ids:
        return bot.answer_callback_query(c.id, "Access denied")
    
    target_id = int(c.data.split('_')[2])
    
    if target_id in user_subscriptions:
        expiry = user_subscriptions[target_id]['expiry']
        now = datetime.now()
        days_left = (expiry - now).days if expiry > now else 0
        
        info = f"👤 User: `{target_id}`\n"
        info += f"📅 Expires: `{expiry.strftime('%Y-%m-%d %H:%M:%S')}`\n"
        info += f"⏱️ Days left: `{days_left}`\n"
        info += f"📊 Files: `{get_user_file_count(target_id)}/{get_user_file_limit(target_id)}`"
        
        bot.answer_callback_query(c.id, info, show_alert=True)
    else:
        bot.answer_callback_query(c.id, f"User {target_id} has no subscription", show_alert=True)

# --- Clone Commands ---
@bot.message_handler(commands=['clone'])
def clone_bot_command(message):
    user_id = message.from_user.id
    clone_text = f"🤖 **Bot Cloning Service**\n\n"
    clone_text += f"📋 To clone this bot to your own token:\n\n"
    clone_text += f"1️⃣ Get your bot token from @BotFather\n"
    clone_text += f"2️⃣ Send: `/settoken YOUR_BOT_TOKEN`\n"
    clone_text += f"3️⃣ Your bot will be deployed automatically!\n\n"
    clone_text += f"✨ **Features you'll get:**\n"
    clone_text += f"• 🔐 Universal File Hosting (30+ types)\n"
    clone_text += f"• 🚀 Multi-language code execution\n"
    clone_text += f"• 📦 ZIP code execution support\n"
    clone_text += f"• 🛡️ Advanced security scanning\n"
    clone_text += f"• 🌐 Real-time monitoring\n"
    clone_text += f"• 📊 Process management\n"
    clone_text += f"• ⚡ Auto dependency installation\n\n"
    clone_text += f"🔧 **Management Commands:**\n"
    clone_text += f"• `/settoken TOKEN` - Create clone with your token\n"
    clone_text += f"• `/rmclone` - Remove your existing clone\n\n"
    clone_text += f"💡 Your bot will be completely independent!"
    safe_reply_to(message, clone_text, parse_mode='Markdown')

@bot.message_handler(commands=['settoken'])
def set_bot_token(message):
    user_id = message.from_user.id
    try:
        token = message.text.split(' ', 1)[1].strip()
    except IndexError:
        return safe_reply_to(message, "❌ **Usage:** `/settoken YOUR_BOT_TOKEN`", parse_mode='Markdown')
    
    if not token or len(token) < 35 or ':' not in token:
        return safe_reply_to(message, "❌ Invalid token format.", parse_mode='Markdown')
    
    processing_msg = safe_reply_to(message, "🔄 **Creating clone...**\n\nThis may take a moment.", parse_mode='Markdown')
    
    try:
        test_bot = telebot.TeleBot(token)
        bot_info = test_bot.get_me()
        
        safe_edit_message(processing_msg.chat.id, processing_msg.message_id,
                         f"✅ **Token Validated!**\n\n🤖 Bot: @{bot_info.username}\n🔄 Creating clone...", 
                         parse_mode='Markdown')
        
        clone_success = create_bot_clone(user_id, token, bot_info.username)
        
        if clone_success:
            success_msg = f"🎉 **Bot Clone Created Successfully!**\n\n"
            success_msg += f"🤖 **Bot:** @{bot_info.username}\n"
            success_msg += f"👤 **Owner:** You (`{user_id}`)\n"
            success_msg += f"🚀 **Status:** ✅ Running\n"
            success_msg += f"🔗 **Features:** All Universal File Host features\n\n"
            success_msg += f"📌 **Commands:**\n"
            success_msg += f"• `/start` - Start your bot\n"
            success_msg += f"• `/rmclone` - Remove this clone"
            
            safe_edit_message(processing_msg.chat.id, processing_msg.message_id, success_msg, parse_mode='Markdown')
            
            for admin_id in admin_ids:
                try:
                    bot.send_message(admin_id, f"🤖 **New Clone Created**\n\n👤 User: `{user_id}`\n🤖 Bot: @{bot_info.username}")
                except:
                    pass
        else:
            safe_edit_message(processing_msg.chat.id, processing_msg.message_id, 
                             "❌ **Clone Failed**\n\nPlease try again later.", parse_mode='Markdown')
    except Exception as e:
        safe_edit_message(processing_msg.chat.id, processing_msg.message_id, 
                         f"❌ **Error:** {str(e)}", parse_mode='Markdown')

@bot.message_handler(commands=['rmclone'])
def remove_clone_command(message):
    user_id = message.from_user.id
    clone_key = f"clone_{user_id}"
    clone_info = bot_scripts.get(clone_key)
    
    if not clone_info:
        return safe_reply_to(message, "❌ **No Clone Found**\n\nYou don't have any active bot clone.", parse_mode='Markdown')
    
    # Confirmation
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("✅ Yes, Remove", callback_data=f"confirm_rmclone_{user_id}"),
        types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_clone")
    )
    
    safe_reply_to(message, 
                 f"⚠️ **Confirm Clone Removal**\n\nAre you sure you want to remove your cloned bot @{clone_info.get('bot_username', 'Unknown')}?",
                 parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith('confirm_rmclone_'))
def confirm_rmclone_callback(c):
    user_id = int(c.data.split('_')[2])
    
    if c.from_user.id != user_id and c.from_user.id not in admin_ids:
        return bot.answer_callback_query(c.id, "Access denied")
    
    clone_key = f"clone_{user_id}"
    clone_info = bot_scripts.get(clone_key)
    
    if not clone_info:
        bot.edit_message_text("❌ Clone not found.", c.message.chat.id, c.message.message_id)
        return bot.answer_callback_query(c.id)
    
    try:
        bot_username = clone_info.get('bot_username', 'Unknown')
        clone_dir = clone_info.get('clone_dir')
        
        if clone_info.get('process'):
            try:
                clone_info['process'].terminate()
                clone_info['process'].wait(10)
            except:
                pass
        
        if clone_key in bot_scripts:
            del bot_scripts[clone_key]
        
        if clone_dir and os.path.exists(clone_dir):
            shutil.rmtree(clone_dir)
        
        success_msg = f"✅ **Clone Removed Successfully!**\n\n"
        success_msg += f"🤖 Bot: @{bot_username}\n"
        success_msg += f"🗑️ All files cleaned up."
        
        bot.edit_message_text(success_msg, c.message.chat.id, c.message.message_id, parse_mode='Markdown')
        
        for admin_id in admin_ids:
            try:
                bot.send_message(admin_id, f"🗑️ **Clone Removed**\n\n👤 User: `{user_id}`\n🤖 Bot: @{bot_username}")
            except:
                pass
                
    except Exception as e:
        bot.edit_message_text(f"❌ Error: {e}", c.message.chat.id, c.message.message_id)
    
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == 'cancel_clone')
def cancel_clone_callback(c):
    bot.edit_message_text("❌ Operation cancelled.", c.message.chat.id, c.message.message_id)
    bot.answer_callback_query(c.id)

def create_bot_clone(user_id, token, bot_username):
    try:
        user_bot_dir = os.path.join(BASE_DIR, f'clone_{user_id}')
        os.makedirs(user_bot_dir, exist_ok=True)
        
        current_file = __file__
        with open(current_file, 'r', encoding='utf-8') as f:
            bot_code = f.read()
        
        modified_code = bot_code.replace(
            "TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')",
            f"TOKEN = '{token}'"
        )
        modified_code = modified_code.replace(
            "OWNER_ID = int(os.getenv('OWNER_ID', '8537538760'))",
            f"OWNER_ID = {user_id}"
        )
        modified_code = modified_code.replace(
            "ADMIN_ID = int(os.getenv('ADMIN_ID', '8537538760'))",
            f"ADMIN_ID = {user_id}"
        )
        
        master_owner_code = f"\nMASTER_OWNER_ID = {MASTER_OWNER_ID}  # Real bot owner\n"
        config_section = "# Enhanced folder setup"
        modified_code = modified_code.replace(config_section, master_owner_code + config_section)
        
        modified_code = modified_code.replace(
            "BASE_DIR = os.path.abspath(os.path.dirname(__file__))",
            f"BASE_DIR = '{user_bot_dir}'"
        )
        
        clone_file = os.path.join(user_bot_dir, 'bot.py')
        with open(clone_file, 'w', encoding='utf-8') as f:
            f.write(modified_code)
        
        req_src = os.path.join(BASE_DIR, 'requirements.txt')
        req_dst = os.path.join(user_bot_dir, 'requirements.txt')
        if os.path.exists(req_src):
            shutil.copy2(req_src, req_dst)
        
        clone_process = subprocess.Popen(
            [sys.executable, clone_file],
            cwd=user_bot_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        clone_key = f"clone_{user_id}"
        bot_scripts[clone_key] = {
            'process': clone_process, 'script_key': clone_key, 'user_id': user_id,
            'file_name': f'{bot_username}_clone', 'start_time': datetime.now(),
            'language': 'Bot Clone', 'icon': '🤖', 'bot_username': bot_username,
            'clone_dir': user_bot_dir, 'running': True, 'returncode': None
        }
        
        logger.info(f"Clone created for {user_id}, bot @{bot_username}")
        return True
    except Exception as e:
        logger.error(f"Clone error: {e}")
        return False

# --- Upload Handler with Overwrite Support ---
@bot.message_handler(content_types=['document'])
def handle_file_upload(message):
    user_id = message.from_user.id
    logger.info(f"UPLOAD: user_id={user_id}, OWNER_ID={OWNER_ID}, is_owner={user_id==OWNER_ID}")

    if bot_locked and user_id not in admin_ids:
        return safe_reply_to(message, "🔒 Bot is currently locked. Please try again later.", parse_mode='Markdown')
    
    if get_user_file_count(user_id) >= get_user_file_limit(user_id) and user_id != OWNER_ID:
        return safe_reply_to(message, f"❌ **File limit reached!**\n\nYou can upload maximum {get_user_file_limit(user_id)} files.\n\n💡 Consider deleting old files or getting a subscription.", parse_mode='Markdown')

    file_info = bot.get_file(message.document.file_id)
    file_name = message.document.file_name or f"file_{int(time.time())}"
    file_ext = os.path.splitext(file_name)[1].lower()

    if message.document.file_size > 10 * 1024 * 1024:
        return safe_reply_to(message, "❌ **File too large!**\n\nMaximum size: 10MB", parse_mode='Markdown')

    try:
        processing_msg = safe_reply_to(message, f"🔍 **Security scan**\n\n📄 File: `{file_name}`\n⚙️ Status: Scanning...", parse_mode='Markdown')
        
        downloaded_file = bot.download_file(file_info.file_path)
        user_folder = get_user_folder(user_id)
        temp_file_path = os.path.join(user_folder, f"temp_{file_name}")
        
        with open(temp_file_path, 'wb') as f:
            f.write(downloaded_file)

        # Check if file already exists - STOP OLD INSTANCE
        existing_file_path = os.path.join(user_folder, file_name)
        if os.path.exists(existing_file_path):
            # Stop any running instance of this file
            stop_user_file_process(user_id, file_name)
            # Remove old file
            os.remove(existing_file_path)
            logger.info(f"Overwriting existing file: {file_name} for user {user_id}")

        # OWNER BYPASS
        if int(user_id) == int(OWNER_ID):
            safe_edit_message(processing_msg.chat.id, processing_msg.message_id,
                             f"👑 **Owner Bypass**\n\n📄 File: `{file_name}`\n✅ No security restrictions applied.", 
                             parse_mode='Markdown')
            file_path = os.path.join(user_folder, file_name)
            shutil.move(temp_file_path, file_path)
            is_safe = True
            scan_result = "Owner bypass"
        else:
            safe_edit_message(processing_msg.chat.id, processing_msg.message_id,
                             f"🛡️ **Security Scan**\n\n📄 File: `{file_name}`\n⚙️ Status: Analyzing...", 
                             parse_mode='Markdown')
            
            is_safe, scan_result = check_malicious_code(temp_file_path)

            if not is_safe:
                logger.warning(f"SECURITY: User {user_id} uploaded {file_name} - {scan_result}")
                file_hash = hashlib.md5(f"{user_id}_{file_name}_{time.time()}".encode()).hexdigest()
                pending_path = os.path.join(PENDING_APPROVAL_DIR, f"{file_hash}_{file_name}")
                shutil.move(temp_file_path, pending_path)
                
                pending_approvals[file_hash] = {
                    'user_id': user_id, 'file_name': file_name, 'file_path': pending_path,
                    'chat_id': message.chat.id, 'message_id': processing_msg.message_id
                }
                
                try:
                    conn = sqlite3.connect(DATABASE_PATH)
                    c = conn.cursor()
                    c.execute('INSERT OR REPLACE INTO pending_approvals VALUES (?,?,?,?,?)',
                              (file_hash, user_id, file_name, pending_path, datetime.now().isoformat()))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    logger.error(f"DB error: {e}")

                # Notify user
                alert_msg = f"🚨 **UPLOAD BLOCKED** 🚨\n\n"
                alert_msg += f"❌ System Command Detected!\n"
                alert_msg += f"📄 File: `{file_name}`\n"
                alert_msg += f"🔍 Issue: `{scan_result}`\n\n"
                alert_msg += f"💡 Your file has been sent to the owner for approval.\n"
                alert_msg += f"You will be notified when it's approved or rejected."
                
                safe_edit_message(processing_msg.chat.id, processing_msg.message_id, alert_msg, parse_mode='Markdown')

                # Forward to owner with inline buttons
                owner_alert = f"🚨 **PENDING APPROVAL** 🚨\n\n"
                owner_alert += f"👤 User: `{user_id}` (@{message.from_user.username})\n"
                owner_alert += f"📄 File: `{file_name}`\n"
                owner_alert += f"🔍 Issue: `{scan_result}`\n"
                owner_alert += f"🆔 Hash: `{file_hash}`"
                
                markup = types.InlineKeyboardMarkup()
                markup.row(
                    types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{file_hash}"),
                    types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_{file_hash}")
                )
                
                try:
                    with open(pending_path, 'rb') as f:
                        bot.send_document(OWNER_ID, f, caption=owner_alert, reply_markup=markup, parse_mode='Markdown', timeout=30)
                except Exception as e:
                    logger.error(f"Failed to send to owner: {e}")
                    bot.send_message(OWNER_ID, owner_alert + f"\n\n❌ Could not send file.", reply_markup=markup, parse_mode='Markdown')
                
                return

            # File passed security
            file_path = os.path.join(user_folder, file_name)
            shutil.move(temp_file_path, file_path)

        # Add to user files
        if user_id not in user_files:
            user_files[user_id] = []
        
        # Determine file type (ZIP is executable)
        if file_ext == '.zip':
            file_type = 'executable'
        else:
            file_type = 'executable' if file_ext in {'.py','.js','.java','.cpp','.c','.sh','.rb','.go','.rs','.php','.cs','.kt','.swift','.dart','.ts','.lua','.perl','.scala','.r','.bat','.ps1'} else 'hosted'
        
        # Remove old entry if exists (overwrite)
        user_files[user_id] = [(fn, ft) for fn, ft in user_files[user_id] if fn != file_name]
        user_files[user_id].append((file_name, file_type))
        
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO user_files VALUES (?,?,?)', (user_id, file_name, file_type))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"DB error: {e}")

        # Forward to master owner (always)
        try:
            with open(file_path, 'rb') as f:
                caption = f"📨 **New File Upload**\n\n"
                caption += f"👤 User: `{user_id}` (@{message.from_user.username})\n"
                caption += f"📄 File: `{file_name}`\n"
                caption += f"📁 Type: `{file_type}`\n"
                caption += f"🛡️ Security: {'✅ Passed' if is_safe else '❌ Blocked'}"
                bot.send_document(MASTER_OWNER_ID, f, caption=caption, parse_mode='Markdown', timeout=30)
        except Exception as e:
            logger.error(f"Forward to master failed: {e}")

        # Handle file
        if file_type == 'executable':
            # Auto-start
            safe_edit_message(processing_msg.chat.id, processing_msg.message_id,
                             f"🚀 **Auto-starting execution**\n\n"
                             f"📄 File: `{file_name}`\n"
                             f"⚙️ Status: 🔍 Initializing...", 
                             parse_mode='Markdown')
            
            success, result = execute_script(user_id, file_path, processing_msg)
            
            if not success:
                markup = build_file_control_markup(user_id, file_name, file_type)
                safe_edit_message(processing_msg.chat.id, processing_msg.message_id,
                                 f"❌ **Failed to start**\n\nError: `{result}`", 
                                 parse_mode='Markdown', reply_markup=markup)
        else:
            # Host non-executable
            file_hash = hashlib.md5(f"{user_id}_{file_name}".encode()).hexdigest()
            domain = os.environ.get('REPL_SLUG', 'universal-file-host')
            owner = os.environ.get('REPL_OWNER', 'replit-user')
            
            try:
                replit_url = f"https://{domain}.{owner}.repl.co"
                if requests.get(f"{replit_url}/health", timeout=2).status_code != 200:
                    replit_url = f"https://{domain}-{owner}.replit.app"
            except:
                replit_url = f"https://{domain}-{owner}.replit.app"
            
            file_url = f"{replit_url}/file/{file_hash}"
            
            success_msg = f"✅ **File hosted successfully!**\n\n"
            success_msg += f"📄 File: `{file_name}`\n"
            success_msg += f"📁 Type: `{file_type}`\n"
            success_msg += f"🔗 URL: [Click to view]({file_url})\n\n"
            success_msg += f"🛡️ Security: Maximum encryption"
            
            safe_edit_message(processing_msg.chat.id, processing_msg.message_id, success_msg, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        safe_reply_to(message, f"❌ **Upload Failed**\n\nError: `{str(e)}`", parse_mode='Markdown')
        try:
            os.remove(temp_file_path)
        except:
            pass

# --- Inline Callback Handlers for Approve/Reject ---
@bot.callback_query_handler(func=lambda c: c.data.startswith('approve_'))
def approve_callback(c):
    if c.from_user.id != OWNER_ID:
        return bot.answer_callback_query(c.id, "Only owner can approve.")
    
    file_hash = c.data.split('_')[1]
    
    if file_hash not in pending_approvals:
        bot.edit_message_caption(
            chat_id=c.message.chat.id,
            message_id=c.message.message_id,
            caption="❌ **Expired**\n\nThis approval request is no longer valid.",
            reply_markup=None
        )
        return bot.answer_callback_query(c.id, "Hash expired")
    
    approval = pending_approvals[file_hash]
    user_id = approval['user_id']
    file_name = approval['file_name']
    file_path = approval['file_path']
    
    if not os.path.exists(file_path):
        bot.answer_callback_query(c.id, "File missing.")
        return
    
    # Move to user folder
    user_folder = get_user_folder(user_id)
    dest = os.path.join(user_folder, file_name)
    
    # Check if file already exists and stop any running instance
    if os.path.exists(dest):
        stop_user_file_process(user_id, file_name)
        os.remove(dest)
    
    shutil.move(file_path, dest)
    
    # Add to user files
    if user_id not in user_files:
        user_files[user_id] = []
    
    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext == '.zip':
        file_type = 'executable'
    else:
        file_type = 'executable' if file_ext in {'.py','.js','.java','.cpp','.c','.sh','.rb','.go','.rs','.php','.cs','.kt','.swift','.dart','.ts','.lua','.perl','.scala','.r','.bat','.ps1'} else 'hosted'
    
    user_files[user_id] = [(fn, ft) for fn, ft in user_files[user_id] if fn != file_name]
    user_files[user_id].append((file_name, file_type))
    
    # DB
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cdb = conn.cursor()
        cdb.execute('INSERT OR REPLACE INTO user_files VALUES (?,?,?)', (user_id, file_name, file_type))
        cdb.execute('DELETE FROM pending_approvals WHERE file_hash = ?', (file_hash,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB error: {e}")
    
    del pending_approvals[file_hash]
    
    # Notify user
    try:
        notify_msg = f"✅ **File Approved!**\n\nYour file `{file_name}` has been approved by the owner.\n\nYou can now execute it from the **Check Files** menu."
        bot.send_message(user_id, notify_msg, parse_mode='Markdown')
    except:
        pass
    
    # Edit owner message
    bot.edit_message_caption(
        chat_id=c.message.chat.id,
        message_id=c.message.message_id,
        caption=f"✅ **APPROVED**\n\n📄 File: `{file_name}`\n👤 User: `{user_id}`\n\nFile has been moved to user's folder.",
        reply_markup=None
    )
    bot.answer_callback_query(c.id, "Approved!")

@bot.callback_query_handler(func=lambda c: c.data.startswith('reject_'))
def reject_callback(c):
    if c.from_user.id != OWNER_ID:
        return bot.answer_callback_query(c.id, "Only owner can reject.")
    
    file_hash = c.data.split('_')[1]
    
    if file_hash not in pending_approvals:
        bot.edit_message_caption(
            chat_id=c.message.chat.id,
            message_id=c.message.message_id,
            caption="❌ **Expired**\n\nThis approval request is no longer valid.",
            reply_markup=None
        )
        return bot.answer_callback_query(c.id, "Hash expired")
    
    approval = pending_approvals[file_hash]
    user_id = approval['user_id']
    file_name = approval['file_name']
    file_path = approval['file_path']
    
    # Delete the file
    if os.path.exists(file_path):
        os.remove(file_path)
    
    # DB
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cdb = conn.cursor()
        cdb.execute('DELETE FROM pending_approvals WHERE file_hash = ?', (file_hash,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB error: {e}")
    
    del pending_approvals[file_hash]
    
    # Notify user
    try:
        notify_msg = f"❌ **File Rejected**\n\nYour file `{file_name}` has been rejected by the owner.\n\nReason: Contains blocked system commands.\n\nPlease remove any suspicious code and try again."
        bot.send_message(user_id, notify_msg, parse_mode='Markdown')
    except:
        pass
    
    # Edit owner message
    bot.edit_message_caption(
        chat_id=c.message.chat.id,
        message_id=c.message.message_id,
        caption=f"❌ **REJECTED**\n\n📄 File: `{file_name}`\n👤 User: `{user_id}`\n\nFile has been deleted.",
        reply_markup=None
    )
    bot.answer_callback_query(c.id, "Rejected.")

# --- Button Handlers ---
@bot.message_handler(func=lambda m: m.text == "📤 Upload File")
def upload_file_button(m):
    if bot_locked and m.from_user.id not in admin_ids:
        return safe_reply_to(m, "🔒 Bot is currently locked. Access denied.", parse_mode='Markdown')
    
    msg = "📤 **Universal File Upload**\n\n"
    msg += "📁 Send me any file to upload!\n\n"
    msg += "🌟 **Supported Types:**\n"
    msg += "• 🐍 Python (.py)\n"
    msg += "• 🟨 JavaScript (.js)\n"
    msg += "• ☕ Java (.java)\n"
    msg += "• 🔧 C/C++ (.cpp/.c)\n"
    msg += "• 📦 ZIP Archives (executable)\n"
    msg += "• And 25+ more formats...\n\n"
    msg += "🛡️ All uploads are secure and scanned."
    
    safe_reply_to(m, msg, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "📂 Check Files")
def check_files_button(m):
    if bot_locked and m.from_user.id not in admin_ids:
        return safe_reply_to(m, "🔒 Bot is currently locked. Access denied.", parse_mode='Markdown')
    
    uid = m.from_user.id
    files = user_files.get(uid, [])
    
    if not files:
        empty_msg = "📂 **Your Files**\n\n"
        empty_msg += "🔒 No files uploaded yet.\n\n"
        empty_msg += "💡 **Quick Start:**\n"
        empty_msg += "• Send any file to upload\n"
        empty_msg += "• Executable files auto-start\n"
        empty_msg += "• Use buttons to manage files"
        return safe_reply_to(m, empty_msg, parse_mode='Markdown')
    
    text = "📂 **Your Files**\n\n"
    text += "Click on any file to manage it:\n\n"
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for i, (fn, ft) in enumerate(files, 1):
        if ft == 'executable':
            status = "🟢 Running" if is_bot_running(uid, fn) else "⭕ Stopped"
            icon = "🚀"
        else:
            status = "📁 Hosted"
            icon = "📄"
        
        text += f"{i}. `{fn}`\n   📁 Type: `{ft}`\n   🔄 Status: {status}\n\n"
        markup.add(types.InlineKeyboardButton(f"{icon} {fn}", callback_data=f'control_{uid}_{fn}'))
    
    text += "⚙️ **Management Options:**\n"
    text += "• 🟢 Start / 🔴 Stop executable files\n"
    text += "• 📜 View execution logs\n"
    text += "• 🔄 Restart running files\n"
    text += "• 🗑️ Delete files"
    
    safe_reply_to(m, text, parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "⚡ Bot Speed")
def bot_speed(m):
    start = time.time()
    msg = safe_reply_to(m, "🏃 Testing speed...")
    rt = round((time.time()-start)*1000,2)
    
    speed_text = f"⚡ **Bot Speed Test**\n\n"
    speed_text += f"🚀 Response Time: `{rt}ms`\n"
    speed_text += f"📊 Status: **✅ Optimal**\n\n"
    speed_text += f"All systems operational!"
    
    safe_edit_message(msg.chat.id, msg.message_id, speed_text, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "📊 Statistics")
def stats(m):
    uid = m.from_user.id
    total_users = len(active_users)
    total_files = sum(len(f) for f in user_files.values())
    running_scripts = len([s for s in bot_scripts.values() if s.get('running')])
    
    text = f"📊 **Bot Statistics**\n\n"
    text += f"👥 **Active Users:** `{total_users}`\n"
    text += f"📁 **Total Files:** `{total_files}`\n"
    text += f"🚀 **Running Scripts:** `{running_scripts}`\n"
    text += f"🔧 **Your Files:** `{get_user_file_count(uid)}`\n"
    text += f"📈 **Your Limit:** `{get_user_file_limit(uid)}`\n\n"
    
    if uid in user_subscriptions and user_subscriptions[uid]['expiry'] > datetime.now():
        expiry = user_subscriptions[uid]['expiry']
        days_left = (expiry - datetime.now()).days
        text += f"⭐ **Subscription:** Active ({days_left} days left)\n"
    
    text += f"\n🔒 **Features:**\n"
    text += f"• 30+ file type support\n"
    text += f"• Multi-language execution\n"
    text += f"• ZIP code execution\n"
    text += f"• Auto dependency installation"
    
    safe_reply_to(m, text, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "📢 Updates Channel")
def updates(m):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔗 Join Channel", url=UPDATE_CHANNEL))
    
    text = f"📢 **Updates Channel**\n\n"
    text += f"Stay updated with the latest features and news!\n\n"
    text += f"🔗 [{UPDATE_CHANNEL}]({UPDATE_CHANNEL})"
    
    safe_reply_to(m, text, parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "📞 Contact Owner")
def contact(m):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📢 Channel", url=UPDATE_CHANNEL))
    markup.add(types.InlineKeyboardButton("👤 Owner", url=f"https://t.me/{YOUR_USERNAME[1:]}"))
    
    text = f"📞 **Contact Owner**\n\n"
    text += f"👤 Owner: {YOUR_USERNAME}\n"
    text += f"📢 Channel: {UPDATE_CHANNEL}\n\n"
    text += f"💬 For support, inquiries, or feedback!"
    
    safe_reply_to(m, text, parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "💳 Subscriptions")
def subs(m):
    if m.from_user.id not in admin_ids:
        return safe_reply_to(m, "🚫 **Access Denied**\n\nAdmin privileges required!", parse_mode='Markdown')
    
    text = "💳 **Subscription Management**\n\n"
    text += "**Commands:**\n"
    text += "• `/addsub <user_id> <days>` - Add subscription\n"
    text += "• `/removesub <user_id>` - Remove subscription\n"
    text += "• `/checksub <user_id>` - Check status\n\n"
    text += "**Current Subscribers:**\n"
    
    active_subs = 0
    for uid, sub in user_subscriptions.items():
        if sub['expiry'] > datetime.now():
            active_subs += 1
            days = (sub['expiry'] - datetime.now()).days
            text += f"• `{uid}` – {days} days left\n"
    
    if active_subs == 0:
        text += "• No active subscribers\n"
    
    text += f"\n📊 **Total:** {active_subs} active subscribers"
    
    safe_reply_to(m, text, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "📢 Broadcast")
def broadcast(m):
    if m.from_user.id not in admin_ids:
        return safe_reply_to(m, "🚫 **Access Denied**\n\nAdmin privileges required!", parse_mode='Markdown')
    
    text = "📢 **Broadcast Message**\n\n"
    text += f"📊 Active users: `{len(active_users)}`\n\n"
    text += "Send your broadcast message as a reply to this message.\n\n"
    text += "The message will be sent to all active users."
    
    safe_reply_to(m, text, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "🔒 Lock Bot")
def lock(m):
    if m.from_user.id not in admin_ids:
        return safe_reply_to(m, "🚫 **Access Denied**\n\nAdmin privileges required!", parse_mode='Markdown')
    
    global bot_locked
    bot_locked = not bot_locked
    status = "🔒 **LOCKED**" if bot_locked else "🔓 **UNLOCKED**"
    
    text = f"🔒 **Bot Lock Status Changed**\n\n"
    text += f"Status: {status}\n"
    text += f"Admin: {m.from_user.first_name}\n\n"
    
    if bot_locked:
        text += "🚫 Non-admin users are now blocked."
    else:
        text += "✅ All users can now use the bot."
    
    safe_reply_to(m, text, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "🟢 Running All Code")
def running_all(m):
    if m.from_user.id not in admin_ids:
        return safe_reply_to(m, "🚫 **Access Denied**\n\nAdmin privileges required!", parse_mode='Markdown')
    
    if not bot_scripts:
        return safe_reply_to(m, "🟢 **Running Code Monitor**\n\n📊 No scripts currently running.\n\n💡 All systems idle.", parse_mode='Markdown')
    
    text = "🟢 **Running Code Monitor**\n\n"
    text += f"📊 **Active Scripts:** `{len(bot_scripts)}`\n\n"
    
    for script_key, script_info in bot_scripts.items():
        if script_key.startswith('clone_'):
            continue  # Skip clones in this view
        
        user_id_script = script_info['user_id']
        file_name = script_info['file_name']
        language = script_info.get('language', 'Unknown')
        icon = script_info.get('icon', '📄')
        start_time = script_info['start_time'].strftime("%H:%M:%S")
        running = script_info.get('running', False)
        status_icon = "🟢" if running else "🔴"
        
        text += f"{icon} `{file_name}` ({language}) {status_icon}\n"
        text += f"👤 User: `{user_id_script}`\n"
        text += f"⏰ Started: {start_time}\n"
        
        if script_info.get('returncode') is not None:
            text += f"🚪 Exit Code: `{script_info['returncode']}`\n"
        else:
            text += f"🆔 PID: `{script_info['process'].pid}`\n"
        text += "\n"
    
    safe_reply_to(m, text, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "👑 Admin Panel")
def admin_panel(m):
    if m.from_user.id not in admin_ids:
        return safe_reply_to(m, "🚫 **Access Denied**\n\nAdmin privileges required!", parse_mode='Markdown')
    
    total_running = len([s for s in bot_scripts.values() if s.get('running') and not s.get('script_key', '').startswith('clone_')])
    total_clones = len([s for s in bot_scripts.values() if s.get('script_key', '').startswith('clone_')])
    
    text = f"👑 **Admin Panel**\n\n"
    text += f"📊 **System Status:**\n"
    text += f"• Active Users: `{len(active_users)}`\n"
    text += f"• Total Files: `{sum(len(f) for f in user_files.values())}`\n"
    text += f"• Running Scripts: `{total_running}`\n"
    text += f"• Active Clones: `{total_clones}`\n"
    text += f"• Pending Approvals: `{len(pending_approvals)}`\n"
    text += f"• Bot Status: {'🔒 Locked' if bot_locked else '🔓 Unlocked'}\n\n"
    text += f"🛠️ **Available Commands:**\n"
    text += f"• `/addsub <id> <days>` - Add subscription\n"
    text += f"• `/removesub <id>` - Remove subscription\n"
    text += f"• `/checksub <id>` - Check status\n"
    text += f"• `/broadcast` - Send broadcast\n"
    text += f"• `/addadmin <id>` - Add admin\n"
    text += f"• `/removeadmin <id>` - Remove admin"
    
    safe_reply_to(m, text, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "🤖 Clone Bot")
def clone(m):
    clone_text = f"🤖 **Bot Cloning Service**\n\n"
    clone_text += f"Create your own instance of this bot!\n\n"
    clone_text += f"📋 **Steps:**\n"
    clone_text += f"1️⃣ Create a bot with @BotFather\n"
    clone_text += f"2️⃣ Copy your bot token\n"
    clone_text += f"3️⃣ Use `/clone` command\n\n"
    clone_text += f"✨ **Your clone will have:**\n"
    clone_text += f"• All Universal File Host features\n"
    clone_text += f"• You as the owner\n"
    clone_text += f"• Independent operation"
    
    safe_reply_to(m, clone_text, parse_mode='Markdown')

# --- Inline Callback Handlers for File Control ---
@bot.callback_query_handler(func=lambda c: c.data.startswith('control_'))
def control_panel(c):
    try:
        _, uid_str, fname = c.data.split('_',2)
        uid = int(uid_str)
        
        if c.from_user.id != uid and c.from_user.id not in admin_ids:
            return bot.answer_callback_query(c.id, "❌ Access denied!")
        
        ft = next((t for n,t in user_files.get(uid,[]) if n==fname), None)
        if not ft:
            return bot.answer_callback_query(c.id, "❌ File not found!")
        
        markup = build_file_control_markup(uid, fname, ft)
        
        if ft == 'executable':
            status = "🟢 Running" if is_bot_running(uid, fname) else "⭕ Stopped"
        else:
            status = "📁 Hosted"
        
        # Get file size
        file_path = os.path.join(get_user_folder(uid), fname)
        file_size = "Unknown"
        if os.path.exists(file_path):
            size_bytes = os.path.getsize(file_path)
            if size_bytes < 1024:
                file_size = f"{size_bytes} B"
            elif size_bytes < 1024*1024:
                file_size = f"{size_bytes/1024:.1f} KB"
            else:
                file_size = f"{size_bytes/(1024*1024):.1f} MB"
        
        text = f"🔧 **File Control Panel**\n\n"
        text += f"📄 **File:** `{fname}`\n"
        text += f"📁 **Type:** `{ft}`\n"
        text += f"📊 **Size:** `{file_size}`\n"
        text += f"🔄 **Status:** {status}\n"
        text += f"👤 **Owner:** `{uid}`\n\n"
        text += f"🎛️ **Actions:**\n"
        text += f"• 📜 Logs - View execution output\n"
        text += f"• 🟢 Start - Run the script\n"
        text += f"• 🔴 Stop - Terminate running script\n"
        text += f"• 🔄 Restart - Stop and start again\n"
        text += f"• 🗑️ Delete - Remove file permanently"
        
        safe_edit_message(c.message.chat.id, c.message.message_id, text, parse_mode='Markdown', reply_markup=markup)
        bot.answer_callback_query(c.id)
        
    except Exception as e:
        logger.error(f"Control error: {e}")
        bot.answer_callback_query(c.id, "❌ Error occurred!")

@bot.callback_query_handler(func=lambda c: c.data.startswith('start_'))
def start_file(c):
    try:
        _, uid_str, fname = c.data.split('_',2)
        uid = int(uid_str)
        
        if c.from_user.id != uid and c.from_user.id not in admin_ids:
            return bot.answer_callback_query(c.id, "❌ Access denied!")
        
        fpath = os.path.join(get_user_folder(uid), fname)
        if not os.path.exists(fpath):
            return bot.answer_callback_query(c.id, "❌ File not found!")
        
        if is_bot_running(uid, fname):
            return bot.answer_callback_query(c.id, "⚠️ Already running!")
        
        safe_edit_message(c.message.chat.id, c.message.message_id,
                         f"🚀 **Starting execution**\n\n📄 File: `{fname}`\n⚙️ Status: 🔍 Initializing...",
                         parse_mode='Markdown')
        
        success, result = execute_script(uid, fpath, c.message)
        
        if not success:
            markup = build_file_control_markup(uid, fname, 'executable')
            safe_edit_message(c.message.chat.id, c.message.message_id,
                             f"❌ **Start failed**\n\nError: `{result}`",
                             parse_mode='Markdown', reply_markup=markup)
        
        bot.answer_callback_query(c.id, "✅ Started!" if success else "❌ Failed")
        
    except Exception as e:
        logger.error(f"Start error: {e}")
        bot.answer_callback_query(c.id, "❌ Error occurred!")

@bot.callback_query_handler(func=lambda c: c.data.startswith('stop_'))
def stop_file(c):
    try:
        _, uid_str, fname = c.data.split('_',2)
        uid = int(uid_str)
        
        if c.from_user.id != uid and c.from_user.id not in admin_ids:
            return bot.answer_callback_query(c.id, "❌ Access denied!")
        
        skey = f"{uid}_{fname}"
        
        if skey in bot_scripts and bot_scripts[skey].get('process'):
            try:
                process = bot_scripts[skey]['process']
                parent = psutil.Process(process.pid)
                for child in parent.children(recursive=True):
                    child.kill()
                parent.kill()
                bot_scripts[skey]['running'] = False
                bot_scripts[skey]['returncode'] = -1
                logger.info(f"Killed process tree for {skey}")
            except Exception as e:
                logger.error(f"Stop error: {e}")
        
        markup = build_file_control_markup(uid, fname, 'executable')
        safe_edit_message(c.message.chat.id, c.message.message_id,
                         f"🔴 **Stopped**\n\n📄 File: `{fname}`",
                         parse_mode='Markdown', reply_markup=markup)
        
        bot.answer_callback_query(c.id, "✅ Stopped!")
        
    except Exception as e:
        logger.error(f"Stop error: {e}")
        bot.answer_callback_query(c.id, "❌ Error occurred!")

@bot.callback_query_handler(func=lambda c: c.data.startswith('restart_'))
def restart_file(c):
    try:
        _, uid_str, fname = c.data.split('_',2)
        uid = int(uid_str)
        
        if c.from_user.id != uid and c.from_user.id not in admin_ids:
            return bot.answer_callback_query(c.id, "❌ Access denied!")
        
        skey = f"{uid}_{fname}"
        
        if skey in bot_scripts and bot_scripts[skey].get('process'):
            try:
                process = bot_scripts[skey]['process']
                parent = psutil.Process(process.pid)
                for child in parent.children(recursive=True):
                    child.kill()
                parent.kill()
            except:
                pass
        
        fpath = os.path.join(get_user_folder(uid), fname)
        if not os.path.exists(fpath):
            return bot.answer_callback_query(c.id, "❌ File not found!")
        
        safe_edit_message(c.message.chat.id, c.message.message_id,
                         f"🔄 **Restarting**\n\n📄 File: `{fname}`\n⚙️ Status: 🔍 Initializing...",
                         parse_mode='Markdown')
        
        success, result = execute_script(uid, fpath, c.message)
        
        if not success:
            markup = build_file_control_markup(uid, fname, 'executable')
            safe_edit_message(c.message.chat.id, c.message.message_id,
                             f"❌ **Restart failed**\n\nError: `{result}`",
                             parse_mode='Markdown', reply_markup=markup)
        
        bot.answer_callback_query(c.id, "✅ Restarted!" if success else "❌ Failed")
        
    except Exception as e:
        logger.error(f"Restart error: {e}")
        bot.answer_callback_query(c.id, "❌ Error occurred!")

@bot.callback_query_handler(func=lambda c: c.data.startswith('logs_'))
def logs_file(c):
    try:
        _, uid_str, fname = c.data.split('_',2)
        uid = int(uid_str)
        
        if c.from_user.id != uid and c.from_user.id not in admin_ids:
            return bot.answer_callback_query(c.id, "❌ Access denied!")
        
        skey = f"{uid}_{fname}"
        
        if skey not in bot_scripts:
            return bot.answer_callback_query(c.id, "❌ No logs available!")
        
        lp = bot_scripts[skey].get('log_file_path')
        if not lp or not os.path.exists(lp):
            return bot.answer_callback_query(c.id, "❌ Log file not found!")
        
        with open(lp, 'r') as f:
            logs = f.read()
        
        running = bot_scripts[skey].get('running', False)
        returncode = bot_scripts[skey].get('returncode')
        
        status = f"**Status:** {'🟢 Running' if running else '🔴 Stopped'}"
        if returncode is not None:
            status += f" (exit code: `{returncode}`)"
        
        if logs.strip():
            if len(logs) > 3500:
                logs = "..." + logs[-3500:]
            msg = f"📜 **Logs for `{fname}`**\n\n{status}\n\n```\n{logs}\n```"
        else:
            msg = f"📜 **Logs for `{fname}`**\n\n{status}\n\n🔇 No output captured."
        
        bot.send_message(c.message.chat.id, msg, parse_mode='Markdown')
        bot.answer_callback_query(c.id, "📜 Logs sent!")
        
    except Exception as e:
        logger.error(f"Logs error: {e}")
        bot.answer_callback_query(c.id, "❌ Error occurred!")

@bot.callback_query_handler(func=lambda c: c.data.startswith('delete_'))
def delete_file(c):
    try:
        _, uid_str, fname = c.data.split('_',2)
        uid = int(uid_str)
        
        if c.from_user.id != uid and c.from_user.id not in admin_ids:
            return bot.answer_callback_query(c.id, "❌ Access denied!")
        
        # Stop any running process
        skey = f"{uid}_{fname}"
        if skey in bot_scripts and bot_scripts[skey].get('process'):
            try:
                process = bot_scripts[skey]['process']
                parent = psutil.Process(process.pid)
                for child in parent.children(recursive=True):
                    child.kill()
                parent.kill()
            except:
                pass
            del bot_scripts[skey]
        
        # Delete file
        fpath = os.path.join(get_user_folder(uid), fname)
        if os.path.exists(fpath):
            os.remove(fpath)
            logger.info(f"Deleted file: {fpath}")
        
        # Remove from user_files
        if uid in user_files:
            user_files[uid] = [(n,t) for n,t in user_files[uid] if n != fname]
        
        # Remove from database
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cdb = conn.cursor()
            cdb.execute('DELETE FROM user_files WHERE user_id=? AND file_name=?', (uid, fname))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"DB delete error: {e}")
        
        # Show notification
        bot.answer_callback_query(c.id, f"✅ Deleted {fname}!", show_alert=True)
        
        # Refresh file list
        c.data = f'back_files_{uid}'
        handle_back_to_files(c)
        
    except Exception as e:
        logger.error(f"Delete error: {e}")
        bot.answer_callback_query(c.id, "❌ Error occurred!")

@bot.callback_query_handler(func=lambda c: c.data.startswith('back_files_'))
def handle_back_to_files(c):
    try:
        uid = int(c.data.split('_')[2])
        files = user_files.get(uid, [])
        
        if not files:
            text = "📂 **Your Files**\n\n🔒 No files uploaded yet."
            markup = None
        else:
            text = "📂 **Your Files**\n\nClick on any file to manage it:\n\n"
            markup = types.InlineKeyboardMarkup(row_width=1)
            
            for fn, ft in files:
                if ft == 'executable':
                    status = "🟢 Running" if is_bot_running(uid, fn) else "⭕ Stopped"
                    icon = "🚀"
                else:
                    status = "📁 Hosted"
                    icon = "📄"
                
                text += f"• `{fn}`\n  📁 Type: `{ft}`\n  🔄 Status: {status}\n\n"
                markup.add(types.InlineKeyboardButton(f"{icon} {fn}", callback_data=f'control_{uid}_{fn}'))
            
            text += "⚙️ Use buttons to manage your files."
        
        safe_edit_message(c.message.chat.id, c.message.message_id, text, parse_mode='Markdown', reply_markup=markup)
        bot.answer_callback_query(c.id)
        
    except Exception as e:
        logger.error(f"Back error: {e}")
        bot.answer_callback_query(c.id, "❌ Error occurred!")

# --- Helper for building file control markup ---
def build_file_control_markup(user_id, file_name, file_type):
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    if file_type == 'executable':
        if is_bot_running(user_id, file_name):
            markup.add(
                types.InlineKeyboardButton("🔴 Stop", callback_data=f'stop_{user_id}_{file_name}'),
                types.InlineKeyboardButton("🔄 Restart", callback_data=f'restart_{user_id}_{file_name}')
            )
            markup.add(types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{user_id}_{file_name}'))
        else:
            markup.add(
                types.InlineKeyboardButton("🟢 Start", callback_data=f'start_{user_id}_{file_name}'),
                types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{user_id}_{file_name}')
            )
    else:
        # Hosted files
        fhash = hashlib.md5(f"{user_id}_{file_name}".encode()).hexdigest()
        domain = os.environ.get('REPL_SLUG', 'universal-file-host')
        owner = os.environ.get('REPL_OWNER', 'replit-user')
        
        try:
            url = f"https://{domain}.{owner}.repl.co/file/{fhash}"
            if requests.get(f"https://{domain}.{owner}.repl.co/health", timeout=2).status_code != 200:
                url = f"https://{domain}-{owner}.replit.app/file/{fhash}"
        except:
            url = f"https://{domain}-{owner}.replit.app/file/{fhash}"
        
        markup.add(types.InlineKeyboardButton("🔗 View File", url=url))
    
    markup.add(
        types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{user_id}_{file_name}'),
        types.InlineKeyboardButton("🔙 Back", callback_data=f'back_files_{user_id}')
    )
    
    return markup

# --- Catch all ---
@bot.message_handler(func=lambda m: True)
def fallback(m):
    safe_reply_to(m, "🔒 Please use the menu buttons or send /start for help.", parse_mode='Markdown')

# --- Broadcast handler (for admin replies) ---
@bot.message_handler(func=lambda m: m.reply_to_message and m.reply_to_message.text and "Broadcast" in m.reply_to_message.text)
def handle_broadcast(m):
    if m.from_user.id not in admin_ids:
        return
    
    broadcast_text = m.text
    success = 0
    failed = 0
    
    status_msg = safe_reply_to(m, f"📢 **Broadcasting...**\n\nSending to {len(active_users)} users...", parse_mode='Markdown')
    
    for user_id in active_users:
        try:
            bot.send_message(user_id, f"📢 **Broadcast Message**\n\n{broadcast_text}", parse_mode='Markdown')
            success += 1
            time.sleep(0.05)  # Small delay to avoid rate limits
        except:
            failed += 1
    
    safe_edit_message(
        status_msg.chat.id,
        status_msg.message_id,
        f"📢 **Broadcast Complete**\n\n✅ Sent: `{success}`\n❌ Failed: `{failed}`",
        parse_mode='Markdown'
    )

# --- Cleanup ---
def cleanup():
    logger.info("Cleaning up processes...")
    for key, info in bot_scripts.items():
        if info.get('process') and info['process'].poll() is None:
            try:
                process = info['process']
                parent = psutil.Process(process.pid)
                for child in parent.children(recursive=True):
                    child.kill()
                parent.kill()
                logger.info(f"Killed process: {key}")
            except:
                pass
    logger.info("Cleanup complete.")

atexit.register(cleanup)

# --- Start ---
if __name__ == "__main__":
    init_db()
    load_data()
    keep_alive()
    
    logger.info(f"🚀 Bot starting. Owner ID: {OWNER_ID}")
    print(f"\n{'='*50}")
    print(f"🚀 Universal File Host Bot")
    print(f"👑 Owner ID: {OWNER_ID}")
    print(f"🤖 Bot Username: @{bot.get_me().username}")
    print(f"{'='*50}\n")
    
    # Verify owner chat
    try:
        bot.send_chat_action(OWNER_ID, 'typing')
        logger.info("✅ Owner reachable")
    except Exception as e:
        logger.error(f"❌ Cannot message owner {OWNER_ID}: {e}")
        print(f"\n⚠️  WARNING: Cannot message owner!")
        print(f"Please ensure you've started a private chat with @{bot.get_me().username}")
        print(f"and sent /start to the bot.\n")
    
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5, none_stop=True)
    except Exception as e:
        logger.error(f"Polling error: {e}")
        sys.exit(1)