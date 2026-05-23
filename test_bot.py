"""
Comprehensive test suite for the Telegram Itinerary Bot.
Tests database functions, utility functions, and bot handlers.
"""

import sys
import os
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import asyncio
from unittest.mock import AsyncMock, Mock, MagicMock, patch

# Add the current directory to path
sys.path.insert(0, str(Path(__file__).parent))

import database
import bot
import calendar_service
from bot import (
    format_event_summary,
    get_period_time_range,
    get_day_end_time_options,
    build_period_keyboard,
    build_main_keyboard,
    build_task_keyboard,
    build_view_keyboard,
    format_important_tasks_summary,
    build_button_grid,
    build_confirmation_keyboard,
    round_up_to_next_quarter,
)

# Test database setup
TEST_DB_PATH = Path(__file__).parent / "test_bot_data.db"


def setup_test_db():
    """Create a fresh test database."""
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    
    # Temporarily patch the DB_PATH
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        database.init_db()
    print("✓ Test database initialized")


def cleanup_test_db():
    """Remove test database after testing."""
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    print("✓ Test database cleaned up")


def reply_keyboard_labels(markup):
    labels = []
    for row in markup.keyboard:
        for button in row:
            labels.append(getattr(button, "text", button))
    return labels


def reply_keyboard_rows(markup):
    return [
        [getattr(button, "text", button) for button in row]
        for row in markup.keyboard
    ]


# ============================================================================
# DATABASE TESTS
# ============================================================================

def test_database_functions():
    """Test all database functions."""
    print("\n" + "="*70)
    print("DATABASE FUNCTION TESTS")
    print("="*70)
    
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        # Test 1: Save and retrieve draft
        print("\n1. Testing save_draft() and get_draft()...")
        user_id = 12345
        stage = "date_selection"
        data = {"title": "Test Event", "date": "2026-05-22"}
        
        database.save_draft(user_id, stage, data)
        retrieved = database.get_draft(user_id)
        
        assert retrieved is not None, "Draft should not be None"
        assert retrieved["stage"] == stage, f"Expected stage {stage}, got {retrieved['stage']}"
        assert retrieved["data"]["title"] == data["title"], "Draft data mismatch"
        print(f"   ✓ Draft saved and retrieved successfully")
        print(f"     Stage: {retrieved['stage']}")
        print(f"     Data: {retrieved['data']}")
        
        # Test 2: Clear draft
        print("\n2. Testing clear_draft()...")
        database.clear_draft(user_id)
        cleared = database.get_draft(user_id)
        assert cleared is None, "Draft should be cleared"
        print("   ✓ Draft cleared successfully")
        
        # Test 3: Save and retrieve event
        print("\n3. Testing save_event() and get_event()...")
        event_data = {
            "google_event_id": "google-1",
            "title": "Team Meeting",
            "date": "2026-05-22",
            "start_time": "10:00",
            "end_time": "11:00",
            "location": "Conference Room A",
            "notes": "Discuss Q2 goals",
        }
        
        event_id = database.save_event(user_id, event_data)
        assert event_id > 0, "Event ID should be positive"
        print(f"   ✓ Event saved with ID: {event_id}")
        
        retrieved_event = database.get_event(user_id, event_id)
        assert retrieved_event is not None, "Event should be retrieved"
        assert retrieved_event["title"] == event_data["title"], "Event title mismatch"
        assert retrieved_event["google_event_id"] == event_data["google_event_id"], "Google event ID mismatch"
        assert retrieved_event["location"] == event_data["location"], "Event location mismatch"
        print(f"   ✓ Event retrieved successfully")
        print(f"     Title: {retrieved_event['title']}")
        print(f"     Location: {retrieved_event['location']}")
        print(f"     Time: {retrieved_event['start_time']} - {retrieved_event['end_time']}")
        
        # Test 4: List events
        print("\n4. Testing list_events()...")
        # Save another event
        event_data2 = {
            "google_event_id": "google-2",
            "title": "Lunch Meeting",
            "date": "2026-05-22",
            "start_time": "12:00",
            "end_time": "13:00",
            "location": "Cafe",
            "notes": "Lunch with client",
        }
        event_id2 = database.save_event(user_id, event_data2)
        
        events = database.list_events(user_id, "2026-05-22")
        assert len(events) == 2, f"Expected 2 events, got {len(events)}"
        assert events[0]["start_time"] == "10:00", "Events should be sorted by start time"
        print(f"   ✓ Found {len(events)} events for 2026-05-22")
        for ev in events:
            print(f"     - {ev['start_time']}: {ev['title']}")
        
        # Test 5: Update event
        print("\n5. Testing update_event()...")
        database.update_event(event_id, {"location": "Updated Room", "notes": "Updated notes"})
        updated = database.get_event(user_id, event_id)
        assert updated["location"] == "Updated Room", "Location update failed"
        assert updated["notes"] == "Updated notes", "Notes update failed"
        print("   ✓ Event updated successfully")
        print(f"     New location: {updated['location']}")
        print(f"     New notes: {updated['notes']}")
        
        # Test 6: Delete event
        print("\n6. Testing delete_event()...")
        database.delete_event(event_id2)
        deleted = database.get_event(user_id, event_id2)
        assert deleted is None, "Event should be deleted"
        remaining = database.list_events(user_id, "2026-05-22")
        assert len(remaining) == 1, "Should have 1 remaining event"
        print("   ✓ Event deleted successfully")
        print(f"     Remaining events: {len(remaining)}")

        # Test 7: Important task lifecycle
        print("\n7. Testing important task lifecycle...")
        task_id = database.add_important_task(user_id, "2026-05-22", "Submit report")
        tasks = database.list_important_tasks(user_id, "2026-05-22")
        assert len(tasks) == 1, "Should have one important task"
        assert tasks[0]["status"] == "pending", "New task should be pending"
        retrieved_task = database.get_important_task(user_id, task_id)
        assert retrieved_task["title"] == "Submit report", "Task title mismatch"

        database.mark_important_task_done(user_id, task_id)
        done_task = database.get_important_task(user_id, task_id)
        assert done_task["status"] == "done", "Task should be marked done"
        assert done_task["completed_at"] is not None, "Done task should have completed timestamp"

        database.update_important_task_title(user_id, task_id, "Submit updated report")
        updated_task = database.get_important_task(user_id, task_id)
        assert updated_task["title"] == "Submit updated report", "Task title should be editable"

        database.delete_important_task(user_id, task_id)
        tasks = database.list_important_tasks(user_id, "2026-05-22")
        assert tasks == [], "Deleted task should not be listed"
        print("   ✓ Important tasks can be added, listed, marked done, and deleted")

        # Test 8: Task pin storage
        print("\n8. Testing task pin storage...")
        database.save_task_pin(user_id, 999, "2026-05-22", 123, "calendar-task-1")
        task_pin = database.get_task_pin(user_id, 999, "2026-05-22")
        assert task_pin["pinned_message_id"] == 123, "Pinned message ID mismatch"
        assert task_pin["google_calendar_event_id"] == "calendar-task-1", "Calendar task event ID mismatch"
        database.update_task_pin_google_event_id(user_id, 999, "2026-05-22", None)
        task_pin = database.get_task_pin(user_id, 999, "2026-05-22")
        assert task_pin["google_calendar_event_id"] is None, "Calendar task event ID should be cleared"
        database.save_task_pin(user_id, 999, "2026-05-21", 122, "calendar-task-old")
        old_pins = database.list_task_pins_before(user_id, 999, "2026-05-22")
        assert len(old_pins) == 1 and old_pins[0]["pinned_message_id"] == 122, "Old task pin should be listed"
        print("   ✓ Task pin metadata is saved and updated")

        # Test 9: Bot user storage
        print("\n9. Testing bot user storage...")
        database.save_bot_user(user_id, 999)
        database.save_bot_user(user_id, 999)
        bot_users = database.list_bot_users()
        matching_users = [
            bot_user for bot_user in bot_users
            if bot_user["user_id"] == user_id and bot_user["chat_id"] == 999
        ]
        assert len(matching_users) == 1, "Bot user should be upserted once"
        print("   ✓ Bot users can be saved for scheduled messages")

        # Test 10: Daily review status
        print("\n10. Testing daily review status...")
        database.save_daily_review(user_id, 999, "2026-05-23", "reviewed")
        review = database.get_daily_review(user_id, 999, "2026-05-23")
        assert review["status"] == "reviewed", "Review should be saved"
        database.save_daily_review(user_id, 999, "2026-05-23", "no_plans")
        review = database.get_daily_review(user_id, 999, "2026-05-23")
        assert review["status"] == "no_plans", "Review status should be updated"
        print("   ✓ Daily review statuses can be saved and updated")


