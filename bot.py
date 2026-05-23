import logging
import os
import calendar as calendar_lib

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from telegram.error import TelegramError
import database
import calendar_service
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from typing import Optional

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TIMEZONE = "Asia/Singapore"
LOCAL_TZ = ZoneInfo(TIMEZONE)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)


def build_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["/start", "/add", "/amend"], ["/view", "/tasks"], ["/help"]],
        resize_keyboard=True,
    )


def build_view_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["/today", "/tomorrow"], ["/other_days"], ["/back"]],
        resize_keyboard=True,
    )


def build_task_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["/add_task", "/done_task"],
            ["/edit_task", "/delete_task"],
            ["/refresh_tasks", "/back"],
        ],
        resize_keyboard=True,
    )


def build_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["/cancel"]], resize_keyboard=True)


def build_skip_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["/skip", "/cancel"]], resize_keyboard=True)


def build_task_date_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Today", callback_data="taskdate:today")],
            [InlineKeyboardButton("Tomorrow", callback_data="taskdate:tomorrow")],
            [InlineKeyboardButton("Other days", callback_data="taskdate:other")],
            [InlineKeyboardButton("Cancel", callback_data="taskdate:cancel")],
        ]
    )


def build_tomorrow_review_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("View tomorrow", callback_data="review:view_tomorrow"),
                InlineKeyboardButton("Add event", callback_data="review:add_event"),
            ],
            [
                InlineKeyboardButton("Mark as No Plans", callback_data="review:no_plans"),
                InlineKeyboardButton("Done", callback_data="review:done"),
            ],
        ]
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start and introduce the bot."""
    database.save_bot_user(update.effective_user.id, update.effective_chat.id)
    message = (
        "Hello! I am your itinerary assistant bot.\n\n"
        "I can help you review and manage your Google Calendar itinerary.\n\n"
        "Main commands:\n"
        "/start - Show this welcome message\n"
        "/help - Show available commands\n"
        "/connect_calendar - Check Google Calendar setup instructions\n"
        "/add - Start creating a new event\n"
        "/amend - Edit or delete a Google Calendar event\n"
        "/view - View today, tomorrow, or pick another date\n"
        "/other_days - Pick another date from a calendar\n"
        "/tasks - Manage important tasks by date\n"
        "/today - Show today’s Google Calendar schedule\n"
        "/tomorrow - Show tomorrow’s Google Calendar schedule\n"
    )
    await update.message.reply_text(message, reply_markup=build_main_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help and list commands."""
    message = (
        "Here are the commands you can use now:\n\n"
        "/start - Welcome message and command list\n"
        "/help - This help text\n"
        "/connect_calendar - Check Google Calendar setup instructions\n"
        "/add - Create a Google Calendar event with optional recurrence\n"
        "/amend - Choose a date, then edit or delete a Google Calendar event\n"
        "/view - View today, tomorrow, or pick another date\n"
        "/other_days - Pick another date from a calendar\n"
        "/tasks - Choose a date and open important task tools\n"
        "/today - Show today’s Google Calendar events, usually from /view\n"
        "/tomorrow - Show tomorrow’s Google Calendar events, usually from /view\n"
        "/add_task - Add an important task for today\n"
        "/edit_task - Rename an important task\n"
        "/done_task - Mark an important task done\n"
        "/delete_task - Delete an important task\n"
        "/refresh_tasks - Manual fallback to refresh the pinned important task summary\n"
        "/edit - Alias for /amend\n"
        "/delete - Alias for /amend\n"
        "/cancel - Cancel the current action\n"
        "/skip - Skip optional location or notes entry\n"
        "/back - Return to the main menu\n"
    )
    await update.message.reply_text(message, reply_markup=build_main_keyboard())


def format_event_summary(event_data: dict) -> str:
    title = event_data.get("title", "(no title)")
    date = event_data.get("date", "?")
    start = event_data.get("start_time", "?")
    end = event_data.get("end_time", "?")
    location = event_data.get("location", "No location")
    notes = event_data.get("notes", "No notes")
    return (
        f"Title: {title}\n"
        f"Date: {date}\n"
        f"Start: {start}\n"
        f"End: {end}\n"
        f"Location: {location or 'No location'}\n"
        f"Notes: {notes or 'No notes'}"
    )


def singapore_today():
    return datetime.now(LOCAL_TZ).date()


def parse_date_input(text: str):
    return datetime.fromisoformat(text.strip()).date()


def parse_time_input(text: str) -> str:
    parsed = time.fromisoformat(text.strip())
    return parsed.strftime("%H:%M")


def is_past_date(date_value) -> bool:
    return date_value < singapore_today()


PERIOD_RANGES = {
    "early": ("Early Morning", 0, 5, 0),
    "morning": ("Morning", 6, 11, 45),
    "afternoon": ("Afternoon", 12, 17, 45),
    "evening": ("Evening", 18, 23, 45),
}


def time_to_minutes(time_text: str) -> int:
    parsed = time.fromisoformat(time_text)
    return parsed.hour * 60 + parsed.minute


def minutes_to_time(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def round_up_to_next_quarter(dt: datetime | None = None) -> str | None:
    """Return the next 15-minute slot in HH:MM, or None if today has no slots left."""
    dt = dt or datetime.now(LOCAL_TZ)
    minutes = dt.hour * 60 + dt.minute
    rounded = ((minutes + 14) // 15) * 15
    if rounded >= 24 * 60:
        return None
    return minutes_to_time(rounded)


def get_min_start_time_for_date(date_text: str | None) -> str | None:
    if not date_text:
        return None
    try:
        event_date = parse_date_input(date_text)
    except Exception:
        return None
    if event_date == singapore_today():
        return round_up_to_next_quarter()
    return None


def get_period_time_range(
    period: str,
    for_start: bool = True,
    min_start_time: str | None = None,
) -> list[str]:
    _label, start_h, end_h, end_m = PERIOD_RANGES.get(period, PERIOD_RANGES["morning"])
    times: list[str] = []
    current = start_h * 60
    end_min = end_h * 60 + end_m
    while current <= end_min:
        hour = current // 60
        minute = current % 60
        times.append(f"{hour:02d}:{minute:02d}")
        current += 15
    if for_start and times:
        # the last valid start is 15 minutes before the final end time
        times = times[:-1]
    if for_start and min_start_time:
        min_minutes = time_to_minutes(min_start_time)
        times = [slot for slot in times if time_to_minutes(slot) >= min_minutes]
    return times


def get_day_end_time_options(start_time: str) -> list[str]:
    end_options = get_period_time_range("early", for_start=False)
    end_options += get_period_time_range("morning", for_start=False)
    end_options += get_period_time_range("afternoon", for_start=False)
    end_options += get_period_time_range("evening", for_start=False)
    return [slot for slot in end_options if slot > start_time]


def build_period_keyboard(
    date_text: str | None = None,
    min_start_time: str | None = None,
) -> InlineKeyboardMarkup | None:
    min_time = min_start_time if min_start_time is not None else get_min_start_time_for_date(date_text)
    keyboard = []
    for period, (label, _start_h, _end_h, _end_m) in PERIOD_RANGES.items():
        if get_period_time_range(period, for_start=True, min_start_time=min_time):
            keyboard.append([InlineKeyboardButton(label, callback_data=f"add:period:{period}")])
    if not keyboard:
        return None
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="add:cancel:yes")])
    return InlineKeyboardMarkup(keyboard)


def build_button_grid(strings: list[str], callback_prefix: str) -> list[list[InlineKeyboardButton]]:
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for label in strings:
        row.append(InlineKeyboardButton(label, callback_data=f"{callback_prefix}:{label}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return buttons


def add_cancel_row(buttons: list[list[InlineKeyboardButton]], callback_data: str) -> list[list[InlineKeyboardButton]]:
    buttons.append([InlineKeyboardButton("Cancel", callback_data=callback_data)])
    return buttons


def build_confirmation_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("Confirm", callback_data="add:confirm:yes")],
        [InlineKeyboardButton("Edit title", callback_data="add:edit:title")],
        [InlineKeyboardButton("Cancel", callback_data="add:cancel:yes")],
    ]
    return InlineKeyboardMarkup(buttons)


def build_recurring_keyboard(is_recurring: bool = False) -> InlineKeyboardMarkup:
    yes_label = "Recurring: ON" if is_recurring else "Recurring: OFF"
    buttons = [
        [InlineKeyboardButton(yes_label, callback_data="add:recurring:yes")],
        [InlineKeyboardButton("Not recurring", callback_data="add:recurring:no")],
        [InlineKeyboardButton("Cancel", callback_data="add:cancel:yes")],
    ]
    return InlineKeyboardMarkup(buttons)


def build_recurrence_frequency_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("Daily", callback_data="add:rtype:DAILY")],
        [InlineKeyboardButton("Weekly on same day", callback_data="add:rtype:WEEKLY")],
        [InlineKeyboardButton("Monthly on same week/day", callback_data="add:rtype:MONTHLY")],
        [InlineKeyboardButton("Annually on this date", callback_data="add:rtype:YEARLY")],
        [InlineKeyboardButton("Weekdays (Mon-Fri)", callback_data="add:rtype:WEEKDAYS")],
        [InlineKeyboardButton("Custom dates", callback_data="add:rtype:CUSTOM")],
        [InlineKeyboardButton("Cancel", callback_data="add:cancel:yes")],
    ]
    return InlineKeyboardMarkup(buttons)


def build_overlap_keyboard(mode: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Proceed", callback_data=f"overlap:{mode}:proceed")],
            [InlineKeyboardButton("Change timing", callback_data=f"overlap:{mode}:change_timing")],
            [InlineKeyboardButton("Cancel", callback_data=f"overlap:{mode}:cancel")],
        ]
    )


def format_overlap_message(conflicts: list[calendar_service.CalendarEvent]) -> str:
    lines = ["This timing overlaps with existing event(s):"]
    for event in conflicts:
        if event.all_day:
            lines.append(f"- All day: {event.title}")
        else:
            lines.append(
                f"- {event.start.strftime('%H:%M')} - {event.end.strftime('%H:%M')}: {event.title}"
            )
    lines.append("\nDo you want to proceed anyway, or change timing?")
    return "\n".join(lines)


def find_overlapping_events(event_data: dict, exclude_google_event_id: str | None = None):
    try:
        event_date = parse_date_input(event_data["date"])
        start_dt = datetime.combine(event_date, time.fromisoformat(event_data["start_time"]), tzinfo=LOCAL_TZ)
        end_dt = datetime.combine(event_date, time.fromisoformat(event_data["end_time"]), tzinfo=LOCAL_TZ)
    except Exception:
        return []

    conflicts = []
    for event in calendar_service.get_events_for_day(event_date):
        if (
            event.all_day
            or event.google_event_id == exclude_google_event_id
            or event.recurring_event_id == exclude_google_event_id
        ):
            continue
        if start_dt < event.end and end_dt > event.start:
            conflicts.append(event)
    return conflicts


