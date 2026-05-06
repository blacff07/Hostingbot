# 🤖 HostingBot

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Required-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://core.telegram.org/bots)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
[![Flask](https://img.shields.io/badge/Flask-3.0-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)

*Professional Multi‑User Hosting Platform with Per‑User Docker Isolation*

**[Updates Channel](https://t.me/BlacScriptz) · [Support](https://t.me/NottBlac) · [Report a Bug](https://github.com/blacff07/Hostingbot/issues)**

</div>

---

## 📖 Table of Contents

- [Overview](#-overview)
- [Architecture](#-architecture)
- [Features](#-features)
- [How It Works](#-how-it-works)
- [Tier System](#-tier-system)
- [Security](#-security)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Deployment](#-deployment)
- [Commands](#-commands)
- [Supported Languages](#-supported-languages)
- [Supported File Types](#-supported-file-types)
- [Project Structure](#-project-structure)
- [Tech Stack](#-tech-stack)
- [Contributing](#-contributing)
- [Support](#-support)
- [License](#-license)

---

## 🌐 Overview

**HostingBot** is a high‑performance Telegram bot that transforms your VPS into a **multi‑tenant cloud hosting platform**. Each user receives a fully isolated environment powered by **Docker containers** — complete with a real interactive shell, support for 30+ programming languages, automatic dependency management, and secure file hosting.

Think of it as **Heroku meets GitHub Codespaces, delivered through Telegram**.

> Built and maintained by **Blac** — [@NottBlac](https://t.me/NottBlac) · [@BlacScriptz](https://t.me/BlacScriptz)

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────┐
│                 Telegram API                │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│              HostingBot Core                │
│  ┌─────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ Message │ │  Flask   │ │    Shell     │ │
│  │ Handler │ │  Server  │ │ Orchestrator │ │
│  └─────────┘ └──────────┘ └──────┬───────┘ │
└──────────────────────────────────┼──────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
              ┌─────────┐  ┌─────────┐  ┌─────────┐
              │ User A  │  │ User B  │  │ User C  │
              │Container│  │Container│  │Container│
              └─────────┘  └─────────┘  └─────────┘
```

> The bot is a **controller** — it never executes user code directly.
> All user operations happen inside **dedicated Docker containers** with strict security profiles.

---

## ✨ Features

### 🔐 Security & Isolation
- Per‑user Docker containers with `--cap-drop=ALL`, `--read-only`, and `no-new-privileges`
- Non‑root sandbox user inside every container
- Dangerous commands blocked at the PTY level (`sudo`, `passwd`, `rm -rf /`, etc.)
- Path‑traversal‑safe ZIP extraction
- Blacklist + container‑level security = defense in depth

### 💻 Real VPS Shell
- True PTY (pseudo‑terminal) with **live streaming output**
- Arrow key history navigation (non‑destructive)
- `Ctrl+C` / `Ctrl+D` / `Esc` support via inline buttons
- Interactive programs work (`nano`, `vim`, `python`, `htop`, `read`)
- Output formatted in code blocks for readability

### 📁 File Hosting & Execution
- Upload any file — static files served instantly via Flask
- **30+ languages** auto‑detected with automatic dependency installation
- Scripts execute **inside the user's container** — all installed packages persist
- Background scripts with crash monitoring and live log access

### 🌍 Website Hosting
- Upload ZIP files — auto‑extracted and served immediately
- Custom slug support (`your-domain.com/s/my-site`)
- Single‑page app friendly

### 🔗 GitHub Integration
- Clone any public GitHub repository with `/git <url>`
- Auto‑detects `index.html` → deploys as website
- Auto‑runs `pip install -r requirements.txt` for Python projects

### 🎛️ Environment Variables
- Per‑user, per‑script environment variables
- Securely stored in SQLite with masked display
- Set, list, and delete via dedicated menu buttons

### 👥 User Management
- **Tier‑based resource limits** — Free / Premium / Admin / Owner
- Force‑join verification for updates & support channels
- Ban / unban system with admin panel
- Subscription management (add/remove premium days)

### 📊 Live Stats & Monitoring
- Total users, files, and running scripts at a glance
- System CPU & RAM usage
- Bot uptime and ping latency
- Crash notifications and mid‑run traceback alerts delivered to owner

### 🛡️ Admin Panel
- View all running scripts across all users
- Broadcast messages to all users
- Pending file approval queue
- Bot lock toggle (disables uploads globally)
- Clone monitoring & management

---

## ⚙️ How It Works

### User Journey

```
1. /start        →  Force‑join check  →  Main menu
2. 💻 Shell      →  Docker container created  →  Interactive PTY shell
3. pip install   →  Package saved inside container
4. Upload script →  Executes inside container with all packages available
5. Inline buttons →  Start / Stop / Restart / Logs
6. exit          →  Container destroyed  →  Resources freed
```

### Container Lifecycle

- **Created** when a user opens the shell
- **Shared** between shell sessions and script executions
- **Destroyed** when the user exits or after inactivity timeout
- Each container uses bridge networking (outbound internet for package installs)
- Resource limits enforced by Docker cgroups

---

## 🏅 Tier System

| Feature | 👤 Free | ⭐ Premium | 🛡️ Admin | 👑 Owner |
|---------|---------|-----------|----------|---------|
| File Limit | 5 | 25 | 999 | ∞ |
| RAM Limit | 1 GB | 2 GB | 4 GB | Unlimited |
| CPU Cores | 1 | 1 | 1 | Unlimited |
| Max Processes | 128 | 256 | 512 | Unlimited |
| Open Files | 4096 | 8192 | 16384 | Unlimited |
| Container Timeout | 30 min | 60 min | 120 min | None |

---

## 🔒 Security

| Layer | Implementation |
|-------|---------------|
| **Container Capabilities** | `--cap-drop=ALL` — no kernel capabilities |
| **Privilege Escalation** | `--security-opt=no-new-privileges` |
| **Filesystem** | `--read-only` rootfs + writable `/home` and `/tmp` |
| **Network** | Bridge mode — outbound only, no inter‑container access |
| **User** | `--user sandbox:sandbox` — non‑root inside container |
| **Command Blocking** | `sudo`, `passwd`, `dd`, `mkfs`, etc. filtered at PTY level |
| **ZIP Extraction** | Path‑traversal & symlink attack detection |
| **File Serving** | Real‑path verification prevents directory traversal |
| **Input Validation** | SQLite parameterised queries; Markdown‑safe output |
| **Malicious Code Detection** | Dangerous patterns scanned on upload (`subprocess`, `eval`, `socket`, etc.) |
| **Pending Approval Queue** | Suspicious files quarantined for owner review |

---

## 📋 Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.10 or higher |
| Docker | 24.x or higher |
| pip | Latest |

- A Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- Docker installed and running on the host
- Bot added as **member** to your force‑join channels

---

## 🔧 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/blacff07/Hostingbot.git
cd Hostingbot
```

### 2. Build the Sandbox Image

```bash
docker build -t hostingbot-sandbox .
```

### 3. Install Python Dependencies

```bash
pip3 install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
nano .env
```

### 5. Run the Bot

```bash
python3 src/main.py
```

---

## ⚙️ Configuration

All settings are controlled via environment variables or a `.env` file.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | — | Bot token from @BotFather |
| `OWNER_ID` | ❌ | `8760823326` | Owner's Telegram user ID |
| `ADMIN_ID` | ❌ | `8760823326` | Admin's Telegram user ID |
| `OWNER_NAME` | ❌ | `Blac` | Display name in web panel |
| `UPDATE_CHANNEL` | ❌ | `https://t.me/BlacScriptz` | Force‑join updates channel |
| `SUPPORT_CHANNEL` | ❌ | `https://t.me/NottBlac` | Force‑join support channel |
| `OWNER_USERNAME` | ❌ | `https://t.me/NottBlac` | Owner profile link |
| `USE_DOCKER` | ❌ | `true` | Enable Docker isolation |
| `DOCKER_IMAGE` | ❌ | `hostingbot-sandbox` | Docker image name |
| `HOST_URL` | ❌ | auto‑detected | Public URL for file serving |
| `PORT` | ❌ | `5000` | Flask web server port |

---

## 🚀 Deployment

### Option 1: VPS (Recommended — Ubuntu 22.04)

```bash
# Install Docker
curl -fsSL https://get.docker.com | bash
sudo usermod -aG docker $USER && newgrp docker

# Clone & setup
git clone https://github.com/blacff07/Hostingbot.git
cd Hostingbot
docker build -t hostingbot-sandbox .
pip3 install -r requirements.txt
cp .env.example .env && nano .env
```

Create a systemd service for auto‑restart:

```ini
[Unit]
Description=HostingBot
After=network.target docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/Hostingbot
EnvironmentFile=/root/Hostingbot/.env
ExecStart=/usr/bin/python3 /root/Hostingbot/src/main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now hostingbot
```

### Option 2: One‑Click Cloud Deploy

| Platform | Deploy |
|----------|--------|
| **Render** | [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/blacff07/Hostingbot) |
| **Railway** | [![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https://github.com/blacff07/Hostingbot) |
| **Heroku** | [![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/blacff07/Hostingbot) |
| **Koyeb** | [![Deploy to Koyeb](https://www.koyeb.com/static/images/deploy/button.svg)](https://app.koyeb.com/deploy?type=git&repository=github.com/blacff07/Hostingbot) |
| **Fly.io** | Deploy with `flyctl launch` |

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
| `/listenv` | List all set environment variables |
| `/delenv` | Delete environment variables |
| `/clone` | Clone this bot to your own token |
| `/settoken <token>` | Set your bot token (after `/clone`) |
| `/rmclone` | Remove your cloned bot instance |

### 🛡️ Admin Commands

| Command | Description |
|---------|-------------|
| `/addadmin <id>` | Promote a user to admin |
| `/removeadmin <id>` | Demote an admin |
| `/addsub <id> <days>` | Grant premium subscription days |
| `/removesub <id>` | Remove a subscription |
| `/checksub <id>` | Check a user's subscription status |
| `/ban <id>` | Ban a user |
| `/unban <id>` | Unban a user |
| `/delete <id> <file>` | Delete any user's file |
| `/get <id> <file>` | Retrieve any user's file |
| `/broadcast <msg>` | Send a message to all users |
| `/restart` | **(Owner only)** Wipe all data and restart |
| `/botlogs` | **(Owner only)** View bot's own logs |

---

## 🚀 Supported Languages

| Language | Extensions |
|----------|------------|
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

---

## 📁 Supported File Types

### Executable
`.py` `.pyw` `.js` `.mjs` `.cjs` `.ts` `.tsx` `.java` `.c` `.cpp` `.cc` `.cxx` `.go` `.rs` `.php` `.rb` `.lua` `.sh` `.bash` `.zsh` `.fish` `.pl` `.pm` `.r` `.R` `.swift` `.kt` `.scala` `.ex` `.exs` `.hs` `.ps1` `.bat` `.cmd`

### Hosted / Static
`.html` `.htm` `.css` `.txt` `.md` `.json` `.xml` `.yaml` `.yml` `.csv` `.sql` `.jpg` `.jpeg` `.png` `.gif` `.webp` `.svg` `.mp4` `.webm` `.mp3` `.wav` `.pdf` `.zip` `.ttf` `.woff` `.woff2`

---

## 📂 Project Structure

```
Hostingbot/
├── src/
│   └── main.py              # Bot entry point & all logic
├── Dockerfile               # Sandbox container image
├── docker-compose.yml       # Docker Compose config
├── requirements.txt         # Python dependencies
├── .env.example             # Environment template
├── .gitignore
├── render.yaml              # Render deployment config
├── railway.toml             # Railway deployment config
├── heroku.yml               # Heroku deployment config
├── LICENSE                  # MIT License
├── README.md                # This file
├── CONTRIBUTING.md          # Contribution guide
└── CHANGELOG.md             # Version history
```

---

## 🛠 Tech Stack

| Category | Technology |
|----------|-----------|
| **Core Language** | Python 3.10+ |
| **Bot Framework** | [pyTelegramBotAPI](https://github.com/eternnoir/pyTelegramBotAPI) |
| **Web Server** | [Flask](https://flask.palletsprojects.com/) |
| **Containerization** | [Docker](https://docker.com) |
| **Database** | SQLite3 (WAL mode) |
| **Process Management** | [psutil](https://github.com/giampaolo/psutil) |
| **Terminal Emulation** | Linux PTY (pseudo‑terminal) |
| **Resource Control** | cgroups (via Docker) |
| **Security** | Linux capabilities, namespaces, seccomp |

---

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a pull request.

```bash
# Fork & clone
git clone https://github.com/blacff07/Hostingbot.git
cd Hostingbot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Build sandbox image
docker build -t hostingbot-sandbox .

# Run locally
python3 src/main.py
```

---

## 💬 Support

<div align="center">

| Channel | Link |
|---------|------|
| **Updates** | [@BlacScriptz](https://t.me/BlacScriptz) |
| **Owner / Support** | [@NottBlac](https://t.me/NottBlac) |
| **Bug Reports** | [Open an Issue](https://github.com/blacff07/Hostingbot/issues) |

</div>

---

## ⚠️ Important Security Notes

1. **Never commit your `.env` file.**
2. **Rotate your bot token immediately if exposed.**
3. **Always use environment variables for sensitive data.**
4. **Keep `OWNER_ID` and `ADMIN_ID` private.**

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2025 Blac (@NottBlac)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.
```

---

<div align="center">

### ⭐ Star this repository if you find it useful!

Made with ❤️ by **Blac**

[![Telegram](https://img.shields.io/badge/Telegram-@NottBlac-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/NottBlac)
[![Channel](https://img.shields.io/badge/Channel-@BlacScriptz-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/BlacScriptz)
[![GitHub](https://img.shields.io/badge/GitHub-HostingBot-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/blacff07/Hostingbot)

</div>