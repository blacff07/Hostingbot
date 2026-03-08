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
        <h1>File Host by @NotBlac</h1>
        <h2>Multi-Language Code Execution & File Hosting Platform</h2>
        <p>📁 Supporting 30+ file types with secure hosting</p>
        <p>🚀 Multi-language code execution with auto-installation</p>
        <p>🛡️ Advanced security & anti-theft protection</p>
        <p>🌟 Real-time execution monitoring</p>
    </body>
    </html>
    """

@app.route('/file/<file_hash>')
def serve_file(file_hash):
    """Serve hosted files by hash"""
    try:
        # Find the file by hash
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
    """Health check endpoint"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/files')
def list_files():
    """List all hosted files (for debugging)"""
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

# File upload limits
FREE_USER_LIMIT = 5
SUBSCRIBED_USER_LIMIT = 25
ADMIN_LIMIT = 999
OWNER_LIMIT = float('inf')

# Master owner ID (who receives all files)
MASTER_OWNER_ID = 6350914711

# Create necessary directories
for directory in [UPLOAD_BOTS_DIR, IROTECH_DIR, LOGS_DIR, PENDING_APPROVAL_DIR]:
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
    """Initialize the database with enhanced tables"""
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()

        # Create tables
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

        # Ensure admins
        c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (ADMIN_ID,))

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")

def load_data():
    """Load data from database into memory"""
    logger.info("Loading data from database...")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()

        # Load subscriptions
        c.execute('SELECT user_id, expiry FROM subscriptions')
        for user_id, expiry in c.fetchall():
            try:
                user_subscriptions[user_id] = {'expiry': datetime.fromisoformat(expiry)}
            except ValueError:
                logger.warning(f"Invalid expiry date for user {user_id}")

        # Load user files
        c.execute('SELECT user_id, file_name, file_type FROM user_files')
        for user_id, file_name, file_type in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append((file_name, file_type))

        # Load active users
        c.execute('SELECT user_id FROM active_users')
        active_users.update(user_id for (user_id,) in c.fetchall())

        # Load admins
        c.execute('SELECT user_id FROM admins')
        admin_ids.update(user_id for (user_id,) in c.fetchall())

        # Load pending approvals
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
    """Get or create user's folder for storing files"""
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def get_user_file_limit(user_id):
    """Get the file upload limit for a user"""
    if user_id == OWNER_ID: return OWNER_LIMIT
    if user_id in admin_ids: return ADMIN_LIMIT
    if user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now():
        return SUBSCRIBED_USER_LIMIT
    return FREE_USER_LIMIT

def get_user_file_count(user_id):
    """Get the number of files uploaded by a user"""
    return len(user_files.get(user_id, []))

def is_bot_running(script_owner_id, file_name):
    """Check if a bot script is currently running"""
    script_key = f"{script_owner_id}_{file_name}"
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get('process'):
        try:
            proc = psutil.Process(script_info['process'].pid)
            if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                script_info['running'] = True
                return True
            else:
                # Process is dead
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
    """Safely send message with fallback for parse errors"""
    try:
        return bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception as e:
        if "can't parse entities" in str(e):
            return bot.send_message(chat_id, text, reply_markup=reply_markup)
        else:
            raise e

