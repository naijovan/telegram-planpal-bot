## Telegram Itinerary Assistant

This repository is building a beginner-friendly Telegram itinerary assistant bot.
The current implementation is past Phase 5: the bot reads from Google Calendar,
can create/edit/delete primary-calendar events through Telegram, supports date
selection for `/amend`, warns about overlaps, rejects past `/add` dates, can
create recurring Google Calendar events, and includes daily Important Tasks.

This repository is the first phase of a Telegram itinerary assistant bot that will eventually sync with Google Calendar and send scheduled itinerary reminders.

## Phase 1 goals

- Build a simple Telegram bot using `python-telegram-bot`
- Respond to these commands with placeholder text:
  - `/start`
  - `/help`
  - `/connect_calendar`
  - `/add`
  - `/today`
  - `/tomorrow`
- Use environment variables for the Telegram token
- Keep the code modular and beginner-friendly

## Main files

-- `bot.py` - main Telegram bot logic
-- `database.py` - local SQLite storage for drafts and local Google event references
-- `calendar_service.py` - Google Calendar OAuth, event fetching, creation, editing, and deletion
-- `requirements.txt` - Python dependencies
-- `.env.example` - example environment variables file
-- `.gitignore` - files to ignore in git

## Setup

1. Create a virtual environment (recommended):

```bash
cd "Telegram Bot"
python3 -m venv venv
source venv/bin/activate
```

2. Install dependencies:

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

3. Create a `.env` file from `.env.example`:

```bash
cp .env.example .env
```

4. Edit `.env` and set your Telegram bot token from BotFather:

```text
TELEGRAM_BOT_TOKEN=your_actual_bot_token_here
```

## Run the bot

```bash
python3 bot.py
```

Then open Telegram and send `/start` to your bot.

## Google Calendar setup

Google Calendar is the main source of truth for timed itinerary events. The bot
can read your primary Google Calendar, create events with `/add`, and edit/delete
Google Calendar events with `/amend`. The older `/edit` and `/delete` commands
still work as aliases for `/amend`.

1. Go to Google Cloud Console:
   https://console.cloud.google.com/

2. Create a new project, or select an existing personal project.

3. Enable the Google Calendar API:
   - Open `APIs & Services`
   - Open `Library`
   - Search for `Google Calendar API`
   - Click `Enable`

4. Configure the OAuth consent screen:
   - Use `External` unless you are in a Google Workspace organization
   - App name can be something like `Telegram Itinerary Bot`
   - Add your own Google account as a test user while the app is in testing

5. Create OAuth credentials:
   - Open `APIs & Services` -> `Credentials`
   - Click `Create credentials` -> `OAuth client ID`
   - Choose `Desktop app`
   - Download the JSON file

6. Rename the downloaded file to:

```text
credentials.json
```

7. Place `credentials.json` in this project folder:

```text
/Users/naijovan/Telegram Bot/credentials.json
```

8. Run the one-time login flow:

```bash
python3 calendar_service.py auth
```

This opens a browser login. After you approve Calendar event access,
`token.json` will be created locally.

If your `token.json` was created during Phase 3 with read-only permission, run
this command again to grant write permission:

```bash
python3 calendar_service.py auth
```

Keep these files private and out of GitHub:

```text
.env
credentials.json
token.json
bot_data.db
*.db
bot.log
```

## What to test now

This project is beyond Phase 5. Test the current feature set below.

