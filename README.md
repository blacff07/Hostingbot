# Universal File Host Bot 🤖

[![Deploy on Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/blacff07/Hostingbot)
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https://github.com/blacff07/Hostingbot)
[![Deploy on Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/blacff07/Hostingbot)
[![Deploy to Koyeb](https://www.koyeb.com/static/images/deploy/button.svg)](https://app.koyeb.com/deploy?type=git&repository=github.com/blacff07/Hostingbot)

A powerful Telegram bot for hosting files and executing code in **30+ programming languages** with advanced security features.

---

## ✨ Features

- 📁 **Universal File Hosting** — Support for 30+ file types
- 🚀 **Multi-language Execution** — Python, JavaScript, Java, C/C++, Go, Rust, PHP, Shell, Ruby and more
- 🛡️ **Advanced Security** — Malicious code detection & file theft prevention
- 🌐 **Real-time Monitoring** — Track running scripts and logs
- 📊 **Process Management** — Start, stop, restart and monitor scripts
- ⚡ **Auto Dependency Installation**
- 👑 **Multi-user Support**
- 🔄 **Bot Cloning System**

---

## 🚀 Quick Deploy

### One-Click Deploy

Click any deployment button above to deploy instantly.

---

## 🛠 Manual Deployment

### Clone Repository

```bash
git clone https://github.com/blacff07/Hostingbot.git
cd Hostingbot
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Configure Environment Variables

```bash
cp .env.example .env
# Edit .env with your bot token and IDs
```

### Run the Bot

```bash
python src/main.py
```

---

## 🐳 Docker Deployment

```bash
docker build -t universal-file-host-bot .
docker run -d --env-file .env -p 5000:5000 universal-file-host-bot
```

### Docker Compose

```bash
docker-compose up -d
```

---

## 🔧 Configuration

Create a `.env` file:

```env
# Bot Configuration
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Owner Configuration
OWNER_ID=your_telegram_id
ADMIN_ID=your_telegram_id

# Bot Identity
BOT_USERNAME=@NottBlac
UPDATE_CHANNEL=https://t.me/BlacScriptz

# Hosting URL (set to your deployed app URL)
HOST_URL=https://your-app.up.railway.app
```

---

## 📦 Supported File Types

### Executable Languages

- 🐍 Python (.py)
- 🟨 JavaScript (.js)
- ☕ Java (.java)
- 🔧 C++ (.cpp), C (.c)
- 🐹 Go (.go)
- 🦀 Rust (.rs)
- 🐘 PHP (.php)
- 💎 Ruby (.rb)
- 🌙 Lua (.lua)
- 🔷 TypeScript (.ts)
- 🖥️ Shell (.sh)
- and more...

### Hosted Files

- 🌐 HTML, CSS
- 📄 Text, Markdown, JSON, XML, YAML
- 🖼️ Images (JPEG, PNG, GIF, SVG)
- 📦 Archives (ZIP)
- 📑 PDF Documents

---

## 🛡️ Security Features

- Malicious Code Detection
- File Theft Prevention
- Rate Limiting
- User Upload Limits
- Admin Controls

---

## 👥 User Tiers

| Tier | Upload Limit | Features |
|------|-------------|----------|
| Free | 5 Files | Basic hosting & execution |
| Subscribed | 25 Files | Priority processing |
| Admin | Unlimited | Management access |
| Owner | Unlimited | Complete access |

---

## 📱 Commands

- `/start` — Start the bot
- `/clone` — Create your own bot instance
- `/settoken YOUR_TOKEN`
- `/rmclone`

Admin:

- `/addsub`
- `/removesub`
- `/broadcast`
- `/addadmin`
- `/removeadmin`

---

## 🏗️ Hosting Platforms

Optimized for:

- Heroku
- Railway
- Render
- Fly.io
- Koyeb
- Replit
- DigitalOcean
- AWS / GCP / Azure

---

## 📝 License

MIT License — see LICENSE file.

---

## 👤 Author

**Blac** — [@NottBlac](https://t.me/NottBlac)  
Channel: https://t.me/BlacScriptz  
Repo: https://github.com/blacff07/Hostingbot

---

## 🤝 Contributing

Contributions and feature requests are welcome!

---

## ⭐ Support

If you like this project, please give it a ⭐ on GitHub!

---

## ⚠️ Important Security Notes

1. Never commit your `.env`
2. Rotate exposed tokens immediately
3. Use environment variables
4. Keep OWNER and ADMIN IDs private