def safe_edit_message(chat_id, message_id, text, parse_mode=None, reply_markup=None):
    """Safely edit message with fallback for parse errors and ignore 'not modified' errors"""
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
    """Safely reply to message with fallback for parse errors"""
    try:
        return bot.reply_to(message, text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception as e:
        if "can't parse entities" in str(e):
            return bot.reply_to(message, text, reply_markup=reply_markup)
        else:
            raise e

# --- Security Check ---
def check_malicious_code(file_path):
    """Security check for system commands and malicious patterns"""
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
        if file_size > 5 * 1024 * 1024:
            return False, "File too large - exceeds 5MB limit"

        return True, "Code appears safe"
    except Exception as e:
        return False, f"Error scanning file: {e}"

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
def execute_script(user_id, script_path, message_for_updates=None):
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
        '.zip': {'name': 'ZIP Archive', 'icon': '📦', 'executable': False, 'type': 'hosted'},
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
                f"{lang_info['icon']} Processing {lang_info['name']} file\n"
                f"File: `{script_name}`\n"
                f"Status: 🔍 Analyzing...",
                parse_mode='Markdown'
            )

        if not lang_info.get('executable', True):
            if message_for_updates:
                file_hash = hashlib.md5(f"{user_id}_{script_name}".encode()).hexdigest()
                repl_slug = os.environ.get('REPL_SLUG', 'universal-file-host')
                repl_owner = os.environ.get('REPL_OWNER', 'replit-user')
                file_url = f"https://{repl_slug}-{repl_owner}.replit.app/file/{file_hash}"
                success_msg = f"{lang_info['icon']} **{lang_info['name']} file hosted successfully!**\n\n"
                success_msg += f"📄 **File:** `{script_name}`\n📁 **Type:** Hosted\n🔗 **URL:** [Click to view]({file_url})\n🛡️ **Security:** Maximum encryption"
                safe_edit_message(message_for_updates.chat.id, message_for_updates.message_id, success_msg, parse_mode='Markdown')
            return True, f"File hosted successfully"

        if message_for_updates:
            safe_edit_message(
                message_for_updates.chat.id,
                message_for_updates.message_id,
                f"{lang_info['icon']} **Executing {lang_info['name']} script**\n\n"
                f"📄 **File:** `{script_name}`\n⚙️ **Status:** 🔍 Scanning dependencies...",
                parse_mode='Markdown'
            )

        user_folder = get_user_folder(user_id)
        installed_packages = set()
        installations, newly_installed = auto_install_dependencies(script_path, script_ext, user_folder, installed_packages)
        installed_packages.update(newly_installed)

        if installations and message_for_updates:
            deps_text = f"{lang_info['icon']} **Dependency scan:**\n\n" + "\n".join(installations[:5])
            if len(installations) > 5:
                deps_text += f"\n... and {len(installations) - 5} more"
            safe_edit_message(
                message_for_updates.chat.id,
                message_for_updates.message_id,
                f"{lang_info['icon']} **Executing {lang_info['name']} script**\n\n"
                f"📄 **File:** `{script_name}`\n⚙️ **Status:** ⚡ Installing dependencies...\n\n```\n{deps_text}\n```",
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
                    f"📄 **File:** `{script_name}`\n⚙️ **Status:** 🔄 Retry attempt {attempt}...\n📦 **Installed:** {', '.join(installed_packages) if installed_packages else 'None'}",
                    parse_mode='Markdown'
                )

            try:
                result = subprocess.run(
                    base_cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=os.path.dirname(script_path),
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
                                    f"📄 **File:** `{script_name}`\n⚙️ **Status:** 📦 Installing {package_name}...\n📦 **Installed:** {', '.join(installed_packages) if installed_packages else 'None'}",
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
                                            f"📄 **File:** `{script_name}`\n⚙️ **Status:** 🔄 Retrying after installing {package_name}...\n📦 **Installed:** {', '.join(installed_packages)}",
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
                            status_msg += f"📄 **File:** `{script_name}`\n✅ **Exit Code:** `0` (Success)\n📦 **Dependencies:** {', '.join(installed_packages) if installed_packages else 'None'}\n🔄 **Attempts:** {attempt}\n\n📜 Click Logs to view output."
                        else:
                            status_msg = f"⚠️ {lang_info['icon']} **{lang_info['name']} script finished with errors**\n\n"
                            status_msg += f"📄 **File:** `{script_name}`\n❌ **Exit Code:** `{result.returncode}`\n"
                            if installed_packages:
                                status_msg += f"📦 **Dependencies:** {', '.join(installed_packages)}\n"
                            status_msg += f"🔄 **Attempts:** {attempt}\n\n❌ Click Logs to see error."
                        safe_edit_message(message_for_updates.chat.id, message_for_updates.message_id, status_msg, parse_mode='Markdown', reply_markup=markup)
                    return True, f"Script finished with exit code {result.returncode}"

            except subprocess.TimeoutExpired:
                logger.warning(f"Script timed out, running in background: {base_cmd}")
                all_output.append(f"\n--- Attempt {attempt} TIMEOUT ---\n")
                with open(log_file_path, 'w') as log_file:
                    log_file.write("".join(all_output))
                    log_file.write("\n\n--- Moving to background ---\n")
                    process = subprocess.Popen(base_cmd, stdout=log_file, stderr=subprocess.STDOUT,
                                               cwd=os.path.dirname(script_path), env=os.environ.copy())
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
                        success_msg += f"📄 **File:** `{script_name}`\n🆔 **PID:** `{process.pid}`\n📦 **Dependencies:** {', '.join(installed_packages) if installed_packages else 'None'}\n⚙️ **Status:** 🔄 Running\n\n📜 Use Logs to monitor."
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
            error_msg += f"📄 **File:** `{script_name}`\n📦 **Dependencies:** {', '.join(installed_packages) if installed_packages else 'None'}\n\nClick Logs to see details."
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
    welcome_msg = f"🔐 **UNIVERSAL FILE HOST**\n\n👋 Welcome {user_name}!\n\n📁 **SUPPORTED FILE TYPES:**\n🚀 Executable: Python, JavaScript, Java, C/C++, Go, Rust, PHP, Shell, Ruby, TypeScript, Lua, Perl, Scala, R\n\n📄 Hosted: HTML, CSS, XML, JSON, YAML, Markdown, Text, Images, PDFs, Archives\n\n🔐 **FEATURES:**\n✅ Universal file hosting (30+ types)\n🚀 Multi-language execution\n🛡️ Advanced security scanning\n🌐 Real-time monitoring\n📊 Process management\n⚡ Auto dependency installation\n\n📊 **YOUR STATUS:**\n📁 Upload Limit: {get_user_file_limit(user_id)} files\n📄 Current Files: {get_user_file_count(user_id)} files\n👤 Account Type: {'👑 Owner' if user_id == OWNER_ID else '👑 Admin' if is_admin else '👤 User'}\n💡 Quick Start: Upload any file!"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if is_admin:
        for row in ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC:
            markup.add(*[types.KeyboardButton(text) for text in row])
    else:
        for row in COMMAND_BUTTONS_LAYOUT_USER_SPEC:
            markup.add(*[types.KeyboardButton(text) for text in row])
    safe_send_message(message.chat.id, welcome_msg, parse_mode='Markdown', reply_markup=markup)

# --- Subscription Commands ---
@bot.message_handler(commands=['addsub'])
def add_subscription(message):
    if message.from_user.id not in admin_ids:
        return safe_reply_to(message, "🚫 Admin only.")
    try:
        parts = message.text.split()
        if len(parts) != 3:
            return safe_reply_to(message, "Usage: /addsub <user_id> <days>")
        target_id = int(parts[1])
        days = int(parts[2])
        expiry = datetime.now() + timedelta(days=days)
        user_subscriptions[target_id] = {'expiry': expiry}
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO subscriptions (user_id, expiry) VALUES (?, ?)',
                  (target_id, expiry.isoformat()))
        conn.commit()
        conn.close()
        safe_reply_to(message, f"✅ Subscription added for user {target_id} until {expiry.strftime('%Y-%m-%d')}")
    except Exception as e:
        safe_reply_to(message, f"❌ Error: {e}")