- `/start` should return a welcome message and list commands
- `/help` should explain the menu structure
- Main menu should show `/start`, `/add`, `/amend`, `/view`, `/tasks`, and `/help`
- `/view` should open the view menu with `/today`, `/tomorrow`, `/other_days`, and `/back`
- `/add` should start a guided event creation flow and save to Google Calendar
- `/add` should reject custom dates that are already in the past
- `/add` should warn if the new event overlaps another event, then offer `Proceed` or `Change timing`
- `/add` should let you choose whether the event is recurring
- `/skip` should skip optional location or notes during `/add`
- `/cancel` should cancel the active event draft
- `/today` should still show Google Calendar events for today after OAuth setup
- `/tomorrow` should still show Google Calendar events for tomorrow after OAuth setup
- `/other_days` should open a clickable calendar picker for custom dates
- `/local_today` should show locally saved events for today
- `/local_tomorrow` should show locally saved events for tomorrow
- `/connect_calendar` should show setup instructions
- `/connect_calendar` should also show whether packages, `credentials.json`, `token.json`, and Calendar write permission are ready
- `/amend` should let you choose Today, Tomorrow, or a custom date
- `/amend` should let you edit title, date, start time, end time, location, and notes
- `/amend` should let you delete the selected event
- `/edit` and `/delete` should behave as `/amend` aliases
- `/tasks` should open the Important Tasks menu
- `/add_task` should add a task for today
- `/done_task` should mark a pending task done
- `/edit_task` should rename an important task
- `/delete_task` should delete a task after confirmation
- Today task changes should automatically refresh the pinned task summary and Calendar all-day task event
- `/refresh_tasks` manually rebuilds the latest task summary and only tries to pin it for today
- `/back` should return to the main menu

### Expected `/add` flow

1. Send `/add`
2. Choose `Today`, `Tomorrow`, or `Other days`
3. Choose a period: `Early Morning`, `Morning`, `Afternoon`, `Evening`
4. Choose a start time
5. Choose an end time
6. Enter the event title
7. Enter a location or send `/skip`
8. Enter notes or send `/skip`
9. Choose whether the event repeats
10. If recurring, choose the recurrence end date from the calendar picker
11. Choose Daily, Weekly on the same day, Monthly on the same week/day, Annually on this date, Weekdays, or Custom dates
12. For Custom dates, choose each recurrence date from the calendar and tap `Stop selecting dates`
13. If the event overlaps another event, choose `Proceed` or `Change timing`
14. Confirm to save the event to Google Calendar, edit the title, or cancel

### Menu structure

Main menu:

```text
[/start] [/add] [/amend]
[/view] [/tasks]
[/help]
```

View menu:

```text
[/today] [/tomorrow]
[/other_days]
[/back]
```

Task menu:

```text
[/add_task] [/done_task]
[/edit_task] [/delete_task]
[/refresh_tasks] [/back]
```

### Important Tasks

Important Tasks are daily bookmarks stored in SQLite. They are not normal timed
events. You can create them for today, tomorrow, or a custom future date.

- `/tasks` asks which Important Tasks date to use. Choose Today, Tomorrow, or use the Other days calendar picker.
- Past task dates are rejected as invalid.
- After a date is selected, the bot prints the quick guide as one message, then prints the Important Tasks list as a separate message.
- Only today's separate task-list message is pinned after old known task summaries are unpinned. Future task dates are shown but not pinned.
- `/add_task` asks for the task text, saves it for the selected date, shows the updated list, refreshes the pinned Telegram summary only for today, and creates or updates one all-day Google Calendar event named `Important Tasks`.
- `/done_task` lets you mark one pending task as done.
- `/edit_task` lets you rename one important task.
- `/delete_task` lets you delete one task after confirmation.
- `/refresh_tasks` manually rebuilds the selected date’s task summary. It only unpins old known task summaries and asks Telegram to pin again when the selected date is today.
- If all of today's tasks are deleted, the pinned Telegram summary remains and says `No important tasks for today.`
- If there are no tasks for the day, the Google Calendar all-day `Important Tasks` event is deleted.

### What still is not yet implemented

- scheduled 5am/8pm reminders
- editing recurrence rules after creation
- full natural-language event entry
- conflict detection across every occurrence of a recurring event

## Next phase

The next useful phase is reminders and polish: scheduled morning/evening
summaries, natural-language input, and deeper recurring-event editing.

## Phase 2 status

- Added local draft storage in SQLite (`database.py`).
- Added the guided `/add` button flow with:
  - date selection
  - time period selection
  - start time and end time selection
  - title, location, and notes entry
  - confirm / cancel flow
- Added `/skip` to bypass optional fields
- Added `/today` and `/tomorrow` for locally stored events

## Phase 3 status

- Added Google Calendar read-only OAuth support in `calendar_service.py`.
- Added primary-calendar lookup for one Singapore calendar day.
- `/today` and `/tomorrow` read Google Calendar after setup.
- `/gcal_today` and `/gcal_tomorrow` are aliases.
- `/local_today` and `/local_tomorrow` preserve Phase 2 local event display.
- `/add`, `/edit`, and `/delete` still do not write to Google Calendar.

