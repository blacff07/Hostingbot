# Universal File Host Bot 🤖

[![Deploy on Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/YOUR_USERNAME/universal-file-host-bot)
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https://github.com/YOUR_USERNAME/universal-file-host-bot)
[![Deploy on Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/YOUR_USERNAME/universal-file-host-bot)
[![Deploy to Koyeb](https://www.koyeb.com/static/images/deploy/button.svg)](https://app.koyeb.com/deploy?type=git&repository=github.com/YOUR_USERNAME/universal-file-host-bot)

A powerful Telegram bot for hosting files and executing code in 30+ programming languages with advanced security features.

## ✨ Features

- 📁 **Universal File Hosting** - Support for 30+ file types
- 🚀 **Multi-language Execution** - Python, JavaScript, Java, C/C++, Go, Rust, PHP, Shell, Ruby, and more
- 🛡️ **Advanced Security** - Malicious code detection, file theft prevention
- 🌐 **Real-time Monitoring** - Track running scripts, view logs
- 📊 **Process Management** - Start, stop, restart, and monitor scripts
- ⚡ **Auto Dependency Installation** - Automatically installs required packages
- 👑 **Multi-user Support** - Free users, subscribers, admins, and owner privileges
- 🔄 **Bot Cloning** - Users can create their own bot instances

## 🚀 Quick Deploy

### One-Click Deploy

Click any of the buttons above to deploy instantly!

### Manual Deployment

**Clone the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/universal-file-host-bot.git
   cd universal-file-host-bot
   ```

1. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```
2. Configure environment variables
   ```bash
   cp .env.example .env
   # Edit .env with your bot token and IDs
   ```
3. Run the bot
   ```bash
   python src/main.py
   ```

Docker Deployment

```bash
docker build -t universal-file-host-bot .
docker run -d --env-file .env -p 5000:5000 universal-file-host-bot
```

Docker Compose

```bash
docker-compose up -d
```

🔧 Configuration

Create a .env file with the following variables:

```env
# Bot Configuration (REQUIRED)
TELEGRAM_BOT_TOKEN=your_bot_token_from_@BotFather
OWNER_ID=your_telegram_user_id
ADMIN_ID=admin_telegram_user_id
BOT_USERNAME=@your_bot_username

# Optional Configuration
UPDATE_CHANNEL=https://t.me/your_channel
```

📦 Supported File Types

Executable Languages

· 🐍 Python (.py)
· 🟨 JavaScript (.js)
· ☕ Java (.java)
· 🔧 C++ (.cpp), C (.c)
· 🐹 Go (.go)
· 🦀 Rust (.rs)
· 🐘 PHP (.php)
· 💎 Ruby (.rb)
· 🌙 Lua (.lua)
· 🔷 TypeScript (.ts)
· 🖥️ Shell (.sh)
· and more...

Hosted Files

· 🌐 HTML, CSS
· 📄 Text, Markdown, JSON, XML, YAML
· 🖼️ Images (JPEG, PNG, GIF, SVG)
· 📦 Archives (ZIP)
· 📑 PDF Documents

🛡️ Security Features

· Malicious Code Detection - Blocks system commands and dangerous operations
· File Theft Prevention - Prevents bots from stealing files
· Rate Limiting - Prevents abuse
· User Limits - Configurable upload limits per user tier
· Admin Controls - Lock bot, manage users, broadcast messages

👥 User Tiers

Tier Upload Limit Features
Free 5 files Basic hosting & execution
Subscribed 25 files Priority processing
Admin Unlimited All features + management
Owner Unlimited Complete access + bypass

📱 Commands

· /start - Start the bot
· /clone - Create your own bot instance
· /settoken YOUR_TOKEN - Set token for cloned bot
· /rmclone - Remove your cloned bot
· Admin: /addsub, /removesub, /broadcast, /addadmin, /removeadmin

🏗️ Hosting Platforms

This bot is optimized for deployment on:

· Heroku (with Procfile)
· Railway (with railway.json)
· Render (with render.yaml)
· Fly.io (with fly.toml)
· Koyeb (with Docker)
· Replit (with replit.nix)
· DigitalOcean (with Docker)
· AWS/GCP/Azure (any Python hosting)

📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

👤 Author

@UnknownGuy6666

· Telegram: @UnknownGuy6666
· Channel: @CyberTricks_X

🤝 Contributing

Contributions, issues, and feature requests are welcome!

⭐ Support

If you like this project, please give it a star on GitHub!

```

## Step 3: Create GitHub Repository

### Using GitHub CLI (recommended):
```bash
# Install GitHub CLI first, then:
gh auth login
gh repo create universal-file-host-bot --public --source=. --remote=origin --push
```

Using Git commands:

```bash
# Initialize git repository
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit: Universal File Host Bot"

# Create repository on GitHub manually, then:
git remote add origin https://github.com/YOUR_USERNAME/universal-file-host-bot.git
git branch -M main
git push -u origin main
```

Step 4: Platform-Specific Deployment

Heroku Deployment

```bash
heroku create your-bot-name
heroku config:set TELEGRAM_BOT_TOKEN=your_token
heroku config:set OWNER_ID=your_id
heroku config:set ADMIN_ID=admin_id
heroku config:set BOT_USERNAME=@your_bot
git push heroku main
```

Railway Deployment

1. Go to railway.app
2. Click "New Project" → "Deploy from GitHub"
3. Select your repository
4. Add environment variables in the dashboard

Render Deployment

1. Go to render.com
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Configure environment variables

Replit Deployment

Create a .replit file:

```replit
run = "python src/main.py"

[nix]
channel = "stable-22_11"

[env]
TELEGRAM_BOT_TOKEN = "your_token"
OWNER_ID = "your_id"
ADMIN_ID = "admin_id"
BOT_USERNAME = "@your_bot"
```

Step 5: Add Deployment Badges to README

```markdown
[![Deploy on Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/YOUR_USERNAME/universal-file-host-bot)
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https://github.com/YOUR_USERNAME/universal-file-host-bot)
[![Deploy on Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/YOUR_USERNAME/universal-file-host-bot)
[![Deploy to Koyeb](https://www.koyeb.com/static/images/deploy/button.svg)](https://app.koyeb.com/deploy?type=git&repository=github.com/YOUR_USERNAME/universal-file-host-bot)
```

Important Security Notes ⚠️

1. Never commit your actual .env file (it's in .gitignore)
2. Rotate your tokens if accidentally exposed
3. Use environment variables on all hosting platforms
4. Keep your OWNER_ID and ADMIN_ID private

## 👤 Author

**@NotBlac**
- Telegram: [@NotBlac](https://t.me/NotBlac)
- Channel: [@BlacScriptz](https://t.me/BlacScriptz)