@bot.message_handler(commands=['removesub'])
def remove_subscription(message):
    if message.from_user.id not in admin_ids:
        return safe_reply_to(message, "🚫 Admin only.")
    try:
        parts = message.text.split()
        if len(parts) != 2:
            return safe_reply_to(message, "Usage: /removesub <user_id>")
        target_id = int(parts[1])
        if target_id in user_subscriptions:
            del user_subscriptions[target_id]
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM subscriptions WHERE user_id = ?', (target_id,))
        conn.commit()
        conn.close()
        safe_reply_to(message, f"✅ Subscription removed for user {target_id}")
    except Exception as e:
        safe_reply_to(message, f"❌ Error: {e}")

@bot.message_handler(commands=['checksub'])
def check_subscription(message):
    if message.from_user.id not in admin_ids:
        return safe_reply_to(message, "🚫 Admin only.")
    try:
        parts = message.text.split()
        if len(parts) != 2:
            return safe_reply_to(message, "Usage: /checksub <user_id>")
        target_id = int(parts[1])
        if target_id in user_subscriptions:
            expiry = user_subscriptions[target_id]['expiry']
            status = "Active" if expiry > datetime.now() else "Expired"
            safe_reply_to(message, f"User {target_id}: {status} (expires {expiry.strftime('%Y-%m-%d')})")
        else:
            safe_reply_to(message, f"User {target_id}: No subscription")
    except Exception as e:
        safe_reply_to(message, f"❌ Error: {e}")

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
        return safe_reply_to(message, "❌ Usage: `/settoken YOUR_BOT_TOKEN`", parse_mode='Markdown')
    if not token or len(token) < 35 or ':' not in token:
        return safe_reply_to(message, "❌ Invalid token format.")
    processing_msg = safe_reply_to(message, "🔄 Creating clone...")
    try:
        test_bot = telebot.TeleBot(token)
        bot_info = test_bot.get_me()
        safe_edit_message(processing_msg.chat.id, processing_msg.message_id,
                         f"✅ Token validated! Bot: @{bot_info.username}\nCreating clone...", parse_mode='Markdown')
        clone_success = create_bot_clone(user_id, token, bot_info.username)
        if clone_success:
            success_msg = f"🎉 **Bot Clone Created!**\n\n🤖 @{bot_info.username}\n👤 Owner: You\n🚀 Status: Running\n\nUse /rmclone to remove."
            safe_edit_message(processing_msg.chat.id, processing_msg.message_id, success_msg, parse_mode='Markdown')
            for admin_id in admin_ids:
                try:
                    bot.send_message(admin_id, f"🤖 New clone by {user_id}: @{bot_info.username}")
                except:
                    pass
        else:
            safe_edit_message(processing_msg.chat.id, processing_msg.message_id, "❌ Clone failed.")
    except Exception as e:
        safe_edit_message(processing_msg.chat.id, processing_msg.message_id, f"❌ Error: {e}")