## Phase 4 status

- `/add` creates a timed event in your primary Google Calendar.
- `/amend` lists Google Calendar events and can edit or delete the selected event.
- Local SQLite stores draft flow state and a local reference for bot-created Google events.
- `/today` and `/tomorrow` continue to read from Google Calendar.

## Phase 5 status

- `/add` rejects custom dates before today.
- `/add` checks for same-day timed-event overlaps before saving.
- Overlaps offer `Proceed`, `Change timing`, or `Cancel`.
- `/add` supports recurring Google Calendar events: Daily, Weekly on the same day, Monthly on the same week/day, Annually on this date, Weekdays, and Custom selected dates.
- `/amend` asks which date to work with.
- `/amend` can update title, date, start time, end time, location, and notes.
- Recurring events offer single-occurrence or whole-series edit/delete choices.
- `/edit` and `/delete` remain aliases for `/amend`.

## Important Tasks status

- `/tasks` opens today’s Important Tasks menu.
- Important Tasks are stored in SQLite by Singapore date.
- Telegram keeps one pinned Important Tasks summary for today when pin permissions allow it.
- Google Calendar gets one all-day `Important Tasks` event per day with the Pending and Done lists in the description.
- Adding, editing, deleting, and marking tasks done automatically shows the updated list. Pin refresh only happens for today's task list.
- `/refresh_tasks` is designed so a future 5am scheduler can call the same refresh logic.

## How far are we?

- Phase 1: complete
- Phase 2: complete for local event creation and display, with small known limitations
- Phase 3: implemented for Google Calendar read-only lookup
- Phase 4: implemented for Google Calendar create/edit/delete
- Phase 5: implemented for date-aware edit/delete, overlap warnings, and simple recurrence
- Important Tasks: implemented for dated task lists, today-only pin refresh, and one all-day Calendar event per day

## Testing checklist

```bash
python3 -m py_compile bot.py database.py calendar_service.py test_bot.py
pip install -r requirements.txt
python3 calendar_service.py auth
python3 bot.py
```

Then test these commands in Telegram:

```text
/start
/help
/connect_calendar
/view
/today
/tomorrow
/other_days
/add
/amend
/edit
/delete
/tasks
/add_task
/done_task
/edit_task
/delete_task
/refresh_tasks
/back
```

Manual Calendar checks:

- Add one event manually in Google Calendar for today, then send `/today`.
- Add one event manually in Google Calendar for tomorrow, then send `/tomorrow`.
- Create an all-day event and confirm it appears as `All day: Event title`.
- Use `/add` to create a test event, then confirm it appears in Google Calendar and `/today`.
- Use `/add`, choose `Other days`, and confirm past dates are not available in the calendar picker.
- Use `/add` to create an overlapping test event and confirm it asks whether to proceed or change timing.
- Use `/add` to create a Daily recurring test event and confirm it appears in Google Calendar.
- Use `/amend` to edit that test event's title/date/time/location/notes, using the calendar picker for date changes, then confirm Google Calendar changes.
- Use `/amend` to delete the test event, then confirm it disappears from Google Calendar and `/today`.
- Use `/view`, tap `/other_days`, pick a date from the calendar, and confirm that date’s events appear.
- Use `/tasks`, choose Today/Tomorrow or choose a future date from the calendar picker, and confirm the task keyboard appears.
- Try a past task date and confirm it is rejected as invalid.
- Use `/add_task`, type a task for today, and confirm the pinned Important Tasks summary updates.
- Choose a future task date, use `/add_task`, and confirm it shows the list without pinning it.
- Confirm Google Calendar has one all-day event called `Important Tasks`.
- Use `/done_task` and confirm the task moves under Done.
- Use `/edit_task` and confirm the renamed task appears in the updated list.
- Use `/delete_task` and confirm the task is removed after confirmation.
- Use `/refresh_tasks` for today to manually rebuild and try to pin the latest task summary.
- Use `/refresh_tasks` for a future task date and confirm it rebuilds without changing pins.
