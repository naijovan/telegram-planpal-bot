# Telegram PlanPal Bot

Telegram PlanPal Bot is a self-hosted Telegram itinerary assistant for managing Google Calendar events and daily important tasks.

It is not a public hosted bot. To use it, you create your own Telegram bot, connect your own Google Calendar, and run your own copy of this project locally or on a hosting provider.

Important: the bot only works while the Python process is running. If you stop the terminal, shut down your computer, or the hosting process stops, the bot will stop responding.

## Key Features

- Telegram-first calendar assistant
- Button-based event creation
- Google Calendar sync
- `/view` for today, tomorrow, or a custom date
- `/add` for guided event creation
- `/amend` for editing or deleting events
- Overlap warnings before saving conflicting events
- Simple recurring events
- Important Tasks for daily priorities
- Pinned Telegram task summary
- Pending and Done task tracking
- Dynamic Telegram keyboards
- SQLite local storage for drafts, task status, and local bot data

## Why This Project Is Different

Telegram PlanPal Bot is not mainly an AI or LLM natural-language calendar bot.

Instead, it is designed for low-typing, button-based daily use. This is useful when typing long messages or speaking voice commands is inconvenient. The main goal is a minimal, practical, everyday planning flow that works directly inside Telegram.

## Tech Stack

- Python
- `python-telegram-bot`
- Google Calendar API
- SQLite
- `python-dotenv`

## Project Structure

```text
bot.py               Main Telegram bot handlers, menus, and flows
calendar_service.py  Google Calendar OAuth, event reading, creation, editing, and deletion
database.py          SQLite setup and helper functions for drafts, tasks, and local references
requirements.txt     Python package dependencies
test_bot.py          Local test suite
.env.example         Example environment variable file
.gitignore           Files that should not be committed
```

## Security Warning

Never commit private credentials, tokens, local databases, or logs.

Keep these files out of GitHub:

```text
.env
credentials.json
token.json
bot_data.db
*.db
bot.log
venv/
__pycache__/
```

## Prerequisites

You need:

- Python 3.10 or newer
- A Telegram account
- A Google account
- Git
- A Google Cloud project

## Local Setup

Clone the repo and install the dependencies:

```bash
git clone <repo-url>
cd telegram-planpal-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Then edit `.env` and add your Telegram bot token.

## Telegram BotFather Setup

1. Open Telegram.
2. Search for `@BotFather`.
3. Send `/newbot`.
4. Follow the prompts to choose a bot name and username.
5. Copy the bot token from BotFather.
6. Paste it into `.env` like this:

```text
TELEGRAM_BOT_TOKEN=your_botfather_token_here
```

Do not share this token publicly.

## Google Calendar Setup

1. Go to the Google Cloud Console:
   <https://console.cloud.google.com/>
2. Create a new project, or select an existing project.
3. Enable the Google Calendar API:
   - Open `APIs & Services`
   - Open `Library`
   - Search for `Google Calendar API`
   - Click `Enable`
4. Configure the OAuth consent screen:
   - Choose `External` unless you are using a Google Workspace organization
   - Fill in the required app information
   - Add yourself as a test user
5. Create OAuth credentials:
   - Open `APIs & Services` -> `Credentials`
   - Click `Create credentials` -> `OAuth client ID`
   - Choose `Desktop app`
6. Download the JSON file.
7. Rename it to:

```text
credentials.json
```

8. Place `credentials.json` in the project folder.
9. Run the one-time Google login flow:

```bash
python3 calendar_service.py auth
```

A browser window should open. After you approve access, `token.json` will be created locally.

Keep both `credentials.json` and `token.json` private.

## Running The Bot Locally

Start the bot with:

```bash
python3 bot.py
```

Then open Telegram and send `/start` to your bot.

The bot will only respond while this command is running. If the terminal is closed, your laptop shuts down, or your computer sleeps, the bot stops. This is fine for testing, but not ideal for everyday use.

## Bot Command Guide

- `/start` - Start the bot and show the main menu
- `/help` - Show help and command information
- `/connect_calendar` - Check Google Calendar setup status
- `/view` - Open the view menu for today, tomorrow, or another date
- `/today` - Show today's Google Calendar events
- `/tomorrow` - Show tomorrow's Google Calendar events
- `/add` - Start guided event creation
- `/amend` - Edit or delete Google Calendar events
- `/tasks` - Open Important Tasks
- `/add_task` - Add an important task
- `/done_task` - Mark a task as done
- `/edit_task` - Rename an important task
- `/delete_task` - Delete an important task
- `/refresh_tasks` - Refresh the Important Tasks summary and try to pin it when appropriate
- `/back` - Return to the main menu

## Typical Usage Flow

View today's schedule:

```text
/view
/today
```

Add an event:

```text
/add
```

Then follow the buttons to choose the date, time, title, optional location, optional notes, recurrence, and confirmation.

Edit or delete an event:

```text
/amend
```

Then choose the date, select the event, and choose whether to edit or delete it.

Add an important task:

```text
/tasks
/add_task
```

Then type the task text when the bot asks.

Mark a task done:

```text
/tasks
/done_task
```

Then select the task from the buttons.

## Testing

Run syntax checks:

```bash
python3 -m py_compile bot.py database.py calendar_service.py test_bot.py
```

Run the test suite:

```bash
python3 test_bot.py
```

## Important Hosting Note For Everyday Use

This bot is not hosted by default.

For testing, running the bot locally is enough. For daily use, you should host your own copy on a service that supports long-running Python processes. A beginner-friendly option to consider is fps.ms Telegram Bot Hosting because it is designed specifically for Telegram bots. However, check the latest pricing and plan limits before choosing a provider. Other options include Railway, Render Background Worker, Fly.io, Oracle Cloud Free Tier, or running it on a Raspberry Pi/home server.

The hosting provider must support long-running Python processes or background workers. If the host stops the process, the bot will stop responding.

On any hosting provider, keep these files private:

```text
.env
credentials.json
token.json
bot_data.db
```

Hosting plans and free tiers can change, so check current pricing yourself before choosing where to deploy.

## Current Limitations

- This is not hosted as a public bot.
- Each user must create their own Telegram bot and Google credentials.
- SQLite is best for personal or local use.
- Multi-user public deployment would need per-user OAuth and a hosted database.
- Scheduled 5am and 8pm reminders are not implemented yet.

## Future Improvements

- 5am daily itinerary reminders
- 8pm tomorrow review reminder
- Better recurrence editing
- Optional natural-language quick-add
- Public multi-user version with proper OAuth