def calendar_event_to_draft(event: calendar_service.CalendarEvent) -> dict:
    if event.all_day:
        start_time = "All day"
        end_time = "All day"
        date_text = event.start.isoformat()
    else:
        start_time = event.start.strftime("%H:%M")
        end_time = event.end.strftime("%H:%M")
        date_text = event.start.date().isoformat()

    return {
        "google_event_id": event.google_event_id,
        "title": event.title,
        "date": date_text,
        "start_time": start_time,
        "end_time": end_time,
        "location": event.location,
        "notes": event.description,
        "all_day": event.all_day,
        "recurring_event_id": event.recurring_event_id,
    }


def is_recurring_calendar_event(event_data: dict) -> bool:
    return bool(event_data.get("recurring_event_id"))


def build_recurring_scope_keyboard(mode: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Only this occurrence", callback_data=f"recurring:{mode}:single")],
            [InlineKeyboardButton("Whole recurring series", callback_data=f"recurring:{mode}:series")],
            [InlineKeyboardButton("Cancel", callback_data=f"recurring:{mode}:cancel")],
        ]
    )


def build_edit_fields_keyboard(selected: dict) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Title", callback_data="event:editfield:title")],
        [InlineKeyboardButton("Date", callback_data="event:editfield:date")],
    ]
    if not selected.get("all_day"):
        rows.append(
            [
                InlineKeyboardButton("Start time", callback_data="event:editfield:start_time"),
                InlineKeyboardButton("End time", callback_data="event:editfield:end_time"),
            ]
        )
    rows.extend(
        [
            [InlineKeyboardButton("Location", callback_data="event:editfield:location")],
            [InlineKeyboardButton("Notes", callback_data="event:editfield:notes")],
            [InlineKeyboardButton("Cancel", callback_data="event:cancel")],
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_calendar_update_fields(updated_event: dict, changed_fields: dict) -> dict:
    update_fields = dict(changed_fields)
    if any(key in changed_fields for key in ("date", "start_time", "end_time")):
        update_fields["date"] = changed_fields.get("date", updated_event["date"])
        update_fields["start_time"] = changed_fields.get("start_time", updated_event["start_time"])
        update_fields["end_time"] = changed_fields.get("end_time", updated_event["end_time"])
    return update_fields


def build_google_events_keyboard(events: list[calendar_service.CalendarEvent]) -> InlineKeyboardMarkup:
    buttons = []
    for index, event in enumerate(events):
        if event.all_day:
            label = f"All day {event.title[:35]}"
        else:
            label = f"{event.start.strftime('%H:%M')}-{event.end.strftime('%H:%M')} {event.title[:30]}"
        if event.recurring_event_id:
            label = f"{label} (recurring)"
        buttons.append([InlineKeyboardButton(label, callback_data=f"event:select:{index}")])
        buttons.append(
            [
                InlineKeyboardButton("Edit", callback_data=f"event:edit:{index}"),
                InlineKeyboardButton("Delete", callback_data=f"event:delete:{index}"),
            ]
        )
    buttons.append([InlineKeyboardButton("Cancel", callback_data="event:cancel")])
    return InlineKeyboardMarkup(buttons)


def get_selected_calendar_event(user_id: int, index_text: str) -> dict | None:
    draft = database.get_draft(user_id)
    if not draft:
        return None
    events = draft.get("data", {}).get("events", [])
    try:
        index = int(index_text)
    except ValueError:
        return None
    if index < 0 or index >= len(events):
        return None
    return events[index]


def build_event_date_keyboard(mode: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Today", callback_data=f"eventdate:{mode}:today")],
            [InlineKeyboardButton("Tomorrow", callback_data=f"eventdate:{mode}:tomorrow")],
            [InlineKeyboardButton("Other days", callback_data=f"eventdate:{mode}:pick")],
            [InlineKeyboardButton("Cancel", callback_data="eventdate:cancel:yes")],
        ]
    )


def format_important_tasks_summary(task_date: str, tasks: list[dict]) -> str:
    lines = [f"Important tasks for {task_date}", ""]
    if not tasks:
        no_task_text = "No important tasks for today." if task_date == today_text() else "No important tasks for this date."
        lines.append(no_task_text)
        return "\n".join(lines)

    pending = [task for task in tasks if task.get("status") == "pending"]
    done = [task for task in tasks if task.get("status") == "done"]

    if pending:
        lines.append("Pending:")
        for index, task in enumerate(pending, start=1):
            lines.append(f"{index}. {task['title']}")

    if done:
        if pending:
            lines.append("")
        lines.append("Done:")
        for index, task in enumerate(done, start=1):
            lines.append(f"{index}. {task['title']}")

    return "\n".join(lines)


def build_task_selection_keyboard(tasks: list[dict], action: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(task["title"][:50], callback_data=f"task:{action}:{task['id']}")]
        for task in tasks
    ]
    buttons.append([InlineKeyboardButton("Cancel", callback_data="task:cancel")])
    return InlineKeyboardMarkup(buttons)


def today_text() -> str:
    return singapore_today().isoformat()


def is_today_text(task_date: str) -> bool:
    return task_date == today_text()


def tomorrow_text() -> str:
    return (singapore_today() + timedelta(days=1)).isoformat()


def get_selected_task_date(user_id: int) -> str:
    draft = database.get_draft(user_id)
    if draft:
        data = draft.get("data", {})
        task_date = data.get("task_date")
        if task_date:
            try:
                if not is_past_date(parse_date_input(task_date)):
                    return task_date
            except Exception:
                pass
    return today_text()


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    month_index = year * 12 + month - 1 + delta
    return month_index // 12, month_index % 12 + 1


def build_calendar_picker_keyboard(
    target: str,
    year: int | None = None,
    month: int | None = None,
    min_date=None,
) -> InlineKeyboardMarkup:
    today_day = singapore_today()
    year = year or today_day.year
    month = month or today_day.month
    prev_year, prev_month = shift_month(year, month, -1)
    next_year, next_month = shift_month(year, month, 1)

    rows = [
        [InlineKeyboardButton(f"{calendar_lib.month_name[month]} {year}", callback_data="cal:noop")],
        [
            InlineKeyboardButton("<", callback_data=f"cal:{target}:month:{prev_year}-{prev_month:02d}"),
            InlineKeyboardButton(">", callback_data=f"cal:{target}:month:{next_year}-{next_month:02d}"),
        ],
        [InlineKeyboardButton(day, callback_data="cal:noop") for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]],
    ]

    for week in calendar_lib.monthcalendar(year, month):
        row = []
        for day_number in week:
            if day_number == 0:
                row.append(InlineKeyboardButton(" ", callback_data="cal:noop"))
                continue
            selected_day = date(year, month, day_number)
            if min_date and selected_day < min_date:
                row.append(InlineKeyboardButton(" ", callback_data="cal:noop"))
            else:
                row.append(
                    InlineKeyboardButton(
                        str(day_number),
                        callback_data=f"cal:{target}:day:{selected_day.isoformat()}",
                    )
                )
        rows.append(row)

    rows.append([InlineKeyboardButton("Cancel", callback_data=f"cal:{target}:cancel")])
    return InlineKeyboardMarkup(rows)


def recurrence_type_label(recurrence_type: str | None) -> str:
    labels = {
        "DAILY": "Daily",
        "WEEKLY": "Weekly on same day",
        "MONTHLY": "Monthly on same week/day",
        "YEARLY": "Annually on this date",
        "WEEKDAYS": "Weekdays (Mon-Fri)",
        "CUSTOM": "Custom dates",
    }
    return labels.get(recurrence_type or "", recurrence_type or "")


def calendar_min_date_for_target(user_id: int, target: str):
    today = singapore_today()
    if target in {"task", "add", "editdate"}:
        return today
    if target in {"recur", "customrecur"}:
        draft = database.get_draft(user_id)
        data = draft.get("data", {}) if draft else {}
        try:
            event_date = parse_date_input(data["date"])
            return max(today, event_date)
        except Exception:
            return today
    return None


def build_context_calendar_keyboard(
    user_id: int,
    target: str,
    year: int | None = None,
    month: int | None = None,
) -> InlineKeyboardMarkup:
    return build_calendar_picker_keyboard(
        target,
        year,
        month,
        min_date=calendar_min_date_for_target(user_id, target),
    )


def build_custom_recurrence_keyboard(
    user_id: int,
    year: int | None = None,
    month: int | None = None,
) -> InlineKeyboardMarkup:
    draft = database.get_draft(user_id)
    data = draft.get("data", {}) if draft else {}
    today_day = singapore_today()
    event_date = parse_date_input(data.get("date", today_text()))
    until_date = parse_date_input(data.get("recurrence_until", data.get("date", today_text())))
    min_date = max(today_day, event_date)
    selected_dates = set(data.get("recurrence_custom_dates") or [])
    year = year or event_date.year
    month = month or event_date.month
    prev_year, prev_month = shift_month(year, month, -1)
    next_year, next_month = shift_month(year, month, 1)

    rows = [
        [InlineKeyboardButton(f"{calendar_lib.month_name[month]} {year}", callback_data="cal:noop")],
        [
            InlineKeyboardButton("<", callback_data=f"customrecur:month:{prev_year}-{prev_month:02d}"),
            InlineKeyboardButton(">", callback_data=f"customrecur:month:{next_year}-{next_month:02d}"),
        ],
        [InlineKeyboardButton(day, callback_data="cal:noop") for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]],
    ]
    for week in calendar_lib.monthcalendar(year, month):
        row = []
        for day_number in week:
            if day_number == 0:
                row.append(InlineKeyboardButton(" ", callback_data="cal:noop"))
                continue
            selected_day = date(year, month, day_number)
            if selected_day < min_date or selected_day > until_date:
                row.append(InlineKeyboardButton(" ", callback_data="cal:noop"))
                continue
            label = f"*{day_number}" if selected_day.isoformat() in selected_dates else str(day_number)
            row.append(
                InlineKeyboardButton(
                    label,
                    callback_data=f"customrecur:day:{selected_day.isoformat()}",
                )
            )
        rows.append(row)

    rows.append([InlineKeyboardButton("Stop selecting dates", callback_data="customrecur:done")])
    rows.append([InlineKeyboardButton("Cancel", callback_data="customrecur:cancel")])
    return InlineKeyboardMarkup(rows)


def event_mode_label(mode: str) -> str:
    if mode == "delete":
        return "delete"
    if mode == "edit":
        return "edit"
    return "amend"


async def send_google_events_for_date(target, user_id: int, mode: str, target_day) -> None:
    mode_label = event_mode_label(mode)
    try:
        events = calendar_service.get_events_for_day(target_day)
    except calendar_service.CalendarSetupError as exc:
        await target.reply_text(f"Google Calendar is not ready for {mode} yet.\n\n" + str(exc))
        return
    except calendar_service.CalendarApiError as exc:
        logger.warning("Google Calendar list error: %s", exc)
        await target.reply_text(f"I could not load Google Calendar events to {mode}. Please try again.")
        return

    if not events:
        await target.reply_text(f"No Google Calendar events found to {mode_label} for {target_day.isoformat()}.")
        return

    database.save_draft(
        user_id,
        "event_selection",
        {
            "mode": mode,
            "date": target_day.isoformat(),
            "events": [calendar_event_to_draft(event) for event in events],
        },
    )
    await target.reply_text(
        f"Select a Google Calendar event to {mode_label} for {target_day.isoformat()}:",
        reply_markup=build_google_events_keyboard(events),
    )


