# Freebies Bot

A simple Discord bot for your private server that shares free games and free books/comics.

## Features

- `/freegames` → Shows current free games from Epic Games Store + any custom games you add
- `/freebooks` → Shows free books, comics and PDFs you added
- `/read` → Interactive page-by-page reader with Next / Previous buttons
- `/help` → Shows all commands
- `/addgame` and `/addbook` → Admin-only commands so you can easily add custom free finds

## Setup Instructions

### 1. Create the bot on Discord

1. Go to https://discord.com/developers/applications
2. Click **New Application**
3. Go to the **Bot** tab → Reset Token → copy the token
4. Enable the intents you want (Message Content is optional)
5. Go to **OAuth2 → URL Generator**
   - Scopes: `bot` + `applications.commands`
   - Permissions: Send Messages, Embed Links, Attach Files, Use Slash Commands
6. Invite the bot to your private server using the generated link

### 2. Install Python packages

```bash
pip install -r requirements.txt
```

### 3. Configure the bot

1. Rename `.env.example` to `.env`
2. Open `.env` and paste:
   - Your bot token
   - Your Discord User ID (enable Developer Mode in Discord → right click your name → Copy User ID)

### 4. Run the bot

```bash
python bot.py
```

You should see:
```
Logged in as YourBot#1234
Synced 6 slash command(s)
```

### 5. Test the commands

In your Discord server type:
- `/help`
- `/freegames`
- `/freebooks`

## Adding Custom Content

Only the owner (the ID in `.env`) can use these:

**Add a free game:**
```
/addgame title:Game Name link:https://... platform:Steam description:Optional text
```

**Add a free book/comic:**
```
/addbook title:Book Name link:https://... type:Comic pages:https://img1.jpg,https://img2.jpg,https://img3.jpg
```

The `pages` parameter is optional. If you provide image URLs of the pages (comma separated), users can use `/read` to flip through them with buttons.

## Notes

- Only use **legal** free content (official free promotions, public domain, or content the authors allow free sharing).
- The Epic free games list is fetched automatically.
- Data is stored in `data.json` — you can also edit this file manually.
- The bot must stay running to respond to commands.

## Optional: Keep the bot online 24/7

You can later host it for free/cheap on services like Railway, a VPS, or a Raspberry Pi. Ask me when you're ready for that guide.