# ============================================================================
# UTILITY FUNCTION TESTS
# ============================================================================

def test_utility_functions():
    """Test all utility functions."""
    print("\n" + "="*70)
    print("UTILITY FUNCTION TESTS")
    print("="*70)
    
    # Test 1: format_event_summary
    print("\n1. Testing format_event_summary()...")
    event_data = {
        "title": "Team Standup",
        "date": "2026-05-22",
        "start_time": "09:00",
        "end_time": "09:30",
        "location": "Video Call",
        "notes": "Daily sync",
    }
    
    summary = format_event_summary(event_data)
    assert "Team Standup" in summary, "Summary should contain title"
    assert "09:00" in summary, "Summary should contain start time"
    assert "Video Call" in summary, "Summary should contain location"
    print("   ✓ Event summary formatted correctly")
    print("   Summary:")
    for line in summary.split("\n"):
        print(f"     {line}")
    
    # Test 2: get_period_time_range for start times
    print("\n2. Testing get_period_time_range() for start times...")
    periods = ["early", "morning", "afternoon", "evening"]
    for period in periods:
        times = get_period_time_range(period, for_start=True)
        assert len(times) > 0, f"Should have times for {period}"
        assert all(":" in t for t in times), "All times should be in HH:MM format"
        print(f"   ✓ {period.capitalize()}: {len(times)} start times available")
        print(f"     Range: {times[0]} - {times[-1]}")
    
    # Test 3: get_period_time_range for end times
    print("\n3. Testing get_period_time_range() for end times...")
    for period in periods:
        times = get_period_time_range(period, for_start=False)
        assert len(times) > 0, f"Should have times for {period}"
        print(f"   ✓ {period.capitalize()}: {len(times)} end times available")
        print(f"     Range: {times[0]} - {times[-1]}")
    
    # Test 4: current-day time filtering
    print("\n4. Testing current-day time filtering...")
    assert round_up_to_next_quarter(datetime(2026, 5, 22, 15, 14, tzinfo=bot.LOCAL_TZ)) == "15:15"
    assert round_up_to_next_quarter(datetime(2026, 5, 22, 15, 15, tzinfo=bot.LOCAL_TZ)) == "15:15"
    assert round_up_to_next_quarter(datetime(2026, 5, 22, 23, 59, tzinfo=bot.LOCAL_TZ)) is None

    morning_after_315 = get_period_time_range("morning", for_start=True, min_start_time="15:15")
    afternoon_after_315 = get_period_time_range("afternoon", for_start=True, min_start_time="15:15")
    assert morning_after_315 == [], "Morning should be unavailable after 15:15"
    assert afternoon_after_315[0] == "15:15", "Afternoon should start at the next valid slot"
    assert "15:00" not in afternoon_after_315, "Past afternoon slots should be hidden"

    filtered_keyboard = build_period_keyboard(min_start_time="15:15")
    keyboard_labels = [button.text for row in filtered_keyboard.inline_keyboard for button in row]
    assert "Morning" not in keyboard_labels, "Passed periods should be hidden"
    assert "Afternoon" in keyboard_labels, "Current period should stay visible when it has future slots"
    assert "Cancel" in keyboard_labels, "Active period selection should include Cancel"

    end_times_after_315 = get_day_end_time_options("15:15")
    assert "15:00" not in end_times_after_315, "End time cannot be before start"
    assert "18:00" in end_times_after_315, "Afternoon starts should allow evening end times"
    print("   ✓ Today start-time options hide passed periods and slots")

    # Test 5: build_button_grid
    print("\n5. Testing build_button_grid()...")
    items = ["10:00", "10:15", "10:30", "10:45", "11:00"]
    buttons = build_button_grid(items, "test_prefix")
    
    # Should be organized in 2-column grid
    assert len(buttons) > 0, "Should have button rows"
    assert all(len(row) <= 2 for row in buttons), "Each row should have max 2 buttons"
    assert sum(len(row) for row in buttons) == len(items), "Should have all items"
    print(f"   ✓ Button grid created with {len(items)} items in {len(buttons)} rows")
    
    # Test 6: build_confirmation_keyboard
    print("\n6. Testing build_confirmation_keyboard()...")
    kb = build_confirmation_keyboard()
    assert kb is not None, "Keyboard should be created"
    print("   ✓ Confirmation keyboard created successfully")

    # Test 7: Important task summaries
    print("\n7. Testing important task summary formatting...")
    today = bot.today_text()
    empty_summary = format_important_tasks_summary(today, [])
    assert f"Important tasks for {today}" in empty_summary
    assert "No important tasks for today." in empty_summary
    task_summary = format_important_tasks_summary(
        "2026-05-22",
        [
            {"title": "Pay bills", "status": "pending"},
            {"title": "Send update", "status": "done"},
        ],
    )
    assert "Pending:\n1. Pay bills" in task_summary
    assert "Done:\n1. Send update" in task_summary
    print("   ✓ Important task summaries handle empty, pending, and done tasks")

    # Test 8: Reply keyboard layouts
    print("\n8. Testing reply keyboard layouts...")
    main_labels = reply_keyboard_labels(build_main_keyboard())
    assert "/start" in main_labels and "/view" in main_labels and "/tasks" in main_labels, "Main keyboard should include /start, /view, and /tasks"
    main_rows = reply_keyboard_rows(build_main_keyboard())
    assert main_rows[0] == ["/start", "/add", "/amend"], "Main keyboard should put /start at the top-left"
    assert main_rows[1] == ["/view", "/tasks"], "Main keyboard should group /view and /tasks"
    assert main_rows[2] == ["/help"], "Main keyboard should put /help alone at the bottom"
    assert "/today" not in main_labels and "/tomorrow" not in main_labels, "Main keyboard should hide /today and /tomorrow"

    task_labels = reply_keyboard_labels(build_task_keyboard())
    task_rows = reply_keyboard_rows(build_task_keyboard())
    for label in ["/add_task", "/done_task", "/edit_task", "/delete_task", "/refresh_tasks", "/back"]:
        assert label in task_labels, f"Task keyboard missing {label}"
    assert task_rows[2] == ["/refresh_tasks", "/back"], "Task keyboard should group /refresh_tasks and /back"
    assert "/view" not in task_labels, "Task keyboard should not include /view"

    view_labels = reply_keyboard_labels(build_view_keyboard())
    for label in ["/today", "/tomorrow", "/other_days", "/back"]:
        assert label in view_labels, f"View keyboard missing {label}"
    print("   ✓ Main, task, and view keyboards have the expected commands")


def test_calendar_service_helpers():
    """Test Google Calendar formatting and setup helper behavior."""
    print("\n" + "="*70)
    print("GOOGLE CALENDAR HELPER TESTS")
    print("="*70)

    print("\n1. Testing empty Google Calendar event formatting...")
    empty_message = calendar_service.format_events_for_telegram([], "today")
    assert empty_message == "No events found for today.", "Empty calendar message mismatch"
    print("   ✓ Empty event list formatted correctly")

    print("\n2. Testing all-day and timed Google Calendar formatting...")
    event_day = datetime(2026, 5, 22).date()
    events = [
        calendar_service.CalendarEvent(
            google_event_id="all-day-id",
            title="All Hands",
            start=event_day,
            end=event_day + timedelta(days=1),
            all_day=True,
        ),
        calendar_service.CalendarEvent(
            google_event_id="timed-id",
            title="Planning",
            start=datetime(2026, 5, 22, 9, 0, tzinfo=bot.LOCAL_TZ),
            end=datetime(2026, 5, 22, 10, 0, tzinfo=bot.LOCAL_TZ),
            all_day=False,
            location="Office",
            description="Bring notes",
        ),
    ]
    message = calendar_service.format_events_for_telegram(events, "today")
    assert "All day: All Hands" in message, "All-day event format missing"
    assert "09:00 - 10:00: Planning" in message, "Timed event format missing"
    assert "Location: Office" in message, "Location missing"
    assert "Notes: Bring notes" in message, "Notes missing"
    print("   ✓ All-day and timed event formatting works")

    print("\n3. Testing setup status helper...")
    status = calendar_service.get_setup_status()
    assert isinstance(status.ready, bool), "Ready status should be boolean"
    print("   ✓ Setup status helper returns readiness flags")

    print("\n4. Testing Important Tasks all-day event body...")
    body = calendar_service._important_tasks_body(event_day, "Pending:\n1. Pay bills")
    assert body["summary"] == "Important Tasks"
    assert body["start"] == {"date": "2026-05-22"}
    assert body["end"] == {"date": "2026-05-23"}
    assert "Pay bills" in body["description"]
    print("   ✓ Important Tasks Calendar body uses all-day date fields")