async def edit_google_events_message_text(query, user_id: int, mode: str, target_day) -> None:
    mode_label = event_mode_label(mode)
    try:
        events = calendar_service.get_events_for_day(target_day)
    except calendar_service.CalendarSetupError as exc:
        await query.edit_message_text(f"Google Calendar is not ready for {mode} yet.\n\n" + str(exc))
        return
    except calendar_service.CalendarApiError as exc:
        logger.warning("Google Calendar list error: %s", exc)
        await query.edit_message_text(f"I could not load Google Calendar events to {mode}. Please try again.")
        return

    if not events:
        await query.edit_message_text(f"No Google Calendar events found to {mode_label} for {target_day.isoformat()}.")
        return

    database.save_draft(
        user_id,
        "event_selection",
        {
            "mode": mode,
            "date": target_day.isoformat(),
            "events": [calendar_event_to_draft(event) for event in events],
        },
    )
    await query.edit_message_text(
        f"Select a Google Calendar event to {mode_label} for {target_day.isoformat()}:",
        reply_markup=build_google_events_keyboard(events),
    )


async def send_add_confirmation_message(message, data: dict) -> None:
    recurring_text = ""
    if data.get("recurring"):
        recurrence_type = data.get("recurrence_type") or data.get("recurrence_frequency")
        if recurrence_type == "CUSTOM":
            custom_dates = ", ".join(data.get("recurrence_custom_dates") or [])
            recurring_text = f"\nRecurring: Custom dates ({custom_dates})"
        else:
            recurring_text = (
                f"\nRecurring: {recurrence_type_label(recurrence_type)} "
                f"until {data.get('recurrence_until')}"
            )
    await message.reply_text(
        "Please review your event:\n\n"
        f"{format_event_summary(data)}{recurring_text}\n\n"
        "Tap Confirm to save to Google Calendar, Edit title to change the title, or Cancel to discard.",
        reply_markup=build_confirmation_keyboard(),
    )


async def edit_add_confirmation_message(query, data: dict) -> None:
    recurring_text = ""
    if data.get("recurring"):
        recurrence_type = data.get("recurrence_type") or data.get("recurrence_frequency")
        if recurrence_type == "CUSTOM":
            custom_dates = ", ".join(data.get("recurrence_custom_dates") or [])
            recurring_text = f"\nRecurring: Custom dates ({custom_dates})"
        else:
            recurring_text = (
                f"\nRecurring: {recurrence_type_label(recurrence_type)} "
                f"until {data.get('recurrence_until')}"
            )
    await query.edit_message_text(
        "Please review your event:\n\n"
        f"{format_event_summary(data)}{recurring_text}\n\n"
        "Tap Confirm to save to Google Calendar, Edit title to change the title, or Cancel to discard.",
        reply_markup=build_confirmation_keyboard(),
    )


async def connect_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Explain the local Google Calendar OAuth setup."""
    status = calendar_service.get_setup_status()
    packages = "OK" if status.packages_installed else "Missing"
    credentials = "OK" if status.credentials_file_exists else "Missing"
    token = "OK" if status.token_file_exists else "Missing"
    scope = "OK" if status.token_has_required_scopes else "Missing"
    ready_message = (
        "Calendar status: ready."
        if status.ready
        else "Calendar status: setup needed."
    )

    await update.message.reply_text(
        "Google Calendar sync is enabled for Phase 4.\n\n"
        f"{ready_message}\n"
        f"- Google packages: {packages}\n"
        f"- credentials.json: {credentials}\n"
        f"- token.json: {token}\n"
        f"- Calendar write permission: {scope}\n\n"
        "To connect it:\n"
        "1. Run: pip install -r requirements.txt\n"
        "2. Put your Google OAuth file at credentials.json in this project folder.\n"
        "3. If token.json was created before Phase 4, run auth again to grant write permission.\n"
        "4. Run this in Terminal:\n"
        "python3 calendar_service.py auth\n\n"
        "After token.json is ready, /add, /amend, /today, and /tomorrow will use your primary Google Calendar."
    )


def sync_important_tasks_calendar_event(
    user_id: int,
    chat_id: int,
    task_date: str,
    tasks: list[dict],
) -> str | None:
    task_pin = database.get_task_pin(user_id, chat_id, task_date)
    existing_event_id = task_pin.get("google_calendar_event_id") if task_pin else None

    if not tasks:
        if existing_event_id:
            calendar_service.delete_important_tasks_event(existing_event_id)
            database.update_task_pin_google_event_id(user_id, chat_id, task_date, None)
        return None

    event_id = calendar_service.create_or_update_important_tasks_event(
        parse_date_input(task_date),
        format_important_tasks_summary(task_date, tasks),
        existing_event_id=existing_event_id,
    )
    database.update_task_pin_google_event_id(user_id, chat_id, task_date, event_id)
    return event_id


async def pin_task_summary_message(message, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int) -> None:
    try:
        await context.bot.pin_chat_message(
            chat_id=chat_id,
            message_id=message_id,
            disable_notification=True,
        )
    except TelegramError as exc:
        if "already pinned" in str(exc).lower():
            return
        logger.info("Could not pin task summary: %s", exc)
        await message.reply_text(
            "Task summary updated, but I could not pin it. "
            "Please check whether the bot has permission to pin messages."
        )


async def unpin_task_summary_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int) -> None:
    try:
        await context.bot.unpin_chat_message(chat_id=chat_id, message_id=message_id)
    except TelegramError as exc:
        logger.info("Could not unpin old task summary: %s", exc)


async def unpin_known_task_summaries(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
    exclude_message_id: int | None = None,
) -> None:
    for task_pin in database.list_task_pins(user_id, chat_id):
        pinned_message_id = task_pin.get("pinned_message_id")
        if not pinned_message_id or pinned_message_id == exclude_message_id:
            continue
        await unpin_task_summary_message(context, chat_id, pinned_message_id)


async def refresh_important_tasks_summary(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
    task_date: str | None = None,
    unpin_old_task_pins: bool = False,
) -> tuple[str, str | None]:
    task_date = task_date or today_text()
    should_pin = is_today_text(task_date)
    if should_pin and unpin_old_task_pins:
        for old_pin in database.list_task_pins_before(user_id, chat_id, task_date):
            await unpin_task_summary_message(context, chat_id, old_pin["pinned_message_id"])
    if should_pin:
        database.clear_old_task_pins_if_needed(user_id, chat_id, task_date)
    tasks = database.list_important_tasks(user_id, task_date)
    summary = format_important_tasks_summary(task_date, tasks)
    task_pin = database.get_task_pin(user_id, chat_id, task_date)
    google_event_id = task_pin.get("google_calendar_event_id") if task_pin else None
    calendar_warning = None

    try:
        google_event_id = sync_important_tasks_calendar_event(user_id, chat_id, task_date, tasks)
    except calendar_service.CalendarSetupError as exc:
        calendar_warning = f"Google Calendar task event was not updated: {exc}"
    except calendar_service.CalendarApiError as exc:
        logger.warning("Important Tasks Calendar sync error: %s", exc)
        calendar_warning = "Google Calendar task event could not be updated."

    edited_existing = False
    if should_pin and task_pin and task_pin.get("pinned_message_id"):
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=task_pin["pinned_message_id"],
                text=summary,
            )
            edited_existing = True
            await pin_task_summary_message(message, context, chat_id, task_pin["pinned_message_id"])
        except TelegramError as exc:
            logger.info("Could not edit pinned task summary: %s", exc)

    if not edited_existing and should_pin:
        if should_pin and task_pin and task_pin.get("pinned_message_id"):
            await unpin_task_summary_message(context, chat_id, task_pin["pinned_message_id"])
        sent = await context.bot.send_message(chat_id=chat_id, text=summary)
        database.save_task_pin(
            user_id,
            chat_id,
            task_date,
            sent.message_id if should_pin else None,
            google_calendar_event_id=google_event_id,
        )
        if should_pin:
            await pin_task_summary_message(message, context, chat_id, sent.message_id)
    elif not should_pin:
        database.save_task_pin(
            user_id,
            chat_id,
            task_date,
            None,
            google_calendar_event_id=google_event_id,
        )

    if google_event_id is not None:
        database.update_task_pin_google_event_id(user_id, chat_id, task_date, google_event_id)

    return summary, calendar_warning


async def skip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    draft = database.get_draft(user_id)
    if not draft:
        await update.message.reply_text("There is no active draft to skip. Use /add to start a new event.")
        return

    stage = draft.get("stage")
    data = draft.get("data", {})

    if stage == "entered_location":
        data["location"] = ""
        database.save_draft(user_id, "entered_notes", data)
        await update.message.reply_text(
            "Location skipped. Enter notes, or use /skip to leave empty.",
            reply_markup=build_skip_cancel_keyboard(),
        )
        return

    if stage == "entered_notes":
        data["notes"] = ""
        database.save_draft(user_id, "recurring_selection", data)
        await update.message.reply_text(
            "Should this event repeat?",
            reply_markup=build_recurring_keyboard(False),
        )
        return

    await update.message.reply_text("Skip only works for optional location or notes entry during /add.")


async def view_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    database.save_draft(user_id, "awaiting_view_date", {})
    await update.message.reply_text(
        "Show today, tomorrow, or use /other_days to pick a date from a calendar.",
        reply_markup=build_view_keyboard(),
    )


async def other_days_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    draft = database.get_draft(user_id)
    stage = draft.get("stage") if draft else None
    data = draft.get("data", {}) if draft else {}
    if stage == "awaiting_task_date":
        target = "task"
    elif stage in {"date_selection", "awaiting_pick_date"}:
        target = "add"
        database.save_draft(user_id, "awaiting_pick_date", data)
    elif stage == "event_date_selection":
        target = "event_amend"
        database.save_draft(user_id, "awaiting_event_date", data)
    elif stage == "awaiting_recurrence_until":
        target = "recur"
    elif stage == "editing_event_field:date":
        target = "editdate"
    else:
        target = "view"
        database.save_draft(user_id, "awaiting_view_date", {})
    await update.message.reply_text(
        "Choose a date:",
        reply_markup=build_context_calendar_keyboard(user_id, target),
    )


async def back_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    database.clear_draft(user_id)
    await update.message.reply_text("Back to main menu.", reply_markup=build_main_keyboard())


async def open_task_menu_for_date(
    source_message,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
    task_date: str,
) -> None:
    database.save_draft(user_id, "task_menu", {"task_date": task_date})
    tasks = database.list_important_tasks(user_id, task_date)
    summary = format_important_tasks_summary(task_date, tasks)
    google_event_id = None
    calendar_warning = None

    try:
        google_event_id = sync_important_tasks_calendar_event(user_id, chat_id, task_date, tasks)
    except calendar_service.CalendarSetupError as exc:
        calendar_warning = f"Google Calendar task event was not updated: {exc}"
    except calendar_service.CalendarApiError as exc:
        logger.warning("Important Tasks Calendar sync error: %s", exc)
        calendar_warning = "Google Calendar task event could not be updated."

    guide_text = (
        f"Task menu opened for {task_date}.\n\n"
        "Quick guide:\n"
        "/add_task - Add an important task for this date\n"
        "/edit_task - Rename a task\n"
        "/done_task - Mark a task as done\n"
        "/delete_task - Delete a task\n"
        "/refresh_tasks - Show the latest list and try to pin it again\n"
        "/back - Return to the main menu"
    )
    if calendar_warning:
        guide_text = f"{guide_text}\n\n{calendar_warning}"
    await source_message.reply_text(guide_text, reply_markup=build_task_keyboard())
    sent_summary = await source_message.reply_text(summary)
    should_pin = is_today_text(task_date)
    if should_pin:
        await unpin_known_task_summaries(context, user_id, chat_id, exclude_message_id=sent_summary.message_id)
    database.save_task_pin(
        user_id,
        chat_id,
        task_date,
        sent_summary.message_id if should_pin else None,
        google_calendar_event_id=google_event_id,
    )
    if should_pin:
        await pin_task_summary_message(source_message, context, chat_id, sent_summary.message_id)


async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    database.save_draft(user_id, "awaiting_task_date", {})
    await update.message.reply_text(
        "Choose a date for Important Tasks.\n\n"
        "Tap Today, Tomorrow, or Other days to pick from a calendar. "
        "Past dates are not allowed.",
        reply_markup=build_task_date_keyboard(),
    )


async def add_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    task_date = get_selected_task_date(user_id)
    database.save_draft(user_id, "awaiting_task_title", {"task_date": task_date})
    await update.message.reply_text(
        f"Type the important task for {task_date}.",
        reply_markup=build_cancel_keyboard(),
    )


async def done_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    task_date = get_selected_task_date(user_id)
    tasks = [
        task for task in database.list_important_tasks(user_id, task_date)
        if task.get("status") == "pending"
    ]
    if not tasks:
        await update.message.reply_text(
            f"No pending important tasks for {task_date}.",
            reply_markup=build_task_keyboard(),
        )
        return
    await update.message.reply_text(
        f"Choose the task to mark as done for {task_date}:",
        reply_markup=build_task_selection_keyboard(tasks, "done"),
    )


async def delete_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    task_date = get_selected_task_date(user_id)
    tasks = database.list_important_tasks(user_id, task_date)
    if not tasks:
        await update.message.reply_text(
            f"No important tasks to delete for {task_date}.",
            reply_markup=build_task_keyboard(),
        )
        return
    await update.message.reply_text(
        f"Choose the task to delete for {task_date}:",
        reply_markup=build_task_selection_keyboard(tasks, "delete"),
    )


async def edit_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    task_date = get_selected_task_date(user_id)
    tasks = database.list_important_tasks(user_id, task_date)
    if not tasks:
        await update.message.reply_text(
            f"No important tasks to edit for {task_date}.",
            reply_markup=build_task_keyboard(),
        )
        return
    await update.message.reply_text(
        f"Choose the task to edit for {task_date}:",
        reply_markup=build_task_selection_keyboard(tasks, "edit"),
    )


async def refresh_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    task_date = get_selected_task_date(user_id)
    summary, calendar_warning = await refresh_important_tasks_summary(
        update.message,
        context,
        user_id,
        chat_id,
        task_date,
        unpin_old_task_pins=True,
    )
    message = f"Important task summary refreshed.\n\n{summary}"
    if calendar_warning:
        message = f"{message}\n\n{calendar_warning}"
    await update.message.reply_text(message, reply_markup=build_task_keyboard())


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    draft = database.get_draft(user_id)
    if not draft:
        await update.message.reply_text("There is no active action to cancel.", reply_markup=build_main_keyboard())
        return
    database.clear_draft(user_id)
    await update.message.reply_text("Action cancelled.", reply_markup=build_main_keyboard())


async def add_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /add as a placeholder for the guided event flow."""
    user_id = update.effective_user.id
    await send_add_event_date_prompt(update.message, user_id)


