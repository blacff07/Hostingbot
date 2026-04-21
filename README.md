# 🚀 HostingBot — Your Private Cloud, Right in Telegram

[![Deploy on Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/blacff07/Hostingbot)
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https://github.com/blacff07/Hostingbot)
[![Deploy on Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/blacff07/Hostingbot)
[![Deploy to Koyeb](https://www.koyeb.com/static/images/deploy/button.svg)](https://app.koyeb.com/deploy?type=git&repository=github.com/blacff07/Hostingbot)

**HostingBot** is a next‑generation Telegram bot that gives every user a **private, isolated VPS‑like environment**—complete with `pyenv`, `nvm`, and customisable resource limits. Upload and host websites, run scripts in 30+ languages, clone GitHub repositories, and manage everything from a persistent shell.

---

## ✨ Key Features

### 🖥️ Private VPS for Every User
- **Isolated Home Directory** – Each user gets their own `home/` folder.
- **Python Version Management** – Pre‑installed `pyenv` lets users install and switch between any Python version.
- **Node.js Version Management** – Pre‑installed `nvm` for seamless Node.js version control.
- **Persistent Shell** – Open `/shell` and pick up exactly where you left off.
- **Zero Interference** – Changes made inside a user's environment never affect the host system or other users.

### ⚡ Smart Resource Limits (Tiered)
| Tier | RAM Limit | CPU Limit | File Limit | Max Processes |
|------|-----------|-----------|------------|---------------|
| 👤 Free | 1 GB | 1 hour | 100 MB | 50 |
| ⭐ Premium | 2 GB | 1 hour | 100 MB | 50 |
| 🛡️ Admin | 4 GB | 1 hour | 100 MB | 50 |
| 👑 Owner | Unlimited | Unlimited | Unlimited | Unlimited |

*Limits are enforced automatically by the kernel—no single script can crash the VPS.*

### 🌐 File Hosting & Websites
- **Instant Public URLs** – Upload any file and get a direct link.
- **Website Hosting** – Upload a ZIP containing `index.html` and get a live site with a custom slug.
- **Static Assets** – HTML, CSS, images, fonts, PDFs, and more.

### 🚀 Multi‑Language Script Execution
Supports **30+ languages** with automatic dependency installation:

| Language | File Extensions |
|----------|-----------------|
| Python | `.py`, `.pyw` |
| JavaScript / TypeScript | `.js`, `.mjs`, `.cjs`, `.ts`, `.tsx` |
| Java | `.java` |
| C / C++ | `.c`, `.cpp`, `.cc`, `.cxx` |
| Go | `.go` |
| Rust | `.rs` |
| PHP | `.php` |
| Ruby | `.rb` |
| Lua | `.lua` |
| Shell | `.sh`, `.bash`, `.zsh`, `.fish` |
| Perl | `.pl`, `.pm` |
| R | `.r`, `.R` |
| Swift | `.swift` |
| Kotlin | `.kt` |
| Scala | `.scala` |
| Elixir | `.ex`, `.exs` |
| Haskell | `.hs` |
| PowerShell | `.ps1` |
| Batch | `.bat`, `.cmd` |

### 🔗 GitHub Integration
- **Clone & Host** – Send any public GitHub URL or use `/git <url>`.
- **Automatic Detection** – If the repo contains `index.html`, it's deployed as a website; otherwise it's treated as an executable project.
- **Requirements.txt Support** – Python projects with `requirements.txt` are automatically installed inside the user's private environment.

### 📊 Real‑Time Monitoring & Logs
- **Live Logs** – View `stdout`/`stderr` with a single click.
- **Crash Notifications** – Receive tracebacks directly in your Telegram DM.
- **Process Control** – Start, stop, restart, and delete running scripts via inline buttons.

### 🛡️ Enterprise‑Grade Security
- **Malicious Code Detection** – Blocks dangerous system calls, file operations, and network exploits.
- **File Theft Prevention** – Scripts cannot access files outside their designated folder.
- **Environment Variable Isolation** – Users can set per‑script environment variables without exposing the host.
- **Admin Moderation** – Ban users, delete files, and manage subscriptions.

### 👥 Multi‑User & Admin Controls
- **User Tiers** – Free, Premium, Admin, Owner with graduated limits.
- **Subscription Management** – Add/remove premium days, check expiry.
- **Broadcast System** – Send announcements to all users.
- **Clone This Bot** – Users can spawn their own instance with `/clone`.

---

## 🚀 Quick Deploy

### One‑Click Deploy
Click any deployment button at the top of this README to deploy instantly on your favourite platform.

### Manual Deployment

```bash
# 1. Clone the repository
git clone https://github.com/blacff07/Hostingbot.git
cd Hostingbot

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Create and configure your .env file
cp .env.example .env
nano .env   # Add your bot token and IDs

# 4. Run the bot
python src/main.py
```

### 🐳 Docker Deployment

```bash
docker build -t hostingbot .
docker run -d --env-file .env -p 5000:5000 hostingbot
```

Or with Docker Compose:

```bash
docker-compose up -d
```

---

## 🔧 Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Your bot token from [@BotFather](https://t.me/BotFather) | `123456:ABCdef...` |
| `OWNER_ID` | Your Telegram numeric ID | `8537538760` |
| `ADMIN_ID` | Additional admin ID (optional) | `8537538760` |
| `BOT_USERNAME` | Public username of your bot | `@MyHostingBot` |
| `UPDATE_CHANNEL` | Your Telegram channel URL | `https://t.me/MyChannel` |
| `HOST_URL` | Public URL where the bot is hosted (required for file/website links) | `https://mybot.onrender.com` |

---

## 📱 Commands

### 👤 User Commands
| Command | Description |
|---------|-------------|
| `/start` | Main menu with keyboard |
| `/help` | Show interactive help (General / Advanced) |
| `/shell [cmd]` | Open persistent shell or run a single command |
| `/git <url>` | Clone and host a public GitHub repository |
| `/setenv` | Set environment variables for a script |
| `/listenv` | List environment variables |
| `/delenv` | Delete environment variables |
| `/clone` | Clone this bot to your own token |
| `/settoken <token>` | Set your bot token (after `/clone`) |
| `/rmclone` | Remove your cloned bot |

### 🛡️ Admin Commands
| Command | Description |
|---------|-------------|
| `/addadmin <id>` | Promote a user to admin |
| `/removeadmin <id>` | Demote an admin |
| `/addsub <id> <days>` | Grant premium days |
| `/removesub <id>` | Remove subscription |
| `/checksub <id>` | Check subscription status |
| `/ban <id>` | Ban a user |
| `/unban <id>` | Unban a user |
| `/delete <id> <file>` | Delete any user's file |
| `/get <id> <file>` | Retrieve any user's file |
| `/broadcast <msg>` | Send a message to all users |
| `/restart` | **(Owner only)** Wipe all data and restart |
| `/botlogs` | **(Owner only)** View bot's own logs |

---

## 📁 Supported File Types

### Executable
`.py`, `.pyw`, `.js`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.java`, `.c`, `.cpp`, `.cc`, `.cxx`, `.go`, `.rs`, `.php`, `.rb`, `.lua`, `.sh`, `.bash`, `.zsh`, `.fish`, `.pl`, `.pm`, `.r`, `.R`, `.swift`, `.kt`, `.scala`, `.ex`, `.exs`, `.hs`, `.ps1`, `.bat`, `.cmd`

### Hosted / Static
`.html`, `.htm`, `.css`, `.txt`, `.md`, `.json`, `.xml`, `.yaml`, `.yml`, `.csv`, `.sql`, `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.svg`, `.mp4`, `.webm`, `.mp3`, `.wav`, `.pdf`, `.zip`, `.ttf`, `.woff`, `.woff2`

---

## 🛡️ Security Features

- **Malicious Code Detection** – Scans uploaded scripts for dangerous patterns (`rm -rf`, `subprocess`, `socket`, `eval`, etc.).
- **Pending Approval System** – Suspicious files are quarantined and require owner approval.
- **Isolated Execution** – Scripts run with restricted resource limits and cannot access the host filesystem.
- **Environment Variable Sanitisation** – Host secrets are never leaked to user scripts.

---

## 👥 User Tiers

| Tier | File Limit | RAM Limit | CPU Limit |
|------|------------|-----------|-----------|
| 👤 Free | 5 files | 1 GB | 1 hour |
| ⭐ Premium | 25 files | 2 GB | 1 hour |
| 🛡️ Admin | 999 files | 4 GB | 1 hour |
| 👑 Owner | Unlimited | Unlimited | Unlimited |

---

## 🏗️ Hosting Platforms

Optimised for and tested on:

- **Render** (recommended)
- **Railway**
- **Heroku**
- **Koyeb**
- **Fly.io**
- **Replit**
- **DigitalOcean** / **VPS**
- **AWS** / **GCP** / **Azure**

---

## 📝 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 👤 Author

**Blac** — [@NottBlac](https://t.me/NottBlac)  
📢 Channel: [@BlacScriptz](https://t.me/BlacScriptz)  
📂 Repository: [github.com/blacff07/Hostingbot](https://github.com/blacff07/Hostingbot)

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome!  
Feel free to open a pull request or start a discussion.

---

## ⭐ Support

If this project helps you, please give it a ⭐ on GitHub—it means a lot!

---

## ⚠️ Important Security Notes

1. **Never commit your `.env` file.**
2. **Rotate your bot token immediately if exposed.**
3. **Always use environment variables for sensitive data.**
4. **Keep `OWNER_ID` and `ADMIN_ID` private.**