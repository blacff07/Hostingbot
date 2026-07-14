# 🤖 HostingBot

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Optional-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://core.telegram.org/bots)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
[![Flask](https://img.shields.io/badge/Flask-3.0-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)

*Professional Multi-User Hosting Platform via Telegram*

**Built by [Blac](https://t.me/blcqt) · [Updates](https://t.me/TechTipsCode) · [Support](https://t.me/EliteCodeLab)**

> **Hosting Support**: Render, Railway, Heroku, AWS EC2, DigitalOcean, Linode, and most cloud platforms

---

</div>

A powerful, production-ready Telegram bot for hosting, managing, and executing Python and Node.js code files with complete isolation, environment management, and administrative controls.

## 📋 Quick Links

- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Usage](#usage)
- [Web Hosting](#web-hosting)
- [Security](#security)
- [Troubleshooting](#troubleshooting)

---

## ✨ Features

### Core Functionality
- ✅ **File Upload & Hosting** - Upload Python, HTML, Node.js files and execute instantly
- ✅ **Code Execution** - Run files with output logging and error handling
- ✅ **Module Installation** - Install Python (pip), system (apt), and Node.js (npm) packages on demand
- ✅ **Environment Variables** - Set and manage environment variables per user
- ✅ **GitHub Integration** - Clone and manage repositories
- ✅ **Website Hosting** - Host static and dynamic HTML sites with custom URLs
- ✅ **Process Management** - View running processes, stop, restart with logging

### Data & Security
- ✅ **User Isolation** - Each user has isolated file and process space
- ✅ **SQLite Database** - Persistent storage for files, users, processes, subscriptions
- ✅ **Role-Based Access** - Public, Admin, and Owner-only controls
- ✅ **File Approval** - Owner approval for suspicious files
- ✅ **Force-Join** - Require users to join update/support channels
- ✅ **Ban Management** - Block users from bot access

### Admin Features
- ✅ **Admin Panel** - Full control over users and files
- ✅ **Subscription Management** - Premium tiers with usage limits
- ✅ **Bot Logging** - Complete activity and error logs
- ✅ **Broadcast** - Send messages to all users
- ✅ **Bot Lock** - Temporarily disable bot for maintenance

---

## 📊 System Requirements

### Minimum (Development)
- **OS**: Ubuntu 20.04+ / Debian 11+ / Any Linux with Python 3.8+
- **Python**: 3.8 or higher
- **RAM**: 512MB
- **Disk**: 500MB
- **Network**: Stable internet

### Recommended (Production)
- **OS**: Ubuntu 22.04 LTS
- **Python**: 3.10+
- **RAM**: 2-4GB
- **Disk**: 5-10GB
- **CPU**: 2+ cores
- **Docker**: 20.10+ (optional)

---

## 🔧 Installation

### Method 1: System Python (Development)

**1. Install Python**
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git
```

**2. Clone Repository**
```bash
git clone https://github.com/yourusername/Hostingbot.git
cd Hostingbot
```

**3. Create Virtual Environment**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**4. Install Dependencies**
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**5. Configure Bot**
```bash
cp .env.example .env
nano .env
```

**6. Run Bot**
```bash
python src/main.py
```

### Method 2: Docker (Production)

**1. Install Docker**
```bash
sudo apt update
sudo apt install -y docker.io docker-compose
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
newgrp docker
```

**2. Clone & Configure**
```bash
git clone https://github.com/yourusername/Hostingbot.git
cd Hostingbot
cp .env.example .env
nano .env
```

**3. Run with Docker Compose**
```bash
docker-compose up -d
```

### Method 3: Systemd Service (Production)

**1. Follow System Python installation above**

**2. Create Service**
```bash
sudo tee /etc/systemd/system/hostingbot.service > /dev/null << 'SYSTEMD'
[Unit]
Description=HostingBot Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/Hostingbot
ExecStart=/root/Hostingbot/.venv/bin/python /root/Hostingbot/src/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SYSTEMD

sudo systemctl enable hostingbot
sudo systemctl start hostingbot
sudo systemctl status hostingbot
```

---

## ⚙️ Configuration

### .env File

```env
# Telegram Bot
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
OWNER_ID=1234567890
ADMIN_ID=9876543210
OWNER_USERNAME=@blcqt

# Bot Settings
UPDATE_CHANNEL=https://t.me/TechTipsCode
SUPPORT_CHANNEL=https://t.me/EliteCodeLab

# Web Hosting - Choose ONE option:

# Option 1: Custom Domain (Recommended for Production)
HOST_URL=https://yourdomain.com

# Option 2: VPS IP with Port (Manual)
# HOST_URL=http://203.0.113.42:14000

# Option 3: Auto-detect VPS IP (Easiest for VPS)
# Leave HOST_URL empty and set AUTO_IP=true
AUTO_IP=true

# Web Server Port (used by Flask & AUTO_IP)
PORT=14000

# Docker
USE_DOCKER=false
```

### Configuration Options Explained

**Option 1: Custom Domain (Best for Production)**
```env
HOST_URL=https://yourdomain.com
PORT=5000
```
- Clean URLs: `https://yourdomain.com/file/user/index.html`
- Requires domain + DNS setup
- Works with HTTPS/SSL

**Option 2: VPS IP + Port (Manual)**
```env
HOST_URL=http://203.0.113.42:14000
AUTO_IP=false
```
- Direct IP access: `http://203.0.113.42:14000/file/user/index.html`
- Port must be open in firewall
- Works immediately with any VPS
- Not secure (HTTP)

**Option 3: Auto-Detect VPS IP (Easiest for Development)**
```env
# Leave HOST_URL empty
AUTO_IP=true
PORT=14000
```
- Bot auto-detects VPS public IP
- Uses PORT you specify
- URL becomes: `http://auto-detected-ip:14000/file/user/index.html`
- Perfect for quick testing on VPS
- ✅ **Recommended for VPS without domain**

### How Auto-Detection Works

When `AUTO_IP=true` and `HOST_URL` is empty:

1. Bot detects your VPS public IP automatically
2. Uses the PORT you specified (default: 14000)
3. Sends users: `http://YOUR_VPS_IP:PORT/file/user/site.html`
4. All features work immediately without manual setup

**Auto-detection methods (in order):**
1. Checks `https://api.ipify.org` (recommended - most reliable)
2. Fallback: Socket connection to 8.8.8.8 (if API fails)
3. Returns None if both fail (bot still works locally)

### Getting Credentials

**Bot Token:**
1. Chat [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot`
3. Follow instructions
4. Copy token to `TELEGRAM_BOT_TOKEN`

**Owner ID:**
1. Chat [@userinfobot](https://t.me/userinfobot) on Telegram
2. Copy your ID to `OWNER_ID`
3. Use same ID or different ID for `ADMIN_ID`

**PORT Setup:**
- Default: 5000
- Common VPS ports: 5000, 8000, 14000
- Must be allowed in firewall: `sudo ufw allow PORT/tcp`

---

## 🚀 Deployment

### Heroku

```bash
# Create app
heroku login
heroku create your-hostingbot-name

# Set environment variables
heroku config:set TELEGRAM_BOT_TOKEN=your_token
heroku config:set OWNER_ID=your_id

# Deploy
git push heroku main

# Start worker
heroku ps:scale worker=1

# View logs
heroku logs --tail
```

### Render.com

1. Go to [render.com](https://render.com)
2. Create new Web Service
3. Connect GitHub repository
4. Set Build Command: `pip install -r requirements.txt`
5. Set Start Command: `python src/main.py`
6. Add environment variables in dashboard
7. Deploy

### Railway

1. Go to [railway.app](https://railway.app)
2. Create project from GitHub
3. Add environment variables
4. Railway auto-deploys on git push

### AWS EC2

```bash
# Launch Ubuntu 22.04 instance (t3.small minimum)
# SSH into instance
ssh -i key.pem ubuntu@your-ip

# Install dependencies
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git

# Clone and setup (same as System Python above)
git clone https://github.com/yourusername/Hostingbot.git
cd Hostingbot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env

# Create systemd service (see above)
```

### DigitalOcean / Linode

Same as AWS EC2 - create droplet with Ubuntu 22.04 and follow system Python installation.

---

## 📱 Usage

### Button Commands

**Public Commands (All Users):**
| Button | Function |
|--------|----------|
| 📂 Files | View/manage your files |
| 👤 Profile | View profile |
| 📊 Stats | View statistics |
| ❓ Help | Help documentation |
| 🎧 Owner | Owner information |
| 📞 Contact | Support contact |
| 🔧 Module | Install packages |
| 🤖 Clone | Clone repositories |
| 🔧 Env Vars | Manage env variables |
| 🌐 GitHub | GitHub integration |

**Admin Commands (Hidden from users):**
| Button | Function |
|--------|----------|
| 🟢 Running | View running scripts |
| 💳 Subs | Manage subscriptions |
| ⏳ Pending | View pending approvals |
| 🤖 Clones | Manage clones |
| 👑 Admin | Admin panel |

**Owner Commands (Hidden from everyone except owner):**
| Button | Function |
|--------|----------|
| 🔒 Lock | Lock/unlock bot |
| 📁 All Files | View all users' files |
| 📜 Bot Logs | View bot logs |

### Slash Commands
- `/start` - Open main menu
- `/help` - Show help
- `/files` - List your files
- `/stats` - Show statistics

---

## 🌐 Web Hosting

### How Web Hosting Works

HostingBot includes Flask server to host static and dynamic websites. Here's how:

### Uploading a Website

1. **Create HTML File**
```html
<!-- index.html -->
<!DOCTYPE html>
<html>
<head>
    <title>My Site</title>
</head>
<body>
    <h1>Hello from HostingBot!</h1>
    <p>Hosted on Telegram 🚀</p>
</body>
</html>
```

2. **Send to Bot**
   - Open bot in Telegram
   - Click 📂 Files
   - Upload `index.html`

3. **Website is Live**
   - Bot hosts on: `http://YOUR_SERVER:14000/users/{user_id}/index.html`
   - Or custom domain if `HOST_URL` configured

### Directory Structure
```
uploads/
└── user_id/
    ├── index.html         (Main page)
    ├── style.css          (Styling)
    ├── script.js          (JavaScript)
    ├── images/            (Images folder)
    │   ├── logo.png
    │   └── banner.jpg
    └── data.json          (Data files)
```

### Web Hosting Features

**Static Sites:**
- HTML, CSS, JavaScript
- Images (PNG, JPG, GIF)
- JSON data files
- No server-side processing

**Dynamic Sites (with Python):**
- Python Flask scripts
- API endpoints
- Database connections
- Real-time updates

### Example: Python Web App

**1. Create Flask App**
```python
# app.py
from flask import Flask, jsonify
app = Flask(__name__)

@app.route('/')
def hello():
    return '''
    <h1>My Web App</h1>
    <p>Hosted via Telegram Bot</p>
    '''

@app.route('/api/data')
def api():
    return jsonify({'status': 'running', 'message': 'Hello from API'})

if __name__ == '__main__':
    app.run(debug=False, port=5000)
```

**2. Upload to Bot**
   - Send `app.py` file to bot
   - Bot auto-executes
   - App runs on port 5000

**3. Access Website**
   - Visit: `http://YOUR_SERVER:5000/`
   - Call API: `http://YOUR_SERVER:5000/api/data`

### Custom Domain Setup

**1. Configure HOST_URL**
```bash
# In .env
HOST_URL=https://mybot.example.com
```

**2. Point Domain to Server**
   - Update DNS A record
   - Point to your server IP

**3. Website Live**
   - Access: `https://mybot.example.com/users/{user_id}/index.html`

### Accessing Hosted Sites

**From Bot:**
- Files → Click file → Get URL

**Direct Access:**
```
http://SERVER_IP:14000/users/USER_ID/index.html
```

**Custom Domain:**
```
https://mybot.example.com/users/USER_ID/index.html
```

---

## 🔒 Security

### User Isolation
- Separate file directories per user
- Independent process namespaces
- Isolated environment variables
- No cross-user access

### Access Control
- **Public**: All users (with force-join)
- **Admin**: Admin and owner only
- **Owner**: Only owner ID

Implementation:
```python
if msg.from_user.id not in admins:
    return  # Silently deny
```

### Force-Join Channels
- Require users to join update channel
- Require users to join support channel
- Verify before bot access

### File Approval System
- Owner approves suspicious files
- Automatic detection of:
  - Executable files
  - Large files
  - Suspicious extensions
- Reject/approve functionality

### Ban System
- Ban specific users
- Prevent re-access
- Clear user data on ban

---

## 📊 Database

### Tables
- **users** - User data, tier, files
- **scripts** - Running processes
- **subscriptions** - Premium tiers
- **pending** - Files awaiting approval

### Data Persistence
- Database never cleared on restart
- Automatic backups
- Journaling for crash recovery
- SQLite with persistent file storage

---

## 🐛 Troubleshooting

### Bot Won't Start

**Check Python:**
```bash
python3 --version  # Should be 3.8+
```

**Check Token:**
```bash
echo $TELEGRAM_BOT_TOKEN
```

**Check Syntax:**
```bash
python -m py_compile src/main.py
```

**View Logs:**
```bash
tail -f logs/bot.log
```

### Module Installation Fails

**Error:** `externally-managed-environment`

**Fix:**
```bash
source .venv/bin/activate
pip install --break-system-packages modulename
```

### Docker Issues

**Image not found:**
```bash
docker build -t hostingbot .
```

**Permission denied:**
```bash
sudo usermod -aG docker $USER
newgrp docker
```

**View logs:**
```bash
docker logs -f hostingbot
```

### Database Locked

**Fix:**
```bash
pkill -f "python.*main.py"
python src/main.py
```

### Connection Problems

**Check internet:**
```bash
ping 8.8.8.8
```

**Check Telegram API:**
```bash
curl -I https://api.telegram.org/
```

**Restart bot:**
```bash
pkill -f "python.*main.py"
systemctl restart hostingbot
```

---

## 📈 Performance

### Resource Usage

**Base Bot:**
- Memory: ~200MB
- CPU: <5% idle
- Network: ~100KB/min

**Per User Script:**
- Memory: 50-500MB
- CPU: Depends on script
- Disk: Depends on file size

### Optimization Tips

1. **Limit uploads** - Set quotas per tier
2. **Monitor processes** - Regular cleanup
3. **Archive logs** - Monthly rotation
4. **Database maintenance** - Vacuum regularly

```bash
# Vacuum database
sqlite3 data/bot.db "VACUUM;"

# Cleanup old logs
find logs -name "*.log" -mtime +30 -delete
```

---

## 📝 Environment Variables

### Required
```
TELEGRAM_BOT_TOKEN  - Bot token from @BotFather
OWNER_ID            - Your Telegram user ID
ADMIN_ID            - Admin user ID (can be same as OWNER_ID)
OWNER_USERNAME      - Your Telegram username (@handle)
```

### Web Hosting (Choose one)
```
# Manual custom domain
HOST_URL            - Custom domain (https://yourdomain.com)

# Auto-detect VPS IP (recommended)
AUTO_IP             - Set to 'true' for automatic VPS IP detection
PORT                - Web server port (default 5000)

# Manual VPS IP
HOST_URL            - VPS IP + port (http://203.0.113.42:14000)
```

### Bot Settings
```
UPDATE_CHANNEL      - Updates announcement channel
SUPPORT_CHANNEL     - Support/help channel
```

### Docker
```
USE_DOCKER          - Enable Docker (true/false)
DOCKER_IMAGE        - Docker image name (default hostingbot)
```

### Quick Setup Examples

**Example 1: Custom Domain (Production)**
```env
TELEGRAM_BOT_TOKEN=123:abc
OWNER_ID=123456789
ADMIN_ID=123456789
OWNER_USERNAME=@myusername
HOST_URL=https://mybot.example.com
PORT=5000
UPDATE_CHANNEL=https://t.me/MyChannel
SUPPORT_CHANNEL=https://t.me/MySupport
```

**Example 2: VPS with Auto-Detection (Development)**
```env
TELEGRAM_BOT_TOKEN=123:abc
OWNER_ID=123456789
ADMIN_ID=123456789
OWNER_USERNAME=@myusername
AUTO_IP=true
PORT=14000
UPDATE_CHANNEL=https://t.me/MyChannel
SUPPORT_CHANNEL=https://t.me/MySupport
```

**Example 3: VPS with Manual IP**
```env
TELEGRAM_BOT_TOKEN=123:abc
OWNER_ID=123456789
ADMIN_ID=123456789
OWNER_USERNAME=@myusername
HOST_URL=http://203.0.113.42:14000
AUTO_IP=false
PORT=14000
UPDATE_CHANNEL=https://t.me/MyChannel
SUPPORT_CHANNEL=https://t.me/MySupport
```

---

## 📞 Support

**Documentation:**
- README.md - This file
- GitHub Issues - For bugs and features

**Telegram:**
- Developer: [@blcqt](https://t.me/blcqt)
- Updates: [@TechTipsCode](https://t.me/TechTipsCode)
- Support: [@EliteCodeLab](https://t.me/EliteCodeLab)

**GitHub:**
- Issues: Report bugs
- Discussions: Ask questions
- Pull Requests: Contribute

---

## 📄 License

MIT License - See LICENSE file

---

## 🙏 Credits

- Built with [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- Telegram Bot API
- Flask for web hosting
- Docker for containerization
- SQLite for persistence

---

**Status**: ✅ Production Ready | **Version**: 2.0 | **Updated**: June 26, 2026