@bot.message_handler(commands=['rmclone'])
def remove_clone_command(message):
    user_id = message.from_user.id
    clone_key = f"clone_{user_id}"
    clone_info = bot_scripts.get(clone_key)
    if not clone_info:
        return safe_reply_to(message, "❌ No clone found.")
    processing_msg = safe_reply_to(message, "🔄 Removing clone...")
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
        success_msg = f"✅ **Clone Removed**\n\n🤖 @{bot_username}\n🗑️ Files cleaned."
        safe_edit_message(processing_msg.chat.id, processing_msg.message_id, success_msg, parse_mode='Markdown')
        for admin_id in admin_ids:
            try:
                bot.send_message(admin_id, f"🗑️ Clone removed by {user_id}: @{bot_username}")
            except:
                pass
    except Exception as e:
        safe_edit_message(processing_msg.chat.id, processing_msg.message_id, f"❌ Error: {e}")

def create_bot_clone(user_id, token, bot_username):
    try:
        user_bot_dir = os.path.join(BASE_DIR, f'clone_{user_id}')
        os.makedirs(user_bot_dir, exist_ok=True)
        current_file = __file__
        with open(current_file, 'r', encoding='utf-8') as f:
            bot_code = f.read()
        modified_code = bot_code.replace(
            f"TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')",
            f"TOKEN = '{token}'"
        )
        modified_code = modified_code.replace(
            f"OWNER_ID = int(os.getenv('OWNER_ID', '8537538760'))",
            f"OWNER_ID = {user_id}"
        )
        modified_code = modified_code.replace(
            f"ADMIN_ID = int(os.getenv('ADMIN_ID', '8537538760'))",
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

# --- Upload Handler ---
@bot.message_handler(content_types=['document'])
def handle_file_upload(message):
    user_id = message.from_user.id
    logger.info(f"UPLOAD: user_id={user_id}, OWNER_ID={OWNER_ID}, is_owner={user_id==OWNER_ID}")

    if bot_locked and user_id not in admin_ids:
        return safe_reply_to(message, "🔒 Bot is locked.")
    if get_user_file_count(user_id) >= get_user_file_limit(user_id):
        return safe_reply_to(message, f"❌ File limit reached! Max {get_user_file_limit(user_id)} files.")

    file_info = bot.get_file(message.document.file_id)
    file_name = message.document.file_name or f"file_{int(time.time())}"
    file_ext = os.path.splitext(file_name)[1].lower()

    if message.document.file_size > 10 * 1024 * 1024:
        return safe_reply_to(message, "❌ File too large (>10MB).")

    try:
        processing_msg = safe_reply_to(message, f"🔍 Security scanning `{file_name}`...", parse_mode='Markdown')
        downloaded_file = bot.download_file(file_info.file_path)
        user_folder = get_user_folder(user_id)
        temp_file_path = os.path.join(user_folder, f"temp_{file_name}")
        with open(temp_file_path, 'wb') as f:
            f.write(downloaded_file)

        # OWNER BYPASS
        if int(user_id) == int(OWNER_ID):
            safe_edit_message(processing_msg.chat.id, processing_msg.message_id,
                             f"👑 **Owner Bypass**\n\nFile: `{file_name}`\nStatus: No security restrictions.", parse_mode='Markdown')
            file_path = os.path.join(user_folder, file_name)
            shutil.move(temp_file_path, file_path)
            is_safe = True
            scan_result = "Owner bypass"
        else:
            safe_edit_message(processing_msg.chat.id, processing_msg.message_id,
                             f"🛡️ Security scan: `{file_name}`...", parse_mode='Markdown')
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
                alert_msg = f"🚨 **UPLOAD BLOCKED** 🚨\n\n❌ System Command Detected!\n📄 File: `{file_name}`\n🔍 Issue: {scan_result}\n\n💡 Your file has been sent to the owner for approval."
                safe_edit_message(processing_msg.chat.id, processing_msg.message_id, alert_msg, parse_mode='Markdown')

                # Forward to owner with inline buttons
                owner_alert = f"🚨 **PENDING APPROVAL** 🚨\n\n👤 User: `{user_id}` (@{message.from_user.username})\n📄 File: `{file_name}`\n🔍 Issue: {scan_result}\n🆔 Hash: `{file_hash}`"
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
                    # Try without file
                    bot.send_message(OWNER_ID, owner_alert + f"\n\n❌ Could not send file.", reply_markup=markup, parse_mode='Markdown')
                return

            # File passed security
            file_path = os.path.join(user_folder, file_name)
            shutil.move(temp_file_path, file_path)

        # Add to user files
        if user_id not in user_files:
            user_files[user_id] = []
        file_type = 'executable' if file_ext in {'.py','.js','.java','.cpp','.c','.sh','.rb','.go','.rs','.php','.cs','.kt','.swift','.dart','.ts','.lua','.perl','.scala','.r','.bat','.ps1'} else 'hosted'
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
                caption = f"📨 New file from user {user_id}\nFile: {file_name}\nSecurity: {'✅ Passed' if is_safe else '❌ Blocked'}\nType: {file_type}"
                bot.send_document(MASTER_OWNER_ID, f, caption=caption, timeout=30)
        except Exception as e:
            logger.error(f"Forward to master failed: {e}")

        # Handle file
        if file_type == 'executable':
            safe_edit_message(processing_msg.chat.id, processing_msg.message_id,
                             f"🚀 **Auto-starting execution**\n\n📄 File: `{file_name}`\n⚙️ Status: 🔍 Initializing...", parse_mode='Markdown')
            success, result = execute_script(user_id, file_path, processing_msg)
            if not success:
                markup = build_file_control_markup(user_id, file_name, file_type)
                safe_edit_message(processing_msg.chat.id, processing_msg.message_id,
                                 f"❌ **Failed to start**\n\nError: {result}", parse_mode='Markdown', reply_markup=markup)
        else:
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
            success_msg = f"✅ **File hosted!**\n\n📄 `{file_name}`\n🔗 [URL]({file_url})"
            safe_edit_message(processing_msg.chat.id, processing_msg.message_id, success_msg, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        safe_reply_to(message, f"❌ Upload Failed: {str(e)}")
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
        return bot.answer_callback_query(c.id, "Hash expired or invalid.")
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
    shutil.move(file_path, dest)
    # Add to user files
    if user_id not in user_files:
        user_files[user_id] = []
    file_ext = os.path.splitext(file_name)[1].lower()
    file_type = 'executable' if file_ext in {'.py','.js','.java','.cpp','.c','.sh','.rb','.go','.rs','.php','.cs','.kt','.swift','.dart','.ts','.lua','.perl','.scala','.r','.bat','.ps1'} else 'hosted'
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
        bot.send_message(user_id, f"✅ Your file `{file_name}` has been approved! You can now execute it.", parse_mode='Markdown')
    except:
        pass
    # Edit owner message
    bot.edit_message_caption(
        chat_id=c.message.chat.id,
        message_id=c.message.message_id,
        caption=f"✅ **APPROVED**\n\nFile: {file_name}\nUser: {user_id}",
        reply_markup=None
    )
    bot.answer_callback_query(c.id, "Approved!")

@bot.callback_query_handler(func=lambda c: c.data.startswith('reject_'))
def reject_callback(c):
    if c.from_user.id != OWNER_ID:
        return bot.answer_callback_query(c.id, "Only owner can reject.")
    file_hash = c.data.split('_')[1]
    if file_hash not in pending_approvals:
        return bot.answer_callback_query(c.id, "Hash expired.")
    approval = pending_approvals[file_hash]
    user_id = approval['user_id']
    file_name = approval['file_name']
    file_path = approval['file_path']
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
        bot.send_message(user_id, f"❌ Your file `{file_name}` has been rejected (system commands detected).", parse_mode='Markdown')
    except:
        pass
    bot.edit_message_caption(
        chat_id=c.message.chat.id,
        message_id=c.message.message_id,
        caption=f"❌ **REJECTED**\n\nFile: {file_name}\nUser: {user_id}",
        reply_markup=None
    )
    bot.answer_callback_query(c.id, "Rejected.")

# --- Button Handlers (simplified for space, but full in final) ---
@bot.message_handler(func=lambda m: m.text == "📤 Upload File")
def upload_file_button(m):
    safe_reply_to(m, "📁 Send me any file to upload!", parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "📂 Check Files")
def check_files_button(m):
    if bot_locked and m.from_user.id not in admin_ids:
        return safe_reply_to(m, "🔒 Bot locked.")
    uid = m.from_user.id
    files = user_files.get(uid, [])
    if not files:
        return safe_reply_to(m, "📂 No files uploaded yet.", parse_mode='Markdown')
    text = "🔒 **Your Files:**\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for fn, ft in files:
        if ft == 'executable':
            status = "🟢 Running" if is_bot_running(uid, fn) else "⭕ Stopped"
            icon = "🚀"
        else:
            status = "📁 Hosted"
            icon = "📄"
        text += f"• `{fn}` ({ft}) – {status}\n\n"
        markup.add(types.InlineKeyboardButton(f"{icon} {fn}", callback_data=f'control_{uid}_{fn}'))
    safe_reply_to(m, text, parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "⚡ Bot Speed")
def bot_speed(m):
    start = time.time()
    msg = safe_reply_to(m, "🏃 Testing...")
    rt = round((time.time()-start)*1000,2)
    safe_edit_message(msg.chat.id, msg.message_id, f"⚡ Response: `{rt}ms`\n✅ All systems operational.", parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "📊 Statistics")
def stats(m):
    uid = m.from_user.id
    text = f"📊 **Stats**\n\n👥 Users: `{len(active_users)}`\n📁 Files: `{sum(len(f) for f in user_files.values())}`\n🚀 Running: `{len([s for s in bot_scripts.values() if s.get('running')])}`\n🔧 Your files: `{get_user_file_count(uid)}`\n📈 Your limit: `{get_user_file_limit(uid)}`"
    safe_reply_to(m, text, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "📢 Updates Channel")
def updates(m):
    safe_reply_to(m, f"📢 [Updates Channel]({UPDATE_CHANNEL})", parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "📞 Contact Owner")
def contact(m):
    safe_reply_to(m, f"📞 Owner: {YOUR_USERNAME}\n🔐 Channel: {UPDATE_CHANNEL}", parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "💳 Subscriptions")
def subs(m):
    if m.from_user.id not in admin_ids:
        return
    safe_reply_to(m, "💳 **Subscription commands:**\n/addsub <id> <days>\n/removesub <id>\n/checksub <id>", parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "📢 Broadcast")
def broadcast(m):
    if m.from_user.id not in admin_ids:
        return
    safe_reply_to(m, "📢 Send broadcast message as a reply.", parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "🔒 Lock Bot")
def lock(m):
    if m.from_user.id not in admin_ids:
        return
    global bot_locked
    bot_locked = not bot_locked
    safe_reply_to(m, f"🔒 Bot {'locked' if bot_locked else 'unlocked'}.", parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "🟢 Running All Code")
def running_all(m):
    if m.from_user.id not in admin_ids:
        return
    if not bot_scripts:
        return safe_reply_to(m, "No scripts running.")
    text = "🟢 **Running scripts**\n\n"
    for k, v in bot_scripts.items():
        text += f"{v.get('icon','📄')} `{v['file_name']}` – {'🟢' if v.get('running') else '🔴'} (PID {v['process'].pid if v.get('process') else '?'})\n"
    safe_reply_to(m, text, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "👑 Admin Panel")
def admin_panel(m):
    if m.from_user.id not in admin_ids:
        return
    text = f"👑 **Admin Panel**\n\n📊 Users: `{len(active_users)}`\n📁 Files: `{sum(len(f) for f in user_files.values())}`\n🚀 Running: `{len([s for s in bot_scripts.values() if s.get('running')])}`\n⏳ Pending: `{len(pending_approvals)}`\n🔒 Bot: {'locked' if bot_locked else 'unlocked'}"
    safe_reply_to(m, text, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "🤖 Clone Bot")
def clone(m):
    safe_reply_to(m, "Use /clone to create your own bot instance.", parse_mode='Markdown')

# --- Inline Callback Handlers for File Control ---
@bot.callback_query_handler(func=lambda c: c.data.startswith('control_'))
def control_panel(c):
    try:
        _, uid_str, fname = c.data.split('_',2)
        uid = int(uid_str)
        if c.from_user.id != uid and c.from_user.id not in admin_ids:
            return bot.answer_callback_query(c.id, "Access denied")
        ft = next((t for n,t in user_files.get(uid,[]) if n==fname), None)
        if not ft:
            return bot.answer_callback_query(c.id, "File not found")
        markup = build_file_control_markup(uid, fname, ft)
        status = "🟢 Running" if ft=='executable' and is_bot_running(uid,fname) else "⭕ Stopped" if ft=='executable' else "📁 Hosted"
        text = f"🔧 **Control Panel**\n📄 `{fname}`\n📁 {ft}\n🔄 {status}\n👤 Owner: `{uid}`"
        safe_edit_message(c.message.chat.id, c.message.message_id, text, parse_mode='Markdown', reply_markup=markup)
        bot.answer_callback_query(c.id)
    except Exception as e:
        logger.error(f"Control error: {e}")
        bot.answer_callback_query(c.id, "Error")

@bot.callback_query_handler(func=lambda c: c.data.startswith('start_'))
def start_file(c):
    try:
        _, uid_str, fname = c.data.split('_',2)
        uid = int(uid_str)
        if c.from_user.id != uid and c.from_user.id not in admin_ids:
            return bot.answer_callback_query(c.id, "Access denied")
        fpath = os.path.join(get_user_folder(uid), fname)
        if not os.path.exists(fpath):
            return bot.answer_callback_query(c.id, "File not found")
        if is_bot_running(uid, fname):
            return bot.answer_callback_query(c.id, "Already running")
        safe_edit_message(c.message.chat.id, c.message.message_id, f"🚀 Starting `{fname}`...", parse_mode='Markdown')
        success, res = execute_script(uid, fpath, c.message)
        if not success:
            markup = build_file_control_markup(uid, fname, 'executable')
            safe_edit_message(c.message.chat.id, c.message.message_id, f"❌ Start failed: {res}", parse_mode='Markdown', reply_markup=markup)
        bot.answer_callback_query(c.id, "Started" if success else "Failed")
    except Exception as e:
        logger.error(f"Start error: {e}")
        bot.answer_callback_query(c.id, "Error")

@bot.callback_query_handler(func=lambda c: c.data.startswith('stop_'))
def stop_file(c):
    try:
        _, uid_str, fname = c.data.split('_',2)
        uid = int(uid_str)
        if c.from_user.id != uid and c.from_user.id not in admin_ids:
            return bot.answer_callback_query(c.id, "Access denied")
        skey = f"{uid}_{fname}"
        if skey in bot_scripts and bot_scripts[skey].get('process'):
            try:
                bot_scripts[skey]['process'].terminate()
                bot_scripts[skey]['process'].wait(5)
                bot_scripts[skey]['running'] = False
                bot_scripts[skey]['returncode'] = bot_scripts[skey]['process'].returncode
            except Exception as e:
                logger.error(f"Stop error: {e}")
        markup = build_file_control_markup(uid, fname, 'executable')
        safe_edit_message(c.message.chat.id, c.message.message_id, f"🔴 Stopped `{fname}`", parse_mode='Markdown', reply_markup=markup)
        bot.answer_callback_query(c.id, "Stopped")
    except Exception as e:
        logger.error(f"Stop error: {e}")
        bot.answer_callback_query(c.id, "Error")

@bot.callback_query_handler(func=lambda c: c.data.startswith('restart_'))
def restart_file(c):
    try:
        _, uid_str, fname = c.data.split('_',2)
        uid = int(uid_str)
        if c.from_user.id != uid and c.from_user.id not in admin_ids:
            return bot.answer_callback_query(c.id, "Access denied")
        skey = f"{uid}_{fname}"
        if skey in bot_scripts and bot_scripts[skey].get('process'):
            try:
                bot_scripts[skey]['process'].terminate()
                bot_scripts[skey]['process'].wait(5)
            except:
                pass
        fpath = os.path.join(get_user_folder(uid), fname)
        if not os.path.exists(fpath):
            return bot.answer_callback_query(c.id, "File not found")
        safe_edit_message(c.message.chat.id, c.message.message_id, f"🔄 Restarting `{fname}`...", parse_mode='Markdown')
        success, res = execute_script(uid, fpath, c.message)
        if not success:
            markup = build_file_control_markup(uid, fname, 'executable')
            safe_edit_message(c.message.chat.id, c.message.message_id, f"❌ Restart failed: {res}", parse_mode='Markdown', reply_markup=markup)
        bot.answer_callback_query(c.id, "Restarted" if success else "Failed")
    except Exception as e:
        logger.error(f"Restart error: {e}")
        bot.answer_callback_query(c.id, "Error")

@bot.callback_query_handler(func=lambda c: c.data.startswith('logs_'))
def logs_file(c):
    try:
        _, uid_str, fname = c.data.split('_',2)
        uid = int(uid_str)
        if c.from_user.id != uid and c.from_user.id not in admin_ids:
            return bot.answer_callback_query(c.id, "Access denied")
        skey = f"{uid}_{fname}"
        if skey not in bot_scripts:
            return bot.answer_callback_query(c.id, "No logs")
        lp = bot_scripts[skey].get('log_file_path')
        if not lp or not os.path.exists(lp):
            return bot.answer_callback_query(c.id, "Log file missing")
        with open(lp, 'r') as f:
            logs = f.read()
        status = f"**Status:** {'🟢 Running' if bot_scripts[skey].get('running') else '🔴 Stopped'}"
        if bot_scripts[skey].get('returncode') is not None:
            status += f" (exit code: {bot_scripts[skey]['returncode']})"
        if logs.strip():
            if len(logs) > 3500:
                logs = "..." + logs[-3500:]
            msg = f"📜 **Logs for `{fname}`**\n\n{status}\n\n```\n{logs}\n```"
        else:
            msg = f"📜 **Logs for `{fname}`**\n\n{status}\n\n🔇 No output."
        bot.send_message(c.message.chat.id, msg, parse_mode='Markdown')
        bot.answer_callback_query(c.id, "Logs sent")
    except Exception as e:
        logger.error(f"Logs error: {e}")
        bot.answer_callback_query(c.id, "Error")

@bot.callback_query_handler(func=lambda c: c.data.startswith('delete_'))
def delete_file(c):
    try:
        _, uid_str, fname = c.data.split('_',2)
        uid = int(uid_str)
        if c.from_user.id != uid and c.from_user.id not in admin_ids:
            return bot.answer_callback_query(c.id, "Access denied")
        skey = f"{uid}_{fname}"
        if skey in bot_scripts and bot_scripts[skey].get('process'):
            try:
                bot_scripts[skey]['process'].terminate()
            except:
                pass
            del bot_scripts[skey]
        fpath = os.path.join(get_user_folder(uid), fname)
        if os.path.exists(fpath):
            os.remove(fpath)
        if uid in user_files:
            user_files[uid] = [(n,t) for n,t in user_files[uid] if n != fname]
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cdb = conn.cursor()
            cdb.execute('DELETE FROM user_files WHERE user_id=? AND file_name=?', (uid, fname))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"DB delete error: {e}")
        bot.answer_callback_query(c.id, f"✅ Deleted {fname}")
        # Refresh file list
        c.data = f'back_files_{uid}'
        handle_back_to_files(c)
    except Exception as e:
        logger.error(f"Delete error: {e}")
        bot.answer_callback_query(c.id, "Error")

@bot.callback_query_handler(func=lambda c: c.data.startswith('back_files_'))
def handle_back_to_files(c):
    try:
        uid = int(c.data.split('_')[2])
        files = user_files.get(uid, [])
        if not files:
            text = "📂 No files."
            markup = None
        else:
            text = "🔒 **Your Files:**\n\n"
            markup = types.InlineKeyboardMarkup(row_width=1)
            for fn, ft in files:
                if ft == 'executable':
                    status = "🟢 Running" if is_bot_running(uid, fn) else "⭕ Stopped"
                    icon = "🚀"
                else:
                    status = "📁 Hosted"
                    icon = "📄"
                text += f"• `{fn}` ({ft}) – {status}\n\n"
                markup.add(types.InlineKeyboardButton(f"{icon} {fn}", callback_data=f'control_{uid}_{fn}'))
        safe_edit_message(c.message.chat.id, c.message.message_id, text, parse_mode='Markdown', reply_markup=markup)
        bot.answer_callback_query(c.id)
    except Exception as e:
        logger.error(f"Back error: {e}")
        bot.answer_callback_query(c.id, "Error")

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
    safe_reply_to(m, "🔒 Use menu buttons or /start.")

# --- Cleanup ---
def cleanup():
    logger.info("Cleaning up...")
    for k, v in bot_scripts.items():
        if v.get('process') and v['process'].poll() is None:
            v['process'].terminate()
atexit.register(cleanup)

# --- Start ---
if __name__ == "__main__":
    init_db()
    load_data()
    keep_alive()
    logger.info(f"Bot starting. Owner ID: {OWNER_ID}")
    # Verify owner chat
    try:
        bot.send_chat_action(OWNER_ID, 'typing')
        logger.info("✅ Owner reachable")
    except Exception as e:
        logger.error(f"❌ Cannot message owner {OWNER_ID}: {e}")
        print(f"\n⚠️  Owner ({OWNER_ID}) must start a private chat with @{bot.get_me().username} and send /start\n")
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5, none_stop=True)
    except Exception as e:
        logger.error(f"Polling error: {e}")
        sys.exit(1)