async def send_add_event_date_prompt(target, user_id: int) -> None:
    """Start the guided add-event flow using any Telegram message target."""
    keyboard = [
        [InlineKeyboardButton("Today", callback_data="add:date:today")],
        [InlineKeyboardButton("Tomorrow", callback_data="add:date:tomorrow")],
        [InlineKeyboardButton("Other days", callback_data="add:date:pick")],
        [InlineKeyboardButton("Cancel", callback_data="add:cancel:yes")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    database.save_draft(user_id, "date_selection", {})
    await target.reply_text("Choose a date for the event:", reply_markup=reply_markup)


async def continue_add_date_selection(query, user_id: int, draft_data: dict, selected_day) -> None:
    if is_past_date(selected_day):
        await query.edit_message_text(
            "Invalid date entered. Please choose today or a future date.",
            reply_markup=build_context_calendar_keyboard(user_id, "add"),
        )
        return

    date_str = selected_day.isoformat()
    draft_data["date"] = date_str
    database.save_draft(user_id, "period_selection", draft_data)
    period_keyboard = build_period_keyboard(date_str)
    if not period_keyboard:
        database.clear_draft(user_id)
        await query.edit_message_text(
            f"No available time slots left for {date_str}. "
            "Please use /add again and choose tomorrow or a future date."
        )
        return

    await query.edit_message_text(
        f"Date set to {date_str}. Now choose a time period:",
        reply_markup=period_keyboard,
    )


async def continue_recurrence_until_selection(query, user_id: int, data: dict, recurrence_until) -> None:
    try:
        event_date = parse_date_input(data["date"])
    except Exception:
        database.clear_draft(user_id)
        await query.edit_message_text("Event draft expired. Please use /add to start again.")
        return

    if recurrence_until < event_date:
        await query.edit_message_text(
            "Invalid date entered. Recurrence end date must be on or after the event date.",
            reply_markup=build_context_calendar_keyboard(user_id, "recur", event_date.year, event_date.month),
        )
        return

    data["recurrence_until"] = recurrence_until.isoformat()
    database.save_draft(user_id, "recurrence_type_selection", data)
    await query.edit_message_text(
        "How should this event repeat?",
        reply_markup=build_recurrence_frequency_keyboard(),
    )


async def continue_event_date_edit_selection(query, user_id: int, data: dict, selected_day) -> None:
    if is_past_date(selected_day):
        await query.edit_message_text(
            "Invalid date entered. Please choose today or a future date.",
            reply_markup=build_context_calendar_keyboard(user_id, "editdate"),
        )
        return

    google_event_id = data.get("google_event_id")
    if not google_event_id:
        await query.edit_message_text("No Google Calendar event found to edit. Use /amend to start again.")
        return

    updated_event = dict(data)
    updated_event["date"] = selected_day.isoformat()
    changed_fields = {"date": updated_event["date"]}

    try:
        conflicts = find_overlapping_events(updated_event, exclude_google_event_id=google_event_id)
    except calendar_service.CalendarSetupError as exc:
        await query.edit_message_text("Google Calendar is not ready for overlap checking.\n\n" + str(exc))
        return
    except calendar_service.CalendarApiError as exc:
        logger.warning("Google Calendar edit overlap check error: %s", exc)
        await query.edit_message_text("I could not check for overlapping events. Please try again.")
        return

    if conflicts:
        database.save_draft(
            user_id,
            "pending_edit_overlap",
            {"event": data, "updated": updated_event, "fields": changed_fields},
        )
        await query.edit_message_text(
            format_overlap_message(conflicts),
            reply_markup=build_overlap_keyboard("edit"),
        )
        return

    await apply_google_event_edit(query, user_id, updated_event, changed_fields)


async def create_google_event_from_draft(query, user_id: int, draft_data: dict) -> None:
    if not draft_data.get("overlap_override"):
        try:
            conflicts = find_overlapping_events(draft_data)
        except calendar_service.CalendarSetupError as exc:
            await query.edit_message_text("Google Calendar is not ready for overlap checking.\n\n" + str(exc))
            return
        except calendar_service.CalendarApiError as exc:
            logger.warning("Google Calendar overlap check error: %s", exc)
            await query.edit_message_text("I could not check for overlapping events. Please try again.")
            return

        if conflicts:
            database.save_draft(user_id, "pending_add_overlap", draft_data)
            await query.edit_message_text(
                format_overlap_message(conflicts),
                reply_markup=build_overlap_keyboard("add"),
            )
            return

    try:
        google_event_id = calendar_service.create_event(draft_data)
    except calendar_service.CalendarSetupError as exc:
        await query.edit_message_text(
            "Google Calendar is not ready for writing yet.\n\n"
            f"{exc}\n\n"
            "Your draft was not saved. Please fix Calendar setup and run /add again."
        )
        return
    except calendar_service.CalendarApiError as exc:
        logger.warning("Google Calendar create error: %s", exc)
        await query.edit_message_text(
            "I could not create the Google Calendar event. "
            "Your draft was not saved. Please try again."
        )
        return

    draft_data["google_event_id"] = google_event_id
    event_id = database.save_event(user_id, draft_data)
    database.clear_draft(user_id)
    await query.edit_message_text(
        f"Saved event to Google Calendar.\n"
        f"Local reference ID: {event_id}\n\n"
        + format_event_summary(draft_data)
    )


async def apply_google_event_edit(query, user_id: int, updated_event: dict, changed_fields: dict) -> None:
    google_event_id = updated_event.get("google_event_id")
    if not google_event_id:
        await query.edit_message_text("No Google Calendar event found to edit. Use /amend to start again.")
        return

    try:
        calendar_service.update_event(
            google_event_id,
            build_calendar_update_fields(updated_event, changed_fields),
        )
    except calendar_service.CalendarSetupError as exc:
        await query.edit_message_text("Google Calendar is not ready for editing yet.\n\n" + str(exc))
        return
    except calendar_service.CalendarApiError as exc:
        logger.warning("Google Calendar update error: %s", exc)
        database.clear_draft(user_id)
        await query.edit_message_text("I could not update that Google Calendar event. Please try again.")
        return

    database.clear_draft(user_id)
    changed_text = "\n".join(f"{key}: {value}" for key, value in changed_fields.items())
    await query.edit_message_text("Event updated in Google Calendar.\n\n" + changed_text)


async def delete_selected_google_event(query, user_id: int, selected: dict, delete_series: bool = False) -> None:
    google_event_id = (
        selected.get("recurring_event_id")
        if delete_series and selected.get("recurring_event_id")
        else selected.get("google_event_id")
    )
    if not google_event_id:
        await query.edit_message_text("No Google Calendar event found to delete. Use /amend to start again.")
        return

    try:
        calendar_service.delete_event(google_event_id)
    except calendar_service.CalendarSetupError as exc:
        await query.edit_message_text("Google Calendar is not ready for deleting yet.\n\n" + str(exc))
        return
    except calendar_service.CalendarApiError as exc:
        logger.warning("Google Calendar delete error: %s", exc)
        await query.edit_message_text("I could not delete that Google Calendar event. Please try again.")
        return

    database.delete_event_by_google_id(google_event_id)
    database.clear_draft(user_id)
    scope_text = "recurring series" if delete_series else "event occurrence"
    await query.edit_message_text(f"Deleted Google Calendar {scope_text}: {selected['title']}")


def replace_with_series_master_timing(selected: dict) -> dict:
    """Use the series master date/time when editing a whole recurring series."""
    series_event = calendar_service.get_event_by_id(selected["recurring_event_id"])
    prepared = dict(selected)
    prepared["google_event_id"] = selected["recurring_event_id"]
    prepared["edit_scope"] = "series"
    prepared["title"] = series_event.title
    prepared["location"] = series_event.location
    prepared["notes"] = series_event.description
    prepared["all_day"] = series_event.all_day
    if series_event.all_day:
        prepared["date"] = series_event.start.isoformat()
        prepared["start_time"] = "All day"
        prepared["end_time"] = "All day"
    else:
        prepared["date"] = series_event.start.date().isoformat()
        prepared["start_time"] = series_event.start.strftime("%H:%M")
        prepared["end_time"] = series_event.end.strftime("%H:%M")
    return prepared


async def add_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data  # format: add:action:value
    parts = data.split(":")
    if len(parts) < 3:
        await query.edit_message_text("Invalid action")
        return
    action = parts[1]
    val = ":".join(parts[2:])

    draft = database.get_draft(user_id) or {"stage": None, "data": {}}
    draft_data = draft.get("data", {})

    if action == "date":
        if val == "today":
            selected_day = singapore_today()
        elif val == "tomorrow":
            selected_day = singapore_today() + timedelta(days=1)
        else:
            database.save_draft(user_id, "awaiting_pick_date", draft_data)
            await query.edit_message_text(
                "Choose a date for the event:",
                reply_markup=build_context_calendar_keyboard(user_id, "add"),
            )
            return

        await continue_add_date_selection(query, user_id, draft_data, selected_day)
        return

    if action == "period":
        if not draft_data.get("date"):
            await query.edit_message_text("This event draft expired. Please use /add to start again.")
            return
        period = val
        draft_data["period"] = period
        database.save_draft(user_id, "start_time_selection", draft_data)

        start_options = get_period_time_range(
            period,
            for_start=True,
            min_start_time=get_min_start_time_for_date(draft_data.get("date")),
        )
        if not start_options:
            await query.edit_message_text(
                "That time period has already passed. Please use /add again and choose another period."
            )
            return
        buttons = add_cancel_row(build_button_grid(start_options, "add:start"), "add:cancel:yes")
        await query.edit_message_text("Select start time:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if action == "start":
        if not draft_data.get("date") or not draft_data.get("period"):
            await query.edit_message_text("This event draft expired. Please use /add to start again.")
            return
        start_time = val
        period = draft_data.get("period", "morning")
        valid_start_options = get_period_time_range(
            period,
            for_start=True,
            min_start_time=get_min_start_time_for_date(draft_data.get("date")),
        )
        if start_time not in valid_start_options:
            await query.edit_message_text(
                "That start time has already passed. Please use /add again and choose a valid time."
            )
            return
        draft_data["start_time"] = start_time
        database.save_draft(user_id, "end_time_selection", draft_data)

        end_options = get_day_end_time_options(start_time)

        if not end_options:
            await query.edit_message_text(
                "That start time has no valid end time in the selected period. "
                "Please choose a different start time."
            )
            return

        buttons = add_cancel_row(build_button_grid(end_options, "add:end"), "add:cancel:yes")
        await query.edit_message_text("Select end time:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if action == "end":
        if not draft_data.get("date") or not draft_data.get("start_time"):
            await query.edit_message_text("This event draft expired. Please use /add to start again.")
            return
        end_time = val
        start_time = draft_data.get("start_time")
        if start_time and end_time <= start_time:
            await query.edit_message_text(
                "Invalid end time. Please start again with /add and choose an end time after the start time."
            )
            return
        draft_data["end_time"] = end_time
        if draft_data.get("title"):
            database.save_draft(user_id, "confirm_event", draft_data)
            await edit_add_confirmation_message(query, draft_data)
            return

        database.save_draft(user_id, "entered_title", draft_data)
        await query.edit_message_text(
            "Enter the event title as a text message:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="add:cancel:yes")]]),
        )
        return

    if action == "confirm":
        await create_google_event_from_draft(query, user_id, draft_data)
        return

    if action == "recurring":
        if val == "no":
            draft_data["recurring"] = False
            database.save_draft(user_id, "confirm_event", draft_data)
            await edit_add_confirmation_message(query, draft_data)
            return

        draft_data["recurring"] = True
        database.save_draft(user_id, "awaiting_recurrence_until", draft_data)
        event_date = parse_date_input(draft_data["date"])
        await query.edit_message_text(
            "Choose the recurrence end date:",
            reply_markup=build_context_calendar_keyboard(user_id, "recur", event_date.year, event_date.month),
        )
        return

    if action in {"frequency", "rtype"}:
        if val not in {"DAILY", "WEEKLY", "MONTHLY", "YEARLY", "WEEKDAYS", "CUSTOM"}:
            await query.edit_message_text("Invalid recurrence choice. Please use /add to start again.")
            return
        draft_data["recurring"] = True
        draft_data["recurrence_type"] = val
        draft_data["recurrence_frequency"] = val
        if val == "CUSTOM":
            draft_data["recurrence_custom_dates"] = []
            database.save_draft(user_id, "custom_recurrence_selection", draft_data)
            event_date = parse_date_input(draft_data["date"])
            await query.edit_message_text(
                "Choose the exact recurrence dates. Selected dates are marked with *. Tap Stop selecting dates when done.",
                reply_markup=build_custom_recurrence_keyboard(user_id, event_date.year, event_date.month),
            )
            return
        database.save_draft(user_id, "confirm_event", draft_data)
        await edit_add_confirmation_message(query, draft_data)
        return

    if action == "cancel":
        database.clear_draft(user_id)
        await query.edit_message_text("Event creation cancelled. You can start again with /add.")
        return

    if action == "edit" and val == "title":
        database.save_draft(user_id, "entered_title", draft_data)
        await query.edit_message_text(
            "Enter the updated event title:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="add:cancel:yes")]]),
        )
        return

    await query.edit_message_text("Unknown action. Please use /add to start again.")


async def overlap_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    parts = query.data.split(":")
    if len(parts) != 3:
        await query.edit_message_text("Invalid overlap action.")
        return

    mode = parts[1]
    action = parts[2]
    draft = database.get_draft(user_id)
    if not draft:
        await query.edit_message_text("This overlap choice expired. Please start again.")
        return

    data = draft.get("data", {})

    if action == "cancel":
        database.clear_draft(user_id)
        await query.edit_message_text("Action cancelled.")
        return

    if mode == "add":
        if action == "proceed":
            data["overlap_override"] = True
            await create_google_event_from_draft(query, user_id, data)
            return

        if action == "change_timing":
            for key in ("period", "start_time", "end_time", "overlap_override"):
                data.pop(key, None)
            database.save_draft(user_id, "period_selection", data)
            period_keyboard = build_period_keyboard(data.get("date"))
            if not period_keyboard:
                database.clear_draft(user_id)
                await query.edit_message_text(
                    "No available time slots are left for that date. "
                    "Please use /add again and choose tomorrow or a future date."
                )
                return
            await query.edit_message_text(
                "Choose a new time period:",
                reply_markup=period_keyboard,
            )
            return

    if mode == "edit":
        if action == "proceed":
            await apply_google_event_edit(query, user_id, data.get("updated", {}), data.get("fields", {}))
            return

        if action == "change_timing":
            selected = data.get("event", {})
            database.save_draft(user_id, "editing_event", selected)
            kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Start time", callback_data="event:editfield:start_time"),
                        InlineKeyboardButton("End time", callback_data="event:editfield:end_time"),
                    ],
                    [InlineKeyboardButton("Cancel", callback_data="event:cancel")],
                ]
            )
            await query.edit_message_text(
                "Choose which timing field to change:",
                reply_markup=kb,
            )
            return

    await query.edit_message_text("Unknown overlap action.")


async def add_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    text = update.message.text.strip()
    draft = database.get_draft(user_id)
    if not draft:
        return  # ignore unrelated texts

    stage = draft.get("stage")
    data = draft.get("data", {})

    if stage == "awaiting_view_date":
        try:
            target_day = parse_date_input(text)
        except Exception:
            await update.message.reply_text(
                "Please use /today, /tomorrow, /other_days, or /back.",
                reply_markup=build_view_keyboard(),
            )
            return
        database.clear_draft(user_id)
        try:
            events = calendar_service.get_events_for_day(target_day)
            message = calendar_service.format_events_for_telegram(events, target_day.isoformat())
        except calendar_service.CalendarSetupError as exc:
            message = "Google Calendar is not ready yet.\n\n" + str(exc)
        except calendar_service.CalendarApiError as exc:
            logger.warning("Google Calendar custom view error: %s", exc)
            message = "I could not read Google Calendar right now. Please try again later."
        await update.message.reply_text(message, reply_markup=build_main_keyboard())
        return

    if stage == "awaiting_task_date":
        try:
            task_day = parse_date_input(text)
        except Exception:
            await update.message.reply_text(
                "Please choose Today, Tomorrow, Other days, or use /back.",
                reply_markup=build_task_date_keyboard(),
            )
            return
        if is_past_date(task_day):
            await update.message.reply_text(
                "Invalid date entered. Please choose today or a future date.",
                reply_markup=build_task_date_keyboard(),
            )
            return
        await open_task_menu_for_date(
            update.message,
            context,
            user_id,
            update.effective_chat.id,
            task_day.isoformat(),
        )
        return

    if stage == "awaiting_task_title":
        if not text:
            await update.message.reply_text(
                "Please type a task before I save it, or use /cancel.",
                reply_markup=build_cancel_keyboard(),
            )
            return
        task_date = data.get("task_date") or today_text()
        try:
            if is_past_date(parse_date_input(task_date)):
                database.clear_draft(user_id)
                await update.message.reply_text(
                    "Invalid date entered. Use /tasks to choose today or a future date.",
                    reply_markup=build_main_keyboard(),
                )
                return
        except Exception:
            task_date = today_text()
        database.add_important_task(user_id, task_date, text)
        database.save_draft(user_id, "task_menu", {"task_date": task_date})
        summary, calendar_warning = await refresh_important_tasks_summary(
            update.message,
            context,
            user_id,
            update.effective_chat.id,
            task_date,
        )
        message = f"Important task saved.\n\n{summary}"
        if calendar_warning:
            message = f"{message}\n\n{calendar_warning}"
        await update.message.reply_text(message, reply_markup=build_task_keyboard())
        return

    if stage == "awaiting_task_edit_title":
        if not text:
            await update.message.reply_text(
                "Please type the updated task text, or use /cancel.",
                reply_markup=build_cancel_keyboard(),
            )
            return
        task_id = data.get("task_id")
        task = database.get_important_task(user_id, task_id) if task_id else None
        if not task or is_past_date(parse_date_input(task["task_date"])):
            database.clear_draft(user_id)
            await update.message.reply_text(
                "Task selection expired. Use /edit_task to start again.",
                reply_markup=build_task_keyboard(),
            )
            return
        task_date = task["task_date"]
        database.update_important_task_title(user_id, task_id, text)
        database.save_draft(user_id, "task_menu", {"task_date": task_date})
        summary, calendar_warning = await refresh_important_tasks_summary(
            update.message,
            context,
            user_id,
            update.effective_chat.id,
            task_date,
        )
        message = f"Important task updated.\n\n{summary}"
        if calendar_warning:
            message = f"{message}\n\n{calendar_warning}"
        await update.message.reply_text(message, reply_markup=build_task_keyboard())
        return

    if stage == "awaiting_pick_date":
        try:
            d = parse_date_input(text)
            if is_past_date(d):
                await update.message.reply_text(
                    "Invalid date entered. Please choose today or a future date.",
                    reply_markup=build_context_calendar_keyboard(user_id, "add"),
                )
                return
            data["date"] = d.isoformat()
            database.save_draft(user_id, "period_selection", data)
            period_keyboard = build_period_keyboard(data["date"])
            if not period_keyboard:
                database.clear_draft(user_id)
                await update.message.reply_text(
                    f"No available time slots left for {data['date']}. "
                    "Please use /add again and choose tomorrow or a future date."
                )
                return
            await update.message.reply_text(
                f"Date set to {d.isoformat()}. Now choose a time period:",
                reply_markup=period_keyboard,
            )
        except Exception:
            await update.message.reply_text(
                "Please choose a date from the calendar.",
                reply_markup=build_context_calendar_keyboard(user_id, "add"),
            )
        return

    if stage == "awaiting_event_date":
        mode = data.get("mode", "edit")
        try:
            target_day = parse_date_input(text)
        except Exception:
            await update.message.reply_text(
                "Please choose a date from the calendar.",
                reply_markup=build_context_calendar_keyboard(user_id, "event_amend"),
            )
            return
        await send_google_events_for_date(update.message, user_id, mode, target_day)
        return

    if stage == "entered_title":
        data["title"] = text
        database.save_draft(user_id, "entered_location", data)
        await update.message.reply_text(
            "Enter location, or use /skip to leave empty.",
            reply_markup=build_skip_cancel_keyboard(),
        )
        return

    if stage == "entered_location":
        data["location"] = text
        database.save_draft(user_id, "entered_notes", data)
        await update.message.reply_text(
            "Enter notes, or use /skip to leave empty.",
            reply_markup=build_skip_cancel_keyboard(),
        )
        return

    if stage == "entered_notes":
        data["notes"] = text
        database.save_draft(user_id, "recurring_selection", data)
        await update.message.reply_text(
            "Should this event repeat?",
            reply_markup=build_recurring_keyboard(False),
        )
        return

    if stage == "awaiting_recurrence_until":
        try:
            recurrence_until = parse_date_input(text)
            event_date = parse_date_input(data["date"])
            if recurrence_until < event_date:
                await update.message.reply_text(
                    "Invalid date entered. Recurrence end date must be on or after the event date.",
                    reply_markup=build_context_calendar_keyboard(user_id, "recur", event_date.year, event_date.month),
                )
                return
        except Exception:
            await update.message.reply_text(
                "Please choose the recurrence end date from the calendar.",
                reply_markup=build_context_calendar_keyboard(user_id, "recur"),
            )
            return

        class _MessageEditAdapter:
            def __init__(self, message):
                self.message = message

            async def edit_message_text(self, text, reply_markup=None):
                await self.message.reply_text(text, reply_markup=reply_markup)

        await continue_recurrence_until_selection(
            _MessageEditAdapter(update.message),
            user_id,
            data,
            recurrence_until,
        )
        return

    if stage == "confirm_event":
        await update.message.reply_text(
            "Please use the confirmation buttons to finish the event creation, or use /cancel.",
            reply_markup=build_cancel_keyboard(),
        )
        return

    # Handle edits started via /amend -> pick field
    if isinstance(stage, str) and stage.startswith("editing_event_field:"):
        # stage format: editing_event_field:fieldname
        parts = stage.split(":", 1)
        field = parts[1] if len(parts) > 1 else None
        if not field:
            await update.message.reply_text("Edit stage invalid. Use /amend to start again.")
            return

        google_event_id = data.get("google_event_id")
        if not google_event_id:
            await update.message.reply_text("No Google Calendar event found to edit. Use /amend to start again.")
            return

        updated_event = dict(data)
        changed_fields = {}
        try:
            if field == "date":
                new_date = parse_date_input(text)
                if is_past_date(new_date):
                    await update.message.reply_text(
                        "Invalid date entered. Please choose today or a future date.",
                        reply_markup=build_context_calendar_keyboard(user_id, "editdate"),
                    )
                    return
                updated_event["date"] = new_date.isoformat()
                changed_fields["date"] = updated_event["date"]
            elif field in {"start_time", "end_time"}:
                updated_event[field] = parse_time_input(text)
                if updated_event["end_time"] <= updated_event["start_time"]:
                    await update.message.reply_text(
                        "Invalid time entered. End time must be after start time, or use /cancel.",
                        reply_markup=build_cancel_keyboard(),
                    )
                    return
                changed_fields[field] = updated_event[field]
            else:
                updated_event[field] = text
                changed_fields[field] = text
        except Exception:
            if field == "date":
                await update.message.reply_text(
                    "Please choose the new date from the calendar.",
                    reply_markup=build_context_calendar_keyboard(user_id, "editdate"),
                )
            elif field in {"start_time", "end_time"}:
                await update.message.reply_text(
                    "Invalid time format. Please send HH:MM, or use /cancel.",
                    reply_markup=build_cancel_keyboard(),
                )
            else:
                await update.message.reply_text(
                    "Invalid value. Please try again, or use /cancel.",
                    reply_markup=build_cancel_keyboard(),
                )
            return

        if field in {"date", "start_time", "end_time"}:
            try:
                conflicts = find_overlapping_events(updated_event, exclude_google_event_id=google_event_id)
            except calendar_service.CalendarSetupError as exc:
                await update.message.reply_text("Google Calendar is not ready for overlap checking.\n\n" + str(exc))
                return
            except calendar_service.CalendarApiError as exc:
                logger.warning("Google Calendar overlap check error: %s", exc)
                await update.message.reply_text("I could not check for overlapping events. Please try again.")
                return

            if conflicts:
                database.save_draft(
                    user_id,
                    "pending_edit_overlap",
                    {"event": data, "updated": updated_event, "fields": changed_fields},
                )
                await update.message.reply_text(
                    format_overlap_message(conflicts),
                    reply_markup=build_overlap_keyboard("edit"),
                )
                return

        try:
            calendar_service.update_event(
                google_event_id,
                build_calendar_update_fields(updated_event, changed_fields),
            )
        except calendar_service.CalendarSetupError as exc:
            await update.message.reply_text(
                "Google Calendar is not ready for editing yet.\n\n" + str(exc)
            )
            return
        except calendar_service.CalendarApiError as exc:
            logger.warning("Google Calendar update error: %s", exc)
            database.clear_draft(user_id)
            await update.message.reply_text("I could not update that Google Calendar event. Please try again.")
            return

        local_event_id = data.get("local_event_id")
        if local_event_id:
            database.update_event(local_event_id, changed_fields)
        database.clear_draft(user_id)
        changed_text = "\n".join(f"{key}: {value}" for key, value in changed_fields.items())
        await update.message.reply_text("Event updated in Google Calendar.\n\n" + changed_text)
        return



async def today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show Google Calendar events for today."""
    draft = database.get_draft(update.effective_user.id)
    if draft and draft.get("stage") == "awaiting_view_date":
        database.clear_draft(update.effective_user.id)
    await show_google_calendar_day(update, singapore_today(), "today")


async def tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show Google Calendar events for tomorrow."""
    draft = database.get_draft(update.effective_user.id)
    if draft and draft.get("stage") == "awaiting_view_date":
        database.clear_draft(update.effective_user.id)
    await show_google_calendar_day(update, singapore_today() + timedelta(days=1), "tomorrow")


async def show_google_calendar_day(update: Update, target_day, day_label: str) -> None:
    await send_google_calendar_day(update.message, target_day, day_label)


def build_google_calendar_day_text(target_day, day_label: str) -> str:
    try:
        events = calendar_service.get_events_for_day(target_day)
        return calendar_service.format_events_for_telegram(events, day_label)
    except calendar_service.CalendarSetupError as exc:
        return (
            "Google Calendar is not ready yet.\n\n"
            f"{exc}\n\n"
            "Local events are still available with /local_today and /local_tomorrow."
        )
    except calendar_service.CalendarApiError as exc:
        logger.warning("Google Calendar API error: %s", exc)
        return (
            "I could not read Google Calendar right now. "
            "Please try again later, or use /local_today and /local_tomorrow for local events."
        )


async def send_google_calendar_day(target, target_day, day_label: str, reply_markup=None) -> None:
    message = build_google_calendar_day_text(target_day, day_label)
    await target.reply_text(message, reply_markup=reply_markup)


def build_daily_itinerary_message(user_id: int, target_day) -> str:
    date_text = target_day.isoformat()
    calendar_text = build_google_calendar_day_text(target_day, "today")
    task_summary = format_important_tasks_summary(
        date_text,
        database.list_important_tasks(user_id, date_text),
    )
    return (
        f"Good morning! Here is your itinerary for {date_text}.\n\n"
        f"{calendar_text}\n\n"
        f"{task_summary}"
    )


async def send_5am_itinerary_to_chat(context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int) -> None:
    await context.bot.send_message(
        chat_id=chat_id,
        text=build_daily_itinerary_message(user_id, singapore_today()),
    )


async def send_8pm_review_to_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    await context.bot.send_message(
        chat_id=chat_id,
        text="Have you reviewed tomorrow’s itinerary?",
        reply_markup=build_tomorrow_review_keyboard(),
    )


async def send_5am_itineraries_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    for bot_user in database.list_bot_users():
        try:
            await send_5am_itinerary_to_chat(context, bot_user["user_id"], bot_user["chat_id"])
        except TelegramError as exc:
            logger.info("Could not send 5am itinerary to chat %s: %s", bot_user["chat_id"], exc)


async def send_8pm_reviews_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    for bot_user in database.list_bot_users():
        try:
            await send_8pm_review_to_chat(context, bot_user["chat_id"])
        except TelegramError as exc:
            logger.info("Could not send 8pm review to chat %s: %s", bot_user["chat_id"], exc)

async def local_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show locally stored events for today (Phase 2)."""
    user_id = update.effective_user.id
    date_str = singapore_today().isoformat()
    events = database.list_events(user_id, date_str)
    if not events:
        await update.message.reply_text(
            "No locally saved events found for today. Use /add to create one."
        )
        return

    lines = ["Today’s locally stored events:"]
    for event in events:
        lines.append(
            f"- {event['start_time']}–{event['end_time']}: {event['title']}"
            + (f" @ {event['location']}" if event["location"] else "")
        )
    await update.message.reply_text("\n".join(lines))


async def local_tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show locally stored events for tomorrow (Phase 2)."""
    user_id = update.effective_user.id
    date_str = (singapore_today() + timedelta(days=1)).isoformat()
    events = database.list_events(user_id, date_str)
    if not events:
        await update.message.reply_text(
            "No locally saved events found for tomorrow. Use /add to create one."
        )
        return

    lines = ["Tomorrow’s locally stored events:"]
    for event in events:
        lines.append(
            f"- {event['start_time']}–{event['end_time']}: {event['title']}"
            + (f" @ {event['location']}" if event["location"] else "")
        )
    await update.message.reply_text("\n".join(lines))


def build_events_keyboard(user_id: int) -> Optional[InlineKeyboardMarkup]:
    events = database.list_events(user_id, singapore_today().isoformat())
    if not events:
        return None
    buttons = []
    for ev in events:
        label = f"{ev['start_time']}-{ev['end_time']} {ev['title'][:30]}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"event:select:{ev['id']}")])
        buttons.append([
            InlineKeyboardButton("Edit", callback_data=f"event:edit:{ev['id']}"),
            InlineKeyboardButton("Delete", callback_data=f"event:delete:{ev['id']}"),
        ])
    buttons.append([InlineKeyboardButton("Cancel", callback_data="event:cancel")])
    return InlineKeyboardMarkup(buttons)


async def amend_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask which date to load for editing or deleting Google Calendar events."""
    user_id = update.effective_user.id
    database.save_draft(user_id, "event_date_selection", {"mode": "amend"})
    await update.message.reply_text(
        "Choose which date to amend events from:",
        reply_markup=build_event_date_keyboard("amend"),
    )


async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Backward-compatible alias for /amend."""
    await amend_command(update, context)


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Backward-compatible alias for /amend."""
    await amend_command(update, context)


async def event_date_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    parts = query.data.split(":")
    if len(parts) < 3:
        await query.edit_message_text("Invalid date selection.")
        return

    mode = parts[1]
    val = parts[2]

    if mode == "cancel":
        database.clear_draft(user_id)
        await query.edit_message_text("Action cancelled.")
        return

    if val == "today":
        target_day = singapore_today()
    elif val == "tomorrow":
        target_day = singapore_today() + timedelta(days=1)
    elif val == "pick":
        database.save_draft(user_id, "awaiting_event_date", {"mode": mode})
        await query.edit_message_text(
            f"Choose which date to {event_mode_label(mode)} events from:",
            reply_markup=build_context_calendar_keyboard(user_id, "event_amend"),
        )
        return
    else:
        await query.edit_message_text("Invalid date selection.")
        return

    await edit_google_events_message_text(query, user_id, mode, target_day)


async def recurring_scope_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    parts = query.data.split(":")
    if len(parts) != 3:
        await query.edit_message_text("Invalid recurring event action.")
        return

    mode = parts[1]
    scope = parts[2]
    draft = database.get_draft(user_id)
    if not draft or draft.get("stage") != "recurring_scope_selection":
        await query.edit_message_text("This recurring event choice expired. Use /amend to start again.")
        return

    selected = draft.get("data", {}).get("event", {})
    if not selected:
        await query.edit_message_text("Event selection expired. Use /amend to start again.")
        return

    if scope == "cancel":
        database.clear_draft(user_id)
        await query.edit_message_text("Action cancelled.")
        return

    if mode == "delete":
        if scope == "single":
            await delete_selected_google_event(query, user_id, selected, delete_series=False)
            return
        if scope == "series":
            await delete_selected_google_event(query, user_id, selected, delete_series=True)
            return

    if mode == "edit":
        if scope == "single":
            selected["edit_scope"] = "single"
        elif scope == "series":
            try:
                selected = replace_with_series_master_timing(selected)
            except calendar_service.CalendarSetupError as exc:
                await query.edit_message_text("Google Calendar is not ready for editing yet.\n\n" + str(exc))
                return
            except calendar_service.CalendarApiError as exc:
                logger.warning("Google Calendar recurring series lookup error: %s", exc)
                await query.edit_message_text("I could not load the recurring series to edit. Please try again.")
                return
        else:
            await query.edit_message_text("Invalid recurring edit choice.")
            return

        database.save_draft(user_id, "editing_event", selected)
        scope_text = "this occurrence" if scope == "single" else "the whole recurring series"
        await query.edit_message_text(
            f"Editing {scope_text}. Which field would you like to edit?",
            reply_markup=build_edit_fields_keyboard(selected),
        )
        return

    await query.edit_message_text("Unknown recurring event action.")


async def calendar_picker_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    parts = query.data.split(":")
    if len(parts) < 2 or parts[1] == "noop":
        return
    target = parts[1]
    if target not in {"view", "task", "add", "event_amend", "recur", "editdate"}:
        await query.edit_message_text("Invalid calendar choice.")
        return
    if len(parts) == 3 and parts[2] == "cancel":
        database.clear_draft(user_id)
        await query.edit_message_text("Calendar selection cancelled.")
        return
    if len(parts) != 4:
        await query.edit_message_text("Invalid calendar choice.")
        return

    action = parts[2]
    value = parts[3]
    if action == "cancel":
        database.clear_draft(user_id)
        await query.edit_message_text("Calendar selection cancelled.")
        return

    if action == "month":
        try:
            year_text, month_text = value.split("-", 1)
            year = int(year_text)
            month = int(month_text)
        except ValueError:
            await query.edit_message_text("Invalid calendar month.")
            return
        await query.edit_message_text(
            "Choose a date:",
            reply_markup=build_context_calendar_keyboard(user_id, target, year, month),
        )
        return

    if action != "day":
        await query.edit_message_text("Invalid calendar choice.")
        return

    try:
        selected_day = parse_date_input(value)
    except Exception:
        await query.edit_message_text("Invalid calendar date.")
        return

    if target == "task":
        if is_past_date(selected_day):
            await query.edit_message_text(
                "Invalid date entered. Please choose today or a future date.",
                reply_markup=build_context_calendar_keyboard(user_id, "task"),
            )
            return
        await query.edit_message_text(f"Selected task date: {selected_day.isoformat()}")
        await open_task_menu_for_date(
            query.message,
            context,
            user_id,
            chat_id,
            selected_day.isoformat(),
        )
        return

    if target == "add":
        draft = database.get_draft(user_id) or {"data": {}}
        await continue_add_date_selection(query, user_id, draft.get("data", {}), selected_day)
        return

    if target == "event_amend":
        database.save_draft(user_id, "event_date_selection", {"mode": "amend"})
        await edit_google_events_message_text(query, user_id, "amend", selected_day)
        return

    if target == "recur":
        draft = database.get_draft(user_id)
        data = draft.get("data", {}) if draft else {}
        await continue_recurrence_until_selection(query, user_id, data, selected_day)
        return

    if target == "editdate":
        draft = database.get_draft(user_id)
        data = draft.get("data", {}) if draft else {}
        await continue_event_date_edit_selection(query, user_id, data, selected_day)
        return

    database.clear_draft(user_id)
    await query.edit_message_text(f"Selected date: {selected_day.isoformat()}")
    await send_google_calendar_day(query.message, selected_day, selected_day.isoformat(), build_main_keyboard())


async def custom_recurrence_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    parts = query.data.split(":")
    draft = database.get_draft(user_id)
    if not draft or draft.get("stage") != "custom_recurrence_selection":
        await query.edit_message_text("Custom recurrence selection expired. Please use /add to start again.")
        return
    data = draft.get("data", {})

    if len(parts) < 2:
        await query.edit_message_text("Invalid custom recurrence choice.")
        return
    action = parts[1]

    if action == "cancel":
        database.clear_draft(user_id)
        await query.edit_message_text("Event creation cancelled. You can start again with /add.")
        return

    if action == "month" and len(parts) == 3:
        try:
            year_text, month_text = parts[2].split("-", 1)
            year = int(year_text)
            month = int(month_text)
        except ValueError:
            await query.edit_message_text("Invalid calendar month.")
            return
        await query.edit_message_text(
            "Choose the exact recurrence dates. Selected dates are marked with *. Tap Stop selecting dates when done.",
            reply_markup=build_custom_recurrence_keyboard(user_id, year, month),
        )
        return

    if action == "day" and len(parts) == 3:
        try:
            selected_day = parse_date_input(parts[2])
            event_date = parse_date_input(data["date"])
            until_date = parse_date_input(data["recurrence_until"])
        except Exception:
            await query.edit_message_text("Invalid recurrence date.")
            return
        if selected_day < max(singapore_today(), event_date) or selected_day > until_date:
            await query.edit_message_text(
                "Invalid date entered. Please choose a date within the recurrence period.",
                reply_markup=build_custom_recurrence_keyboard(user_id, selected_day.year, selected_day.month),
            )
            return
        selected_dates = set(data.get("recurrence_custom_dates") or [])
        date_text = selected_day.isoformat()
        if date_text in selected_dates:
            selected_dates.remove(date_text)
        else:
            selected_dates.add(date_text)
        data["recurrence_custom_dates"] = sorted(selected_dates)
        database.save_draft(user_id, "custom_recurrence_selection", data)
        await query.edit_message_text(
            "Choose the exact recurrence dates. Selected dates are marked with *. Tap Stop selecting dates when done.",
            reply_markup=build_custom_recurrence_keyboard(user_id, selected_day.year, selected_day.month),
        )
        return

    if action == "done":
        selected_dates = sorted(set(data.get("recurrence_custom_dates") or []))
        event_date_text = data.get("date")
        extra_dates = [day for day in selected_dates if day != event_date_text]
        if not extra_dates:
            await query.edit_message_text(
                "Please select at least one extra recurrence date before stopping.",
                reply_markup=build_custom_recurrence_keyboard(user_id),
            )
            return
        data["recurrence_custom_dates"] = selected_dates
        data["recurrence_type"] = "CUSTOM"
        data["recurrence_frequency"] = "CUSTOM"
        database.save_draft(user_id, "confirm_event", data)
        await edit_add_confirmation_message(query, data)
        return

    await query.edit_message_text("Invalid custom recurrence choice.")


async def task_date_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    parts = query.data.split(":")
    if len(parts) != 2:
        await query.edit_message_text("Invalid task date choice.")
        return

    choice = parts[1]
    if choice == "cancel":
        database.clear_draft(user_id)
        await query.edit_message_text("Task date selection cancelled.")
        return
    if choice == "today":
        task_date = today_text()
    elif choice == "tomorrow":
        task_date = tomorrow_text()
    elif choice == "other":
        await query.edit_message_text(
            "Choose a task date:",
            reply_markup=build_context_calendar_keyboard(user_id, "task"),
        )
        return
    else:
        await query.edit_message_text("Invalid task date choice.")
        return

    await query.edit_message_text(f"Selected task date: {task_date}")
    await open_task_menu_for_date(
        query.message,
        context,
        user_id,
        chat_id,
        task_date,
    )


async def task_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    parts = query.data.split(":")
    if len(parts) < 2:
        await query.edit_message_text("Invalid task action.")
        return

    action = parts[1]
    if action == "cancel":
        await query.edit_message_text("Task action cancelled.")
        return

    if len(parts) != 3:
        await query.edit_message_text("Invalid task action.")
        return

    try:
        task_id = int(parts[2])
    except ValueError:
        await query.edit_message_text("Invalid task selection.")
        return

    task = database.get_important_task(user_id, task_id)
    if not task or is_past_date(parse_date_input(task["task_date"])):
        await query.edit_message_text("Task selection expired. Use /tasks to start again.")
        return
    task_date = task["task_date"]

    if action == "done":
        database.mark_important_task_done(user_id, task_id)
        database.save_draft(user_id, "task_menu", {"task_date": task_date})
        summary, calendar_warning = await refresh_important_tasks_summary(
            query.message,
            context,
            user_id,
            chat_id,
            task_date,
        )
        message = f"Marked done: {task['title']}\n\n{summary}"
        if calendar_warning:
            message = f"{message}\n\n{calendar_warning}"
        await query.edit_message_text(message)
        return

    if action == "edit":
        database.save_draft(user_id, "awaiting_task_edit_title", {"task_id": task_id, "task_date": task_date})
        await query.edit_message_text(
            f"Type the updated task text:\n\n{task['title']}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="task:cancel")]]),
        )
        return

    if action == "delete":
        await query.edit_message_text(
            f"Delete this important task?\n\n{task['title']}",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Confirm delete", callback_data=f"task:confirm_delete:{task_id}")],
                    [InlineKeyboardButton("Cancel", callback_data="task:cancel")],
                ]
            ),
        )
        return

    if action == "confirm_delete":
        database.delete_important_task(user_id, task_id)
        database.save_draft(user_id, "task_menu", {"task_date": task_date})
        summary, calendar_warning = await refresh_important_tasks_summary(
            query.message,
            context,
            user_id,
            chat_id,
            task_date,
        )
        message = f"Deleted important task: {task['title']}\n\n{summary}"
        if calendar_warning:
            message = f"{message}\n\n{calendar_warning}"
        await query.edit_message_text(message)
        return

    await query.edit_message_text("Unknown task action.")


async def event_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data  # e.g. event:delete:123
    parts = data.split(":")
    if len(parts) < 2:
        await query.edit_message_text("Invalid action")
        return
    action = parts[1]

    if action == "cancel":
        database.clear_draft(user_id)
        await query.edit_message_text("Action cancelled.")
        return

    if action == "select" and len(parts) >= 3:
        selected = get_selected_calendar_event(user_id, parts[2])
        if not selected:
            await query.edit_message_text("Event selection expired. Use /amend to start again.")
            return
        await query.edit_message_text("Selected event:\n\n" + format_event_summary(selected))
        return

    if action == "delete" and len(parts) >= 3:
        selected = get_selected_calendar_event(user_id, parts[2])
        if not selected:
            await query.edit_message_text("Event selection expired. Use /amend to start again.")
            return

        if is_recurring_calendar_event(selected):
            database.save_draft(user_id, "recurring_scope_selection", {"mode": "delete", "event": selected})
            await query.edit_message_text(
                "This is a recurring event. What do you want to delete?",
                reply_markup=build_recurring_scope_keyboard("delete"),
            )
            return

        database.save_draft(user_id, "pending_event_delete", selected)
        await query.edit_message_text(
            "Delete this event?\n\n" + format_event_summary(selected),
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Confirm delete", callback_data=f"event:confirm_delete:{parts[2]}")],
                    [InlineKeyboardButton("Cancel", callback_data="event:cancel")],
                ]
            ),
        )
        return

    if action == "confirm_delete" and len(parts) >= 3:
        selected = get_selected_calendar_event(user_id, parts[2])
        if not selected:
            draft = database.get_draft(user_id)
            selected = draft.get("data", {}) if draft and draft.get("stage") == "pending_event_delete" else None
        if not selected:
            await query.edit_message_text("Event selection expired. Use /amend to start again.")
            return
        await delete_selected_google_event(query, user_id, selected)
        return

    if action == "edit" and len(parts) >= 3:
        selected = get_selected_calendar_event(user_id, parts[2])
        if not selected:
            await query.edit_message_text("Event selection expired. Use /amend to start again.")
            return

        if is_recurring_calendar_event(selected):
            database.save_draft(user_id, "recurring_scope_selection", {"mode": "edit", "event": selected})
            await query.edit_message_text(
                "This is a recurring event. What do you want to edit?",
                reply_markup=build_recurring_scope_keyboard("edit"),
            )
            return

        database.save_draft(user_id, "editing_event", selected)
        await query.edit_message_text(
            "Which field would you like to edit in Google Calendar? (Title, Location, Notes)",
            reply_markup=build_edit_fields_keyboard(selected),
        )
        return

    if action == "editfield" and len(parts) >= 3:
        field = parts[2]
        if field not in {"title", "date", "start_time", "end_time", "location", "notes"}:
            await query.edit_message_text("That field cannot be edited here.")
            return
        draft = database.get_draft(user_id)
        if not draft or draft.get("stage") != "editing_event":
            await query.edit_message_text("Event selection expired. Use /amend to start again.")
            return
        selected = draft.get("data", {})
        if selected.get("all_day") and field in {"start_time", "end_time"}:
            await query.edit_message_text("Editing all-day event times is not supported yet.")
            return
        database.save_draft(user_id, f"editing_event_field:{field}", selected)
        if field == "date":
            await query.edit_message_text(
                "Choose the new event date:",
                reply_markup=build_context_calendar_keyboard(user_id, "editdate"),
            )
            return
        elif field in {"start_time", "end_time"}:
            prompt = f"Please send the new {field.replace('_', ' ')} in HH:MM format."
        else:
            prompt = f"Please send the new value for {field} as a text message."
        await query.edit_message_text(
            prompt,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="event:cancel")]]),
        )
        return

    await query.edit_message_text("Unknown event action. Use /amend to start again.")


async def review_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    review_date = tomorrow_text()
    parts = query.data.split(":")
    if len(parts) != 2:
        await query.edit_message_text("Invalid review action.")
        return

    action = parts[1]
    if action == "view_tomorrow":
        await send_google_calendar_day(query.message, singapore_today() + timedelta(days=1), "tomorrow")
        return

    if action == "add_event":
        await query.message.reply_text("Sure. Let’s add an event for your plans.")
        await send_add_event_date_prompt(query.message, user_id)
        return

    if action == "no_plans":
        database.save_daily_review(user_id, chat_id, review_date, "no_plans")
        await query.edit_message_text(f"Saved. {review_date} is marked as no plans.")
        return

    if action == "done":
        database.save_daily_review(user_id, chat_id, review_date, "reviewed")
        await query.edit_message_text(f"Saved. {review_date} is marked as reviewed.")
        return

    await query.edit_message_text("Unknown review action.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors caused by updates."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text(
            "Sorry, I ran into an error while processing your request. "
            "Please try again or contact the bot owner."
        )


def register_scheduled_jobs(app) -> None:
    """Register daily reminders once when the bot process starts."""
    if not app.job_queue:
        logger.warning(
            "JobQueue is not available. Install python-telegram-bot with the job-queue extra."
        )
        return

    for job_name in ("daily_5am_itinerary", "daily_8pm_review"):
        for existing_job in app.job_queue.get_jobs_by_name(job_name):
            existing_job.schedule_removal()

    app.job_queue.run_daily(
        send_5am_itineraries_job,
        time=time(hour=5, minute=0, tzinfo=LOCAL_TZ),
        name="daily_5am_itinerary",
    )
    app.job_queue.run_daily(
        send_8pm_reviews_job,
        time=time(hour=20, minute=0, tzinfo=LOCAL_TZ),
        name="daily_8pm_review",
    )
    logger.info("Scheduled daily reminders for 05:00 and 20:00 Asia/Singapore.")


def main() -> None:
    """Start the Telegram bot."""
    if (
        not TELEGRAM_BOT_TOKEN
        or TELEGRAM_BOT_TOKEN.strip() == ""
        or "your_bot_token_here" in TELEGRAM_BOT_TOKEN
    ):
        logger.error(
            "Missing or placeholder TELEGRAM_BOT_TOKEN in environment. "
            "Create a .env file with TELEGRAM_BOT_TOKEN=your_real_token_here."
        )
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is required and must be set to a valid bot token."
        )

    # Ensure DB is ready for Phase 2 drafts
    database.init_db()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("connect_calendar", connect_calendar))
    app.add_handler(CommandHandler("add", add_event))
    app.add_handler(CommandHandler("amend", amend_command))
    app.add_handler(CommandHandler("view", view_command))
    app.add_handler(CommandHandler("other_days", other_days_command))
    app.add_handler(CommandHandler("tasks", tasks_command))
    app.add_handler(CommandHandler("add_task", add_task_command))
    app.add_handler(CommandHandler("done_task", done_task_command))
    app.add_handler(CommandHandler("edit_task", edit_task_command))
    app.add_handler(CommandHandler("delete_task", delete_task_command))
    app.add_handler(CommandHandler("refresh_tasks", refresh_tasks_command))
    app.add_handler(CommandHandler("back", back_command))
    app.add_handler(CommandHandler("skip", skip_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CallbackQueryHandler(add_button_handler, pattern=r"^add:"))
    app.add_handler(CallbackQueryHandler(overlap_callback_handler, pattern=r"^overlap:"))
    app.add_handler(CallbackQueryHandler(event_date_callback_handler, pattern=r"^eventdate:"))
    app.add_handler(CallbackQueryHandler(recurring_scope_callback_handler, pattern=r"^recurring:"))
    app.add_handler(CallbackQueryHandler(custom_recurrence_callback_handler, pattern=r"^customrecur:"))
    app.add_handler(CallbackQueryHandler(calendar_picker_callback_handler, pattern=r"^cal:"))
    app.add_handler(CallbackQueryHandler(task_date_callback_handler, pattern=r"^taskdate:"))
    app.add_handler(CallbackQueryHandler(task_callback_handler, pattern=r"^task:"))
    app.add_handler(CallbackQueryHandler(review_callback_handler, pattern=r"^review:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, add_text_handler))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("tomorrow", tomorrow))
    app.add_handler(CommandHandler("gcal_today", today))
    app.add_handler(CommandHandler("gcal_tomorrow", tomorrow))
    app.add_handler(CommandHandler("local_today", local_today))
    app.add_handler(CommandHandler("local_tomorrow", local_tomorrow))

    app.add_error_handler(error_handler)

    # Backward-compatible event management aliases
    app.add_handler(CommandHandler("delete", delete_command))
    app.add_handler(CommandHandler("edit", edit_command))
    app.add_handler(CallbackQueryHandler(event_callback_handler, pattern=r"^event:"))

    register_scheduled_jobs(app)
    logger.info("Bot started with Google Calendar sync enabled. Waiting for commands...")
    app.run_polling()


if __name__ == "__main__":
    main()