# ============================================================================
# COMMAND HANDLER TESTS
# ============================================================================

async def test_command_handlers():
    """Test command handler functions."""
    print("\n" + "="*70)
    print("COMMAND HANDLER TESTS")
    print("="*70)
    
    # Create mock objects
    def create_mock_update(user_id=12345, text=None):
        """Helper to create mock Update object."""
        update = AsyncMock()
        update.effective_user.id = user_id
        update.effective_chat.id = 777
        update.message = AsyncMock()
        update.message.text = text
        update.message.reply_text = AsyncMock()
        return update

    def create_mock_callback(user_id=12345, callback_data="task:done:1"):
        update = AsyncMock()
        update.callback_query = AsyncMock()
        update.callback_query.from_user.id = user_id
        update.callback_query.data = callback_data
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        update.callback_query.message = AsyncMock()
        update.callback_query.message.chat_id = 777
        update.callback_query.message.reply_text = AsyncMock()
        return update
    
    context = AsyncMock()
    
    # Test 1: start command
    print("\n1. Testing start command handler...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        update = create_mock_update()
        await bot.start(update, context)
        assert update.message.reply_text.called, "Should send reply"
        call_args = update.message.reply_text.call_args
        assert "Hello" in str(call_args), "Should contain welcome message"
        assert "itinerary" in str(call_args).lower(), "Should mention itinerary"
        registered = database.list_bot_users()
        assert any(user["chat_id"] == update.effective_chat.id for user in registered)
    print("   ✓ Start command sends welcome message with keyboard")
    
    # Test 2: help command
    print("\n2. Testing help command handler...")
    update = create_mock_update()
    await bot.help_command(update, context)
    assert update.message.reply_text.called, "Should send reply"
    call_args = update.message.reply_text.call_args
    assert "/add" in str(call_args), "Should list /add command"
    assert "/today" in str(call_args), "Should list /today command"
    assert "/test_5am" not in str(call_args) and "/test_8pm" not in str(call_args)
    print("   ✓ Help command lists all available commands")
    
    # Test 3: connect_calendar command
    print("\n3. Testing connect_calendar command handler...")
    update = create_mock_update()
    await bot.connect_calendar(update, context)
    assert update.message.reply_text.called, "Should send reply"
    call_args = update.message.reply_text.call_args
    assert "credentials.json" in str(call_args), "Should explain credentials.json setup"
    assert "calendar_service.py auth" in str(call_args), "Should explain auth command"
    print("   ✓ Connect calendar sends setup instructions")
    
    # Test 4: cancel command
    print("\n4. Testing cancel command handler...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        # First create a draft
        user_id = 12345
        database.save_draft(user_id, "test_stage", {"data": "test"})
        
        update = create_mock_update(user_id=user_id)
        await bot.cancel_command(update, context)
        
        assert update.message.reply_text.called, "Should send confirmation"
        draft = database.get_draft(user_id)
        assert draft is None, "Draft should be cleared"
        print("   ✓ Cancel command clears draft and sends confirmation")
    
    # Test 5: today command (no events)
    print("\n5. Testing today command handler (no Google Calendar events)...")
    with patch.object(bot.calendar_service, 'get_events_for_day', return_value=[]):
        update = create_mock_update(user_id=99999)
        await bot.today(update, context)
        assert update.message.reply_text.called, "Should send reply"
        call_args = update.message.reply_text.call_args
        assert "No events found for today" in str(call_args), "Should say no Google Calendar events"
        print("   ✓ Today command handles no Google Calendar events gracefully")
    
    # Test 6: tomorrow command (no events)
    print("\n6. Testing tomorrow command handler (no Google Calendar events)...")
    with patch.object(bot.calendar_service, 'get_events_for_day', return_value=[]):
        update = create_mock_update(user_id=99999)
        await bot.tomorrow(update, context)
        assert update.message.reply_text.called, "Should send reply"
        call_args = update.message.reply_text.call_args
        assert "No events found for tomorrow" in str(call_args), "Should say no Google Calendar events"
        print("   ✓ Tomorrow command handles no Google Calendar events gracefully")
    
    # Test 7: add_event command
    print("\n7. Testing add_event command handler...")
    update = create_mock_update()
    await bot.add_event(update, context)
    assert update.message.reply_text.called, "Should send reply with options"
    assert "Other days" in str(update.message.reply_text.call_args)
    assert "Cancel" in str(update.message.reply_text.call_args)
    assert "Pick date" not in str(update.message.reply_text.call_args)
    print("   ✓ Add event command sends date selection options")

    # Test 8: amend command
    print("\n8. Testing amend command handler...")
    update = create_mock_update()
    await bot.amend_command(update, context)
    assert update.message.reply_text.called, "Should send reply with date options"
    call_args = str(update.message.reply_text.call_args)
    assert "amend" in call_args.lower(), "Should describe amend flow"
    assert "eventdate:amend" in call_args, "Date buttons should use amend mode"
    assert "Other days" in call_args
    assert "YYYY-MM-DD" not in call_args
    print("   ✓ Amend command sends date selection options for edit/delete")

    # Test 9: view command
    print("\n9. Testing view command handler...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        update = create_mock_update()
        await bot.view_command(update, context)
        call_args = update.message.reply_text.call_args
        assert "Show today, tomorrow, or use /other_days" in str(call_args)
        labels = reply_keyboard_labels(call_args.kwargs["reply_markup"])
        assert "/today" in labels and "/tomorrow" in labels and "/other_days" in labels and "/back" in labels
        draft = database.get_draft(update.effective_user.id)
        assert draft["stage"] == "awaiting_view_date"
        print("   ✓ View command switches to the view keyboard")

    # Test 9b: other_days opens calendar picker for view
    print("\n9b. Testing other_days command opens calendar picker...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        update = create_mock_update()
        await bot.other_days_command(update, context)
        assert "Choose a date" in str(update.message.reply_text.call_args)
        assert "cal:view:day:" in str(update.message.reply_text.call_args)
        print("   ✓ Other days command opens the view calendar picker")

    # Test 9c: calendar picker callbacks select view and task dates
    print("\n9c. Testing calendar picker date selection...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        user_id = 24681
        selected_day = bot.tomorrow_text()
        update = create_mock_callback(user_id=user_id, callback_data=f"cal:view:day:{selected_day}")
        with patch.object(bot, "send_google_calendar_day", AsyncMock()) as send_day:
            await bot.calendar_picker_callback_handler(update, context)
        send_day.assert_called_once()
        assert send_day.call_args.args[2] == selected_day

        update = create_mock_callback(user_id=user_id, callback_data=f"cal:task:day:{selected_day}")
        with patch.object(bot, "open_task_menu_for_date", AsyncMock()) as open_task_menu:
            await bot.calendar_picker_callback_handler(update, context)
        open_task_menu.assert_called_once()
        assert open_task_menu.call_args.args[4] == selected_day

        update = create_mock_callback(user_id=user_id, callback_data="cal:view:month:2026-06")
        await bot.calendar_picker_callback_handler(update, context)
        assert "Choose a date" in str(update.callback_query.edit_message_text.call_args)
        print("   ✓ Calendar picker callbacks handle date selection and month navigation")

    # Test 9d: calendar picker supports add/amend/recurrence/edit date flows
    print("\n9d. Testing calendar picker date flows for add and amend...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        user_id = 24682
        selected_day = bot.tomorrow_text()

        database.save_draft(user_id, "awaiting_pick_date", {})
        update = create_mock_callback(user_id=user_id, callback_data=f"cal:add:day:{selected_day}")
        await bot.calendar_picker_callback_handler(update, context)
        draft = database.get_draft(user_id)
        assert draft["stage"] == "period_selection" and draft["data"]["date"] == selected_day
        assert "Now choose a time period" in str(update.callback_query.edit_message_text.call_args)

        update = create_mock_callback(user_id=user_id, callback_data=f"eventdate:amend:pick")
        await bot.event_date_callback_handler(update, context)
        assert "Choose which date to amend" in str(update.callback_query.edit_message_text.call_args)
        assert "cal:event_amend:day:" in str(update.callback_query.edit_message_text.call_args)

        update = create_mock_callback(user_id=user_id, callback_data=f"cal:event_amend:day:{selected_day}")
        with patch.object(bot, "edit_google_events_message_text", AsyncMock()) as edit_events:
            await bot.calendar_picker_callback_handler(update, context)
        edit_events.assert_called_once()
        assert edit_events.call_args.args[3].isoformat() == selected_day

        event_data = {
            "date": bot.today_text(),
            "start_time": "09:00",
            "end_time": "10:00",
            "title": "Recurring Test",
        }
        database.save_draft(user_id, "awaiting_recurrence_until", event_data)
        update = create_mock_callback(user_id=user_id, callback_data=f"cal:recur:day:{selected_day}")
        await bot.calendar_picker_callback_handler(update, context)
        draft = database.get_draft(user_id)
        assert draft["stage"] == "recurrence_type_selection" and draft["data"]["recurrence_until"] == selected_day
        assert "How should this event repeat" in str(update.callback_query.edit_message_text.call_args)

        selected_event = {
            "google_event_id": "edit-date-event",
            "date": bot.today_text(),
            "start_time": "09:00",
            "end_time": "10:00",
            "title": "Edit Date Test",
        }
        database.save_draft(user_id, "editing_event_field:date", selected_event)
        update = create_mock_callback(user_id=user_id, callback_data=f"cal:editdate:day:{selected_day}")
        with patch.object(bot, "find_overlapping_events", return_value=[]), patch.object(bot, "apply_google_event_edit", AsyncMock()) as apply_edit:
            await bot.calendar_picker_callback_handler(update, context)
        apply_edit.assert_called_once()
        assert apply_edit.call_args.args[2]["date"] == selected_day
        print("   ✓ Calendar picker handles add, amend, recurrence, and edit-date flows")

    # Test 9e: recurrence type and custom date selection flow
    print("\n9e. Testing recurrence type and custom-date flows...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        user_id = 24683
        event_day = bot.today_text()
        recurrence_until = (bot.singapore_today() + timedelta(days=7)).isoformat()
        extra_recurrence_day = (bot.singapore_today() + timedelta(days=2)).isoformat()
        event_data = {
            "date": event_day,
            "start_time": "09:00",
            "end_time": "10:00",
            "title": "Recurring Flow Test",
            "location": "",
            "notes": "",
            "recurring": True,
            "recurrence_until": recurrence_until,
        }

        database.save_draft(user_id, "recurrence_type_selection", dict(event_data))
        update = create_mock_callback(user_id=user_id, callback_data="add:rtype:WEEKDAYS")
        await bot.add_button_handler(update, context)
        draft = database.get_draft(user_id)
        assert draft["stage"] == "confirm_event"
        assert draft["data"]["recurrence_type"] == "WEEKDAYS"
        assert "Weekdays" in str(update.callback_query.edit_message_text.call_args)

        database.save_draft(user_id, "recurrence_type_selection", dict(event_data))
        update = create_mock_callback(user_id=user_id, callback_data="add:rtype:CUSTOM")
        await bot.add_button_handler(update, context)
        draft = database.get_draft(user_id)
        assert draft["stage"] == "custom_recurrence_selection"
        assert "Choose the exact recurrence dates" in str(update.callback_query.edit_message_text.call_args)

        update = create_mock_callback(user_id=user_id, callback_data=f"customrecur:day:{event_day}")
        await bot.custom_recurrence_callback_handler(update, context)
        update = create_mock_callback(user_id=user_id, callback_data="customrecur:done")
        await bot.custom_recurrence_callback_handler(update, context)
        assert "extra recurrence date" in str(update.callback_query.edit_message_text.call_args)

        update = create_mock_callback(user_id=user_id, callback_data=f"customrecur:day:{extra_recurrence_day}")
        await bot.custom_recurrence_callback_handler(update, context)
        draft = database.get_draft(user_id)
        assert extra_recurrence_day in draft["data"]["recurrence_custom_dates"]

        update = create_mock_callback(user_id=user_id, callback_data="customrecur:done")
        await bot.custom_recurrence_callback_handler(update, context)
        draft = database.get_draft(user_id)
        assert draft["stage"] == "confirm_event"
        assert draft["data"]["recurrence_type"] == "CUSTOM"
        assert extra_recurrence_day in draft["data"]["recurrence_custom_dates"]
        print("   ✓ Recurrence choices and custom dates reach confirmation correctly")

    # Test 10: task command family
    print("\n10. Testing task command handlers...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        user_id = 24680
        update = create_mock_update(user_id=user_id)
        await bot.tasks_command(update, context)
        call_args = update.message.reply_text.call_args
        assert "Choose a date for Important Tasks" in str(call_args)
        assert "taskdate:today" in str(call_args)
        draft = database.get_draft(user_id)
        assert draft["stage"] == "awaiting_task_date"

        update = create_mock_callback(user_id=user_id, callback_data="taskdate:other")
        await bot.task_date_callback_handler(update, context)
        assert "Choose a task date" in str(update.callback_query.edit_message_text.call_args)
        assert "cal:task:day:" in str(update.callback_query.edit_message_text.call_args)

        update = create_mock_callback(user_id=user_id, callback_data="taskdate:tomorrow")
        with patch.object(bot, "open_task_menu_for_date", AsyncMock()) as open_task_menu:
            await bot.task_date_callback_handler(update, context)
        open_task_menu.assert_called_once()
        assert open_task_menu.call_args.args[4] == bot.tomorrow_text()

        database.save_draft(user_id, "awaiting_task_date", {})
        update = create_mock_update(user_id=user_id, text=bot.tomorrow_text())
        update.message.reply_text.side_effect = [Mock(message_id=2467), Mock(message_id=2468)]
        with patch.object(bot, "sync_important_tasks_calendar_event", return_value="calendar-task"):
            await bot.add_text_handler(update, context)
        draft = database.get_draft(user_id)
        assert draft["stage"] == "task_menu" and draft["data"]["task_date"] == bot.tomorrow_text()
        task_pin = database.get_task_pin(user_id, update.effective_chat.id, bot.tomorrow_text())
        assert task_pin["pinned_message_id"] is None

        database.save_draft(user_id, "awaiting_task_date", {})
        past_date = (datetime.now(bot.LOCAL_TZ).date() - timedelta(days=1)).isoformat()
        update = create_mock_update(user_id=user_id, text=past_date)
        await bot.add_text_handler(update, context)
        assert "Invalid date entered" in str(update.message.reply_text.call_args)
        assert database.get_draft(user_id)["stage"] == "awaiting_task_date"

        database.save_draft(user_id, "task_menu", {"task_date": bot.tomorrow_text()})

        update = create_mock_update(user_id=user_id)
        await bot.add_task_command(update, context)
        draft = database.get_draft(user_id)
        assert draft["stage"] == "awaiting_task_title"
        assert draft["data"]["task_date"] == bot.tomorrow_text()

        update = create_mock_update(user_id=user_id)
        await bot.done_task_command(update, context)
        assert "No pending important tasks" in str(update.message.reply_text.call_args)

        update = create_mock_update(user_id=user_id)
        await bot.delete_task_command(update, context)
        assert f"No important tasks to delete for {bot.tomorrow_text()}" in str(update.message.reply_text.call_args)

        update = create_mock_update(user_id=user_id)
        await bot.edit_task_command(update, context)
        assert f"No important tasks to edit for {bot.tomorrow_text()}" in str(update.message.reply_text.call_args)
        print("   ✓ Task commands open task menu and handle empty task lists")

    # Test 11: back command
    print("\n11. Testing back command handler...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        user_id = 13579
        database.save_draft(user_id, "awaiting_view_date", {})
        update = create_mock_update(user_id=user_id)
        await bot.back_command(update, context)
        assert database.get_draft(user_id) is None
        labels = reply_keyboard_labels(update.message.reply_text.call_args.kwargs["reply_markup"])
        assert "/view" in labels and "/tasks" in labels
        print("   ✓ Back command returns to main keyboard")

    # Test 12: scheduled reminder send helpers
    print("\n12. Testing scheduled reminder send helpers...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        user_id = 13580
        chat_id = 777
        reminder_context = AsyncMock()
        reminder_context.bot = AsyncMock()
        with patch.object(bot, "build_google_calendar_day_text", return_value="No events found for today."):
            await bot.send_5am_itinerary_to_chat(reminder_context, user_id, chat_id)
        call_args = str(reminder_context.bot.send_message.call_args)
        assert "Good morning" in call_args
        assert "Important tasks for" in call_args

        await bot.send_8pm_review_to_chat(reminder_context, chat_id)
        call_args = reminder_context.bot.send_message.call_args
        assert "Have you reviewed tomorrow’s itinerary?" in str(call_args)
        assert "review:view_tomorrow" in str(call_args)
        print("   ✓ Scheduled 5am and 8pm helpers send the expected reminder messages")

    # Test 13: tomorrow review callbacks
    print("\n13. Testing tomorrow review callbacks...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        user_id = 13581
        update = create_mock_callback(user_id=user_id, callback_data="review:view_tomorrow")
        with patch.object(bot, "send_google_calendar_day", AsyncMock()) as send_day:
            await bot.review_callback_handler(update, context)
        send_day.assert_called_once()
        assert send_day.call_args.args[1].isoformat() == bot.tomorrow_text()
        assert send_day.call_args.args[2] == "tomorrow"

        update = create_mock_callback(user_id=user_id, callback_data="review:add_event")
        await bot.review_callback_handler(update, context)
        assert update.callback_query.message.reply_text.call_count >= 2
        assert database.get_draft(user_id)["stage"] == "date_selection"

        update = create_mock_callback(user_id=user_id, callback_data="review:done")
        await bot.review_callback_handler(update, context)
        review = database.get_daily_review(user_id, update.callback_query.message.chat_id, bot.tomorrow_text())
        assert review["status"] == "reviewed"

        update = create_mock_callback(user_id=user_id, callback_data="review:no_plans")
        await bot.review_callback_handler(update, context)
        review = database.get_daily_review(user_id, update.callback_query.message.chat_id, bot.tomorrow_text())
        assert review["status"] == "no_plans"
        print("   ✓ Review buttons view tomorrow, start add flow, and save statuses")

    # Test 14: scheduled jobs are registered once at startup
    print("\n14. Testing scheduled job registration...")
    mock_app = Mock()
    mock_app.job_queue = Mock()
    old_job = Mock()
    mock_app.job_queue.get_jobs_by_name.side_effect = [[old_job], []]
    bot.register_scheduled_jobs(mock_app)
    assert old_job.schedule_removal.called, "Existing named jobs should be removed before re-registering"
    assert mock_app.job_queue.run_daily.call_count == 2, "Should register 5am and 8pm daily jobs"
    job_names = [call.kwargs["name"] for call in mock_app.job_queue.run_daily.call_args_list]
    assert "daily_5am_itinerary" in job_names and "daily_8pm_review" in job_names
    print("   ✓ Daily jobs are registered once by name at startup")

    # Test 15: event delete asks for confirmation before deleting
    print("\n15. Testing event delete confirmation...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        user_id = 13582
        event_data = {
            "google_event_id": "delete-confirm-event",
            "title": "Delete Confirm Test",
            "date": bot.today_text(),
            "start_time": "09:00",
            "end_time": "10:00",
            "location": "",
            "notes": "",
        }
        database.save_draft(user_id, "event_selection", {"events": [event_data]})
        update = create_mock_callback(user_id=user_id, callback_data="event:delete:0")
        with patch.object(bot.calendar_service, "delete_event") as delete_mock:
            await bot.event_callback_handler(update, context)
        delete_mock.assert_not_called()
        assert "Delete this event" in str(update.callback_query.edit_message_text.call_args)
        assert "Confirm delete" in str(update.callback_query.edit_message_text.call_args)
        assert "Cancel" in str(update.callback_query.edit_message_text.call_args)
        print("   ✓ Event deletion shows Confirm delete and Cancel buttons first")

    # Test 16: custom date view text input
    print("\n16. Testing custom date view text input...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        user_id = 11223
        database.save_draft(user_id, "awaiting_view_date", {})
        update = create_mock_update(user_id=user_id, text="2026-05-22")
        calendar_event = calendar_service.CalendarEvent(
            google_event_id="custom-date-event",
            title="Custom Date Event",
            start=datetime(2026, 5, 22, 14, 0, tzinfo=bot.LOCAL_TZ),
            end=datetime(2026, 5, 22, 15, 0, tzinfo=bot.LOCAL_TZ),
            all_day=False,
        )
        with patch.object(bot.calendar_service, "get_events_for_day", return_value=[calendar_event]):
            await bot.add_text_handler(update, context)
        assert "Custom Date Event" in str(update.message.reply_text.call_args)
        assert database.get_draft(user_id) is None

        database.save_draft(user_id, "awaiting_view_date", {})
        update = create_mock_update(user_id=user_id, text="not-a-date")
        await bot.add_text_handler(update, context)
        assert "Please use /today, /tomorrow, /other_days, or /back" in str(update.message.reply_text.call_args)
        assert database.get_draft(user_id)["stage"] == "awaiting_view_date"
        print("   ✓ Custom date view handles valid and invalid dates")

    # Test 17: /add_task text input saves task
    print("\n17. Testing add task text input...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        user_id = 44556
        task_date = bot.tomorrow_text()
        database.save_draft(user_id, "awaiting_task_title", {"task_date": task_date})
        update = create_mock_update(user_id=user_id, text="Review budget")
        with patch.object(bot, "refresh_important_tasks_summary", AsyncMock(return_value=(f"Important tasks for {task_date}\n\nPending:\n1. Review budget", None))):
            await bot.add_text_handler(update, context)
        tasks = database.list_important_tasks(user_id, task_date)
        assert len(tasks) == 1 and tasks[0]["title"] == "Review budget"
        assert "Important task saved" in str(update.message.reply_text.call_args)
        assert "Review budget" in str(update.message.reply_text.call_args)
        assert database.get_draft(user_id)["data"]["task_date"] == task_date
        print("   ✓ Text after /add_task saves an important task")

    # Test 18: /edit_task text input updates task and shows the refreshed list
    print("\n18. Testing edit task text input...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        user_id = 44557
        task_id = database.add_important_task(user_id, bot.today_text(), "Old task")
        database.save_draft(user_id, "awaiting_task_edit_title", {"task_id": task_id})
        update = create_mock_update(user_id=user_id, text="New task")
        with patch.object(bot, "refresh_important_tasks_summary", AsyncMock(return_value=("Important tasks for today\n\nPending:\n1. New task", None))):
            await bot.add_text_handler(update, context)
        task = database.get_important_task(user_id, task_id)
        assert task["title"] == "New task"
        assert "Important task updated" in str(update.message.reply_text.call_args)
        assert "New task" in str(update.message.reply_text.call_args)
        assert database.get_draft(user_id)["data"]["task_date"] == bot.today_text()
        print("   ✓ Text after /edit_task updates an important task")

    # Test 19: task callbacks auto-show refreshed task lists
    print("\n19. Testing task callbacks show refreshed lists...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        user_id = 44558
        task_id = database.add_important_task(user_id, bot.today_text(), "Callback task")
        update = create_mock_callback(user_id=user_id, callback_data=f"task:done:{task_id}")
        with patch.object(bot, "refresh_important_tasks_summary", AsyncMock(return_value=("Important tasks for today\n\nDone:\n1. Callback task", None))):
            await bot.task_callback_handler(update, context)
        assert "Marked done" in str(update.callback_query.edit_message_text.call_args)
        assert "Callback task" in str(update.callback_query.edit_message_text.call_args)

        task_id = database.add_important_task(user_id, bot.today_text(), "Delete me")
        update = create_mock_callback(user_id=user_id, callback_data=f"task:delete:{task_id}")
        await bot.task_callback_handler(update, context)
        assert "Delete this important task" in str(update.callback_query.edit_message_text.call_args)

        update = create_mock_callback(user_id=user_id, callback_data=f"task:confirm_delete:{task_id}")
        with patch.object(bot, "refresh_important_tasks_summary", AsyncMock(return_value=("Important tasks for today\n\nNo important tasks for today.", None))):
            await bot.task_callback_handler(update, context)
        assert "Deleted important task" in str(update.callback_query.edit_message_text.call_args)
        assert "No important tasks for today" in str(update.callback_query.edit_message_text.call_args)

        task_id = database.add_important_task(user_id, bot.today_text(), "Edit me")
        update = create_mock_callback(user_id=user_id, callback_data=f"task:edit:{task_id}")
        await bot.task_callback_handler(update, context)
        assert database.get_draft(user_id)["stage"] == "awaiting_task_edit_title"
        assert "updated task text" in str(update.callback_query.edit_message_text.call_args)
        print("   ✓ Done, delete, and edit callbacks update or prepare the visible task list")

    # Test 20: task refresh re-pins an existing summary after editing it
    print("\n20. Testing task refresh re-pins existing summary...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        user_id = 44559
        chat_id = 777
        database.add_important_task(user_id, bot.today_text(), "Pinned task")
        database.save_task_pin(user_id, chat_id, bot.today_text(), 321, "calendar-task")
        update = create_mock_update(user_id=user_id)
        task_context = AsyncMock()
        task_context.bot = AsyncMock()
        task_context.bot.edit_message_text = AsyncMock()
        task_context.bot.pin_chat_message = AsyncMock()
        task_context.bot.unpin_chat_message = AsyncMock()
        task_context.bot.send_message = AsyncMock()
        with patch.object(bot, "sync_important_tasks_calendar_event", return_value="calendar-task"):
            await bot.refresh_important_tasks_summary(
                update.message,
                task_context,
                user_id,
                chat_id,
                bot.today_text(),
            )
        task_context.bot.edit_message_text.assert_called_once()
        task_context.bot.pin_chat_message.assert_called_once()
        task_context.bot.unpin_chat_message.assert_not_called()
        task_context.bot.send_message.assert_not_called()
        assert task_context.bot.pin_chat_message.call_args.kwargs["message_id"] == 321
        print("   ✓ Existing task summary is edited and re-pinned")

    # Test 21: manual task refresh unpins old known task summaries
    print("\n21. Testing manual task refresh unpins old task summaries...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        user_id = 44560
        chat_id = 777
        today = bot.today_text()
        old_day = (datetime.now(bot.LOCAL_TZ).date() - timedelta(days=1)).isoformat()
        database.add_important_task(user_id, today, "Today task")
        database.save_task_pin(user_id, chat_id, old_day, 111, "old-calendar-task")
        update = create_mock_update(user_id=user_id)
        task_context = AsyncMock()
        task_context.bot = AsyncMock()
        task_context.bot.edit_message_text = AsyncMock()
        task_context.bot.pin_chat_message = AsyncMock()
        task_context.bot.unpin_chat_message = AsyncMock()
        task_context.bot.send_message = AsyncMock(return_value=Mock(message_id=222))
        with patch.object(bot, "sync_important_tasks_calendar_event", return_value="calendar-task"):
            await bot.refresh_tasks_command(update, task_context)
        task_context.bot.unpin_chat_message.assert_called_once()
        assert task_context.bot.unpin_chat_message.call_args.kwargs["message_id"] == 111
        task_context.bot.pin_chat_message.assert_called_once()
        assert task_context.bot.pin_chat_message.call_args.kwargs["message_id"] == 222
        assert "Important task summary refreshed" in str(update.message.reply_text.call_args)
        print("   ✓ Manual task refresh unpins old known summaries before pinning today's list")

    # Test 22: opening today's task menu pins the newly printed task message
    print("\n22. Testing today's task menu pins the newest printed task message...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        user_id = 44561
        chat_id = 777
        old_day = (datetime.now(bot.LOCAL_TZ).date() - timedelta(days=1)).isoformat()
        selected_day = bot.today_text()
        database.save_task_pin(user_id, chat_id, old_day, 111, "old-calendar-task")
        database.add_important_task(user_id, selected_day, "Today task")
        update = create_mock_update(user_id=user_id)
        update.message.reply_text.side_effect = [Mock(message_id=332), Mock(message_id=333)]
        task_context = AsyncMock()
        task_context.bot = AsyncMock()
        task_context.bot.pin_chat_message = AsyncMock()
        task_context.bot.unpin_chat_message = AsyncMock()
        with patch.object(bot, "sync_important_tasks_calendar_event", return_value="calendar-task"):
            await bot.open_task_menu_for_date(
                update.message,
                task_context,
                user_id,
                chat_id,
                selected_day,
            )
        task_context.bot.unpin_chat_message.assert_called_once()
        assert task_context.bot.unpin_chat_message.call_args.kwargs["message_id"] == 111
        task_context.bot.pin_chat_message.assert_called_once()
        assert task_context.bot.pin_chat_message.call_args.kwargs["message_id"] == 333
        task_pin = database.get_task_pin(user_id, chat_id, selected_day)
        assert task_pin["pinned_message_id"] == 333
        first_reply = update.message.reply_text.call_args_list[0]
        second_reply = update.message.reply_text.call_args_list[1]
        assert "Quick guide" in str(first_reply)
        assert "Today task" not in str(first_reply)
        assert "Today task" in str(second_reply)
        assert "Quick guide" not in str(second_reply)
        print("   ✓ Today's task menu unpins old summaries and pins the newest summary-only message")

    # Test 23: future task menus and refreshes do not pin or unpin
    print("\n23. Testing future task menus and refreshes do not pin...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        user_id = 44562
        chat_id = 777
        selected_day = bot.tomorrow_text()
        database.save_task_pin(user_id, chat_id, bot.today_text(), 111, "today-calendar-task")
        database.add_important_task(user_id, selected_day, "Future task")
        update = create_mock_update(user_id=user_id)
        update.message.reply_text.side_effect = [Mock(message_id=444), Mock(message_id=445)]
        task_context = AsyncMock()
        task_context.bot = AsyncMock()
        task_context.bot.pin_chat_message = AsyncMock()
        task_context.bot.unpin_chat_message = AsyncMock()
        task_context.bot.send_message = AsyncMock()
        with patch.object(bot, "sync_important_tasks_calendar_event", return_value="calendar-task"):
            await bot.open_task_menu_for_date(
                update.message,
                task_context,
                user_id,
                chat_id,
                selected_day,
            )
        task_context.bot.unpin_chat_message.assert_not_called()
        task_context.bot.pin_chat_message.assert_not_called()
        task_pin = database.get_task_pin(user_id, chat_id, selected_day)
        assert task_pin["pinned_message_id"] is None

        database.save_draft(user_id, "task_menu", {"task_date": selected_day})
        update = create_mock_update(user_id=user_id)
        with patch.object(bot, "sync_important_tasks_calendar_event", return_value="calendar-task"):
            await bot.refresh_tasks_command(update, task_context)
        task_context.bot.send_message.assert_not_called()
        task_context.bot.pin_chat_message.assert_not_called()
        task_context.bot.unpin_chat_message.assert_not_called()
        assert "Future task" in str(update.message.reply_text.call_args)
        print("   ✓ Future task menus and refreshes show tasks without changing pins")


async def test_google_calendar_command_workflows():
    """Test Telegram handlers that call Google Calendar services."""
    print("\n" + "="*70)
    print("GOOGLE CALENDAR COMMAND WORKFLOW TESTS")
    print("="*70)

    def create_mock_callback(user_id=12345, callback_data="add:confirm:yes"):
        update = AsyncMock()
        update.callback_query = AsyncMock()
        update.callback_query.from_user.id = user_id
        update.callback_query.data = callback_data
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        return update

    def create_mock_message(user_id=12345):
        update = AsyncMock()
        update.effective_user.id = user_id
        update.message = AsyncMock()
        update.message.reply_text = AsyncMock()
        return update

    context = AsyncMock()

    print("\n1. Testing /add confirmation creates Google Calendar event...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        user_id = 54321
        event_data = {
            "title": "Google Sync Test",
            "date": "2026-05-22",
            "start_time": "09:00",
            "end_time": "10:00",
            "location": "Office",
            "notes": "Created from Telegram",
        }
        database.save_draft(user_id, "confirm_event", event_data)
        update = create_mock_callback(user_id=user_id)
        with patch.object(bot.calendar_service, "get_events_for_day", return_value=[]), \
            patch.object(bot.calendar_service, "create_event", return_value="google-event-123") as create_mock:
            await bot.add_button_handler(update, context)

        create_mock.assert_called_once()
        saved = database.list_events(user_id, "2026-05-22")
        assert len(saved) == 1, "One local reference should be saved"
        assert saved[0]["google_event_id"] == "google-event-123", "Google event ID should be stored"
        assert "Saved event to Google Calendar" in str(update.callback_query.edit_message_text.call_args)
        print("   ✓ /add confirm calls Google Calendar and stores the Google event ID")

    print("\n2. Testing /today displays Google Calendar events...")
    calendar_event = calendar_service.CalendarEvent(
        google_event_id="google-event-456",
        title="Displayed Event",
        start=datetime(2026, 5, 22, 11, 0, tzinfo=bot.LOCAL_TZ),
        end=datetime(2026, 5, 22, 12, 0, tzinfo=bot.LOCAL_TZ),
        all_day=False,
        location="Cafe",
        description="Shown by /today",
    )
    update = create_mock_message()
    with patch.object(bot.calendar_service, "get_events_for_day", return_value=[calendar_event]):
        await bot.today(update, context)

    assert update.message.reply_text.called, "Should reply with Google Calendar events"
    call_args = str(update.message.reply_text.call_args)
    assert "Displayed Event" in call_args, "Calendar event title should be shown"
    assert "11:00 - 12:00" in call_args, "Calendar event time should be shown"
    print("   ✓ /today displays Google Calendar events")


async def test_phase5_behaviors():
    """Test Phase 5 date validation, overlap warnings, and recurrence helpers."""
    print("\n" + "="*70)
    print("PHASE 5 BEHAVIOR TESTS")
    print("="*70)

    def create_mock_message(user_id=12345, text=""):
        update = AsyncMock()
        update.effective_user.id = user_id
        update.message = AsyncMock()
        update.message.text = text
        update.message.reply_text = AsyncMock()
        return update

    def create_mock_callback(user_id=12345, callback_data="add:confirm:yes"):
        update = AsyncMock()
        update.callback_query = AsyncMock()
        update.callback_query.from_user.id = user_id
        update.callback_query.data = callback_data
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        return update

    context = AsyncMock()

    print("\n1. Testing /add rejects past custom dates...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        user_id = 67890
        database.save_draft(user_id, "awaiting_pick_date", {})
        update = create_mock_message(user_id=user_id, text="2000-01-01")
        await bot.add_text_handler(update, context)
        assert "Invalid date entered" in str(update.message.reply_text.call_args)
        print("   ✓ Past /add date is rejected")

    print("\n2. Testing /add warns before creating overlapping event...")
    overlap_event = calendar_service.CalendarEvent(
        google_event_id="existing-event",
        title="Existing Meeting",
        start=datetime(2026, 5, 22, 9, 30, tzinfo=bot.LOCAL_TZ),
        end=datetime(2026, 5, 22, 10, 30, tzinfo=bot.LOCAL_TZ),
        all_day=False,
    )
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        user_id = 67891
        event_data = {
            "title": "Overlap Test",
            "date": "2026-05-22",
            "start_time": "09:00",
            "end_time": "10:00",
            "location": "",
            "notes": "",
        }
        database.save_draft(user_id, "confirm_event", event_data)
        update = create_mock_callback(user_id=user_id)
        with patch.object(bot.calendar_service, "get_events_for_day", return_value=[overlap_event]), \
            patch.object(bot.calendar_service, "create_event") as create_mock:
            await bot.add_button_handler(update, context)
        create_mock.assert_not_called()
        assert "overlaps" in str(update.callback_query.edit_message_text.call_args)
        print("   ✓ Overlap warning appears before Calendar creation")

    print("\n3. Testing recurring event body generation...")
    recurring_data = {
        "title": "Daily Standup",
        "date": "2026-05-22",
        "start_time": "09:00",
        "end_time": "09:30",
        "location": "",
        "notes": "",
        "recurring": True,
        "recurrence_frequency": "DAILY",
        "recurrence_until": "2026-05-25",
    }
    body = calendar_service._event_data_to_body(recurring_data)
    assert body["recurrence"][0].startswith("RRULE:FREQ=DAILY;UNTIL=")
    weekly_data = dict(recurring_data, recurrence_type="WEEKLY", recurrence_frequency="WEEKLY")
    weekly_body = calendar_service._event_data_to_body(weekly_data)
    assert "FREQ=WEEKLY" in weekly_body["recurrence"][0] and "BYDAY=FR" in weekly_body["recurrence"][0]

    monthly_data = dict(recurring_data, recurrence_type="MONTHLY", recurrence_frequency="MONTHLY")
    monthly_body = calendar_service._event_data_to_body(monthly_data)
    assert "FREQ=MONTHLY" in monthly_body["recurrence"][0] and "BYDAY=4FR" in monthly_body["recurrence"][0]

    yearly_data = dict(recurring_data, recurrence_type="YEARLY", recurrence_frequency="YEARLY")
    yearly_body = calendar_service._event_data_to_body(yearly_data)
    assert "FREQ=YEARLY" in yearly_body["recurrence"][0]
    assert "BYMONTH=5" in yearly_body["recurrence"][0] and "BYMONTHDAY=22" in yearly_body["recurrence"][0]

    weekdays_data = dict(recurring_data, recurrence_type="WEEKDAYS", recurrence_frequency="WEEKDAYS")
    weekdays_body = calendar_service._event_data_to_body(weekdays_data)
    assert "BYDAY=MO,TU,WE,TH,FR" in weekdays_body["recurrence"][0]

    custom_data = dict(
        recurring_data,
        recurrence_type="CUSTOM",
        recurrence_frequency="CUSTOM",
        recurrence_custom_dates=["2026-05-22", "2026-05-26", "2026-05-28"],
    )
    custom_body = calendar_service._event_data_to_body(custom_data)
    assert custom_body["recurrence"][0].startswith("RDATE;TZID=Asia/Singapore:")
    assert "20260526T090000" in custom_body["recurrence"][0]
    assert "20260528T090000" in custom_body["recurrence"][0]

    incomplete_data = dict(recurring_data)
    incomplete_data.pop("recurrence_until")
    try:
        calendar_service._event_data_to_body(incomplete_data)
        raise AssertionError("Incomplete recurrence should not silently save as one-time event")
    except calendar_service.CalendarApiError:
        pass
    print("   ✓ Recurrence rules are generated for daily, weekly, monthly, yearly, weekday, and custom events")

    print("\n4. Testing recurring delete asks for occurrence or series scope...")
    recurring_event = calendar_service.CalendarEvent(
        google_event_id="instance-1",
        recurring_event_id="series-1",
        title="Recurring Sync",
        start=datetime(2026, 5, 22, 9, 0, tzinfo=bot.LOCAL_TZ),
        end=datetime(2026, 5, 22, 10, 0, tzinfo=bot.LOCAL_TZ),
        all_day=False,
    )
    recurring_draft = bot.calendar_event_to_draft(recurring_event)
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        user_id = 67892
        database.save_draft(user_id, "event_selection", {"events": [recurring_draft]})
        update = create_mock_callback(user_id=user_id, callback_data="event:delete:0")
        with patch.object(bot.calendar_service, "delete_event") as delete_mock:
            await bot.event_callback_handler(update, context)
        delete_mock.assert_not_called()
        draft = database.get_draft(user_id)
        assert draft["stage"] == "recurring_scope_selection"
        assert "recurring event" in str(update.callback_query.edit_message_text.call_args)
        print("   ✓ Recurring delete prompts for scope before deleting")

    print("\n5. Testing recurring delete scope uses the correct Google event ID...")
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        user_id = 67893
        database.save_draft(user_id, "recurring_scope_selection", {"mode": "delete", "event": recurring_draft})
        update = create_mock_callback(user_id=user_id, callback_data="recurring:delete:single")
        with patch.object(bot.calendar_service, "delete_event") as delete_mock:
            await bot.recurring_scope_callback_handler(update, context)
        delete_mock.assert_called_once_with("instance-1")

        database.save_draft(user_id, "recurring_scope_selection", {"mode": "delete", "event": recurring_draft})
        update = create_mock_callback(user_id=user_id, callback_data="recurring:delete:series")
        with patch.object(bot.calendar_service, "delete_event") as delete_mock:
            await bot.recurring_scope_callback_handler(update, context)
        delete_mock.assert_called_once_with("series-1")
        print("   ✓ Single occurrence and whole series deletion use different IDs")

    print("\n6. Testing recurring edit series scope loads the series master...")
    master_event = calendar_service.CalendarEvent(
        google_event_id="series-1",
        title="Recurring Sync",
        start=datetime(2026, 5, 1, 9, 0, tzinfo=bot.LOCAL_TZ),
        end=datetime(2026, 5, 1, 10, 0, tzinfo=bot.LOCAL_TZ),
        all_day=False,
        location="Office",
        description="Series notes",
    )
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        user_id = 67894
        database.save_draft(user_id, "recurring_scope_selection", {"mode": "edit", "event": recurring_draft})
        update = create_mock_callback(user_id=user_id, callback_data="recurring:edit:series")
        with patch.object(bot.calendar_service, "get_event_by_id", return_value=master_event):
            await bot.recurring_scope_callback_handler(update, context)
        draft = database.get_draft(user_id)
        assert draft["stage"] == "editing_event"
        assert draft["data"]["google_event_id"] == "series-1"
        assert draft["data"]["date"] == "2026-05-01"
        assert draft["data"]["edit_scope"] == "series"
        print("   ✓ Whole-series edit targets the recurring master event")

    print("\n7. Testing calendar update field minimization...")
    updated = {
        "title": "New title",
        "date": "2026-05-22",
        "start_time": "09:00",
        "end_time": "10:00",
        "location": "Office",
        "notes": "Notes",
    }
    assert bot.build_calendar_update_fields(updated, {"title": "New title"}) == {"title": "New title"}
    time_update = bot.build_calendar_update_fields(updated, {"start_time": "09:15"})
    assert time_update == {"start_time": "09:15", "date": "2026-05-22", "end_time": "10:00"}
    print("   ✓ Title-only edits do not resend event time fields")


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

async def test_integration():
    """Test complete workflows."""
    print("\n" + "="*70)
    print("INTEGRATION TESTS")
    print("="*70)
    
    # Use a fresh test database for integration tests
    test_integration_db = Path(__file__).parent / "test_bot_integration.db"
    if test_integration_db.exists():
        test_integration_db.unlink()
    
    with patch.object(database, 'DB_PATH', test_integration_db):
        database.init_db()
        user_id = 12345
        
        # Workflow: Create a complete event
        print("\n1. Testing complete event creation workflow...")
        
        # Step 1: Initialize draft (simulating /add command)
        database.save_draft(user_id, "date_selection", {})
        draft = database.get_draft(user_id)
        assert draft["stage"] == "date_selection", "Should be at date_selection"
        print("   ✓ Step 1: Draft initialized for event creation")
        
        # Step 2: User selects date and period
        data = {"date": "2026-05-22"}
        database.save_draft(user_id, "period_selection", data)
        print("   ✓ Step 2: Date selected")
        
        # Step 3: User selects period and start time
        data["period"] = "morning"
        data["start_time"] = "10:00"
        database.save_draft(user_id, "end_time_selection", data)
        print("   ✓ Step 3: Period and start time selected")
        
        # Step 4: User selects end time
        data["end_time"] = "11:00"
        database.save_draft(user_id, "entered_title", data)
        print("   ✓ Step 4: End time selected")
        
        # Step 5: User enters title
        data["title"] = "Team Meeting"
        database.save_draft(user_id, "entered_location", data)
        print("   ✓ Step 5: Title entered")
        
        # Step 6: User enters location
        data["location"] = "Conference Room"
        database.save_draft(user_id, "entered_notes", data)
        print("   ✓ Step 6: Location entered")
        
        # Step 7: User enters notes and confirms
        data["notes"] = "Quarterly review"
        event_id = database.save_event(user_id, data)
        database.clear_draft(user_id)
        print(f"   ✓ Step 7: Event created with ID {event_id}")
        
        # Verify the event
        event = database.get_event(user_id, event_id)
        assert event["title"] == "Team Meeting", "Event title mismatch"
        assert event["date"] == "2026-05-22", "Event date mismatch"
        assert event["location"] == "Conference Room", "Event location mismatch"
        print("   ✓ Event verified successfully")
        
        # Test 2: Edit event workflow
        print("\n2. Testing edit event workflow...")
        
        # Start edit draft
        database.save_draft(user_id, "editing_event", {"event_id": event_id})
        draft = database.get_draft(user_id)
        assert draft["data"]["event_id"] == event_id, "Should have event_id in draft"
        print("   ✓ Edit draft initialized")
        
        # Update title
        database.update_event(event_id, {"title": "Q2 Review"})
        updated = database.get_event(user_id, event_id)
        assert updated["title"] == "Q2 Review", "Title should be updated"
        print("   ✓ Event title updated")
        
        # Test 3: List events
        print("\n3. Testing list events...")
        
        # Add another event
        event2 = {
            "title": "Lunch",
            "date": "2026-05-22",
            "start_time": "12:00",
            "end_time": "13:00",
            "location": "Cafe",
            "notes": "Team lunch",
        }
        event_id2 = database.save_event(user_id, event2)
        
        events = database.list_events(user_id, "2026-05-22")
        assert len(events) == 2, f"Should have 2 events, got {len(events)}"
        assert events[0]["start_time"] <= events[1]["start_time"], "Events should be sorted"
        print(f"   ✓ Found {len(events)} events for 2026-05-22")
        for ev in events:
            print(f"     - {ev['start_time']}: {ev['title']}")
        
        # Cleanup integration test database
        if test_integration_db.exists():
            test_integration_db.unlink()


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

def test_error_handling():
    """Test error handling in database operations."""
    print("\n" + "="*70)
    print("ERROR HANDLING TESTS")
    print("="*70)
    
    with patch.object(database, 'DB_PATH', TEST_DB_PATH):
        # Test 1: Get non-existent draft
        print("\n1. Testing get_draft() with non-existent user...")
        draft = database.get_draft(99999)
        assert draft is None, "Should return None for non-existent draft"
        print("   ✓ Returns None gracefully for non-existent draft")
        
        # Test 2: Get non-existent event
        print("\n2. Testing get_event() with non-existent event...")
        event = database.get_event(12345, 99999)
        assert event is None, "Should return None for non-existent event"
        print("   ✓ Returns None gracefully for non-existent event")
        
        # Test 3: List events for non-existent date
        print("\n3. Testing list_events() with no events...")
        events = database.list_events(12345, "2099-01-01")
        assert isinstance(events, list) and len(events) == 0, "Should return empty list"
        print("   ✓ Returns empty list for non-existent date")
        
        # Test 4: Update non-existent event
        print("\n4. Testing update_event() with non-existent event...")
        try:
            database.update_event(99999, {"title": "New Title"})
            print("   ✓ Update silently skips non-existent event (no error)")
        except Exception as e:
            print(f"   ✗ Unexpected error: {e}")
        
        # Test 5: Delete non-existent event
        print("\n5. Testing delete_event() with non-existent event...")
        try:
            database.delete_event(99999)
            print("   ✓ Delete silently skips non-existent event (no error)")
        except Exception as e:
            print(f"   ✗ Unexpected error: {e}")


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

async def main():
    """Run all tests."""
    print("\n")
    print("█" * 70)
    print("TELEGRAM ITINERARY BOT - COMPREHENSIVE TEST SUITE")
    print("█" * 70)
    
    try:
        # Setup
        setup_test_db()
        
        # Run tests
        test_database_functions()
        test_utility_functions()
        test_calendar_service_helpers()
        await test_command_handlers()
        await test_google_calendar_command_workflows()
        await test_phase5_behaviors()
        await test_integration()
        test_error_handling()
        
        # Summary
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        print("✓ All database functions working correctly")
        print("✓ All utility functions working correctly")
        print("✓ Google Calendar helper functions working correctly")
        print("✓ All command handlers working correctly")
        print("✓ Google Calendar command workflows working correctly")
        print("✓ Phase 5 behaviors working correctly")
        print("✓ Integration workflows working correctly")
        print("✓ Error handling working correctly")
        print("\n✅ ALL TESTS PASSED!")
        print("="*70 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Cleanup
        cleanup_test_db()


if __name__ == "__main__":
    asyncio.run(main())
