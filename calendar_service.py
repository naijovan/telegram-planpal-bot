from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:  # pragma: no cover - depends on optional installed packages
    class _MissingHttpError(Exception):
        pass

    RefreshError = None
    Request = None
    Credentials = None
    InstalledAppFlow = None
    build = None
    HttpError = _MissingHttpError


PROJECT_DIR = Path(__file__).parent
CREDENTIALS_FILE = PROJECT_DIR / "credentials.json"
TOKEN_FILE = PROJECT_DIR / "token.json"
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
SINGAPORE_TZ = ZoneInfo("Asia/Singapore")


class CalendarSetupError(Exception):
    """Raised when local Google Calendar setup is missing or incomplete."""


class CalendarApiError(Exception):
    """Raised when Google Calendar returns an API error."""


@dataclass
class CalendarSetupStatus:
    packages_installed: bool
    credentials_file_exists: bool
    token_file_exists: bool
    token_has_required_scopes: bool

    @property
    def ready(self) -> bool:
        return (
            self.packages_installed
            and self.credentials_file_exists
            and self.token_file_exists
            and self.token_has_required_scopes
        )


@dataclass
class CalendarEvent:
    google_event_id: str
    title: str
    start: datetime | date
    end: datetime | date
    all_day: bool
    location: str = ""
    description: str = ""
    recurring_event_id: str = ""


def _google_packages_available() -> bool:
    return all([Request, Credentials, InstalledAppFlow, build])


def _token_file_scopes() -> set[str]:
    if not TOKEN_FILE.exists():
        return set()
    try:
        data = json.loads(TOKEN_FILE.read_text())
    except Exception:
        return set()

    scopes = data.get("scopes") or data.get("scope") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    return set(scopes)


def _token_file_has_required_scopes() -> bool:
    return set(SCOPES).issubset(_token_file_scopes())


def _is_insufficient_scope_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "insufficient authentication scopes" in text or "insufficientpermissions" in text


def get_setup_status() -> CalendarSetupStatus:
    return CalendarSetupStatus(
        packages_installed=_google_packages_available(),
        credentials_file_exists=CREDENTIALS_FILE.exists(),
        token_file_exists=TOKEN_FILE.exists(),
        token_has_required_scopes=_token_file_has_required_scopes(),
    )


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    without_tags = re.sub(r"<[^>]+>", "", value)
    cleaned = html.unescape(without_tags)
    return " ".join(cleaned.split())


def _load_credentials(allow_oauth: bool = False):
    if not _google_packages_available():
        raise CalendarSetupError(
            "Google Calendar packages are not installed yet. Run: pip install -r requirements.txt"
        )

    if not CREDENTIALS_FILE.exists():
        raise CalendarSetupError(
            "credentials.json was not found. Create OAuth credentials in Google Cloud, "
            "download the JSON file, and place it in this project folder."
        )

    creds = None
    if TOKEN_FILE.exists():
        if not _token_file_has_required_scopes():
            if allow_oauth:
                creds = None
            else:
                raise CalendarSetupError(
                    "token.json does not have Google Calendar write permission yet. "
                    "Run: python3 calendar_service.py auth"
                )
        else:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError as exc:
            raise CalendarSetupError(
                "Google token refresh failed. Run: python3 calendar_service.py auth"
            ) from exc
        TOKEN_FILE.write_text(creds.to_json())
        return creds

    if not allow_oauth:
        raise CalendarSetupError(
            "token.json was not found or is not valid yet. Run: python3 calendar_service.py auth"
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_FILE.write_text(creds.to_json())
    return creds


def authenticate() -> None:
    """Run the local OAuth browser flow and save token.json."""
    _load_credentials(allow_oauth=True)


def _get_service():
    creds = _load_credentials(allow_oauth=False)
    return build("calendar", "v3", credentials=creds)


def _parse_event_time(value: dict) -> tuple[datetime | date, bool]:
    if "date" in value:
        return date.fromisoformat(value["date"]), True

    raw = value.get("dateTime")
    if not raw:
        return datetime.combine(date.today(), time.min, tzinfo=SINGAPORE_TZ), False

    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SINGAPORE_TZ)
    return parsed.astimezone(SINGAPORE_TZ), False


def _local_datetime(date_text: str, time_text: str) -> datetime:
    parsed_date = date.fromisoformat(date_text)
    parsed_time = time.fromisoformat(time_text)
    return datetime.combine(parsed_date, parsed_time, tzinfo=SINGAPORE_TZ)


def _recurrence_until_utc(end_date_text: str) -> str:
    local_end = datetime.combine(
        date.fromisoformat(end_date_text),
        time(hour=23, minute=59, second=59),
        tzinfo=SINGAPORE_TZ,
    )
    return local_end.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")


def _weekday_code(value: date) -> str:
    return ["MO", "TU", "WE", "TH", "FR", "SA", "SU"][value.weekday()]


def _recurrence_rules(event_data: dict) -> list[str]:
    if not event_data.get("recurring"):
        return []

    event_date = date.fromisoformat(event_data["date"])
    recurrence_type = event_data.get("recurrence_type") or event_data.get("recurrence_frequency")
    recurrence_until = event_data.get("recurrence_until")

    if recurrence_type == "CUSTOM":
        custom_dates = sorted(set(event_data.get("recurrence_custom_dates") or []))
        custom_dates = [d for d in custom_dates if d != event_data["date"]]
        if not custom_dates:
            raise CalendarApiError("Custom recurrence needs at least one selected date.")
        start_time = time.fromisoformat(event_data["start_time"])
        values = []
        for date_text in custom_dates:
            selected_date = date.fromisoformat(date_text)
            values.append(datetime.combine(selected_date, start_time).strftime("%Y%m%dT%H%M%S"))
        return ["RDATE;TZID=Asia/Singapore:" + ",".join(values)]

    if not recurrence_until:
        raise CalendarApiError("Recurring event is missing an end date.")

    until = _recurrence_until_utc(recurrence_until)
    if recurrence_type == "DAILY":
        return [f"RRULE:FREQ=DAILY;UNTIL={until}"]
    if recurrence_type == "WEEKLY":
        return [f"RRULE:FREQ=WEEKLY;BYDAY={_weekday_code(event_date)};UNTIL={until}"]
    if recurrence_type == "MONTHLY":
        week_number = ((event_date.day - 1) // 7) + 1
        return [f"RRULE:FREQ=MONTHLY;BYDAY={week_number}{_weekday_code(event_date)};UNTIL={until}"]
    if recurrence_type == "YEARLY":
        return [f"RRULE:FREQ=YEARLY;BYMONTH={event_date.month};BYMONTHDAY={event_date.day};UNTIL={until}"]
    if recurrence_type == "WEEKDAYS":
        return [f"RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;UNTIL={until}"]

    raise CalendarApiError("Recurring event is missing a valid recurrence pattern.")


def _event_data_to_body(event_data: dict) -> dict:
    start_dt = _local_datetime(event_data["date"], event_data["start_time"])
    end_dt = _local_datetime(event_data["date"], event_data["end_time"])
    if end_dt <= start_dt:
        raise CalendarApiError("End time must be after start time.")

    body = {
        "summary": event_data.get("title") or "(No title)",
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": "Asia/Singapore",
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": "Asia/Singapore",
        },
    }
    if event_data.get("location"):
        body["location"] = event_data["location"]
    if event_data.get("notes"):
        body["description"] = event_data["notes"]
    recurrence = _recurrence_rules(event_data)
    if recurrence:
        body["recurrence"] = recurrence
    return body


def _important_tasks_body(task_date: date, description: str) -> dict:
    end_date = task_date + timedelta(days=1)
    return {
        "summary": "Important Tasks",
        "description": description,
        "start": {"date": task_date.isoformat()},
        "end": {"date": end_date.isoformat()},
    }


def create_event(event_data: dict) -> str:
    """Create a timed event in the primary Google Calendar."""
    try:
        created = (
            _get_service()
            .events()
            .insert(calendarId="primary", body=_event_data_to_body(event_data))
            .execute()
        )
    except HttpError as exc:
        if _is_insufficient_scope_error(exc):
            raise CalendarSetupError(
                "token.json does not have Google Calendar write permission yet. "
                "Run: python3 calendar_service.py auth"
            ) from exc
        raise CalendarApiError(f"Google Calendar API error: {exc}") from exc
    except Exception as exc:
        raise CalendarApiError(f"Could not create Google Calendar event: {exc}") from exc

    return created["id"]


def create_or_update_important_tasks_event(
    task_date: date,
    description: str,
    existing_event_id: str | None = None,
) -> str:
    """Create or update the one all-day Important Tasks event for a date."""
    body = _important_tasks_body(task_date, description)
    try:
        service = _get_service()
        if existing_event_id:
            saved = (
                service.events()
                .patch(calendarId="primary", eventId=existing_event_id, body=body)
                .execute()
            )
        else:
            saved = (
                service.events()
                .insert(calendarId="primary", body=body)
                .execute()
            )
    except HttpError as exc:
        if _is_insufficient_scope_error(exc):
            raise CalendarSetupError(
                "token.json does not have Google Calendar write permission yet. "
                "Run: python3 calendar_service.py auth"
            ) from exc
        raise CalendarApiError(f"Google Calendar API error: {exc}") from exc
    except Exception as exc:
        raise CalendarApiError(f"Could not save Important Tasks calendar event: {exc}") from exc

    return saved["id"]


def update_event(google_event_id: str, fields: dict) -> None:
    """Patch basic fields for an event in the primary Google Calendar."""
    body = {}
    if "title" in fields:
        body["summary"] = fields["title"] or "(No title)"
    if "location" in fields:
        body["location"] = fields["location"] or ""
    if "notes" in fields:
        body["description"] = fields["notes"] or ""
    if any(key in fields for key in ("date", "start_time", "end_time")):
        start_dt = _local_datetime(fields["date"], fields["start_time"])
        end_dt = _local_datetime(fields["date"], fields["end_time"])
        if end_dt <= start_dt:
            raise CalendarApiError("End time must be after start time.")
        body["start"] = {
            "dateTime": start_dt.isoformat(),
            "timeZone": "Asia/Singapore",
        }
        body["end"] = {
            "dateTime": end_dt.isoformat(),
            "timeZone": "Asia/Singapore",
        }

    if not body:
        return

    try:
        (
            _get_service()
            .events()
            .patch(calendarId="primary", eventId=google_event_id, body=body)
            .execute()
        )
    except HttpError as exc:
        if _is_insufficient_scope_error(exc):
            raise CalendarSetupError(
                "token.json does not have Google Calendar write permission yet. "
                "Run: python3 calendar_service.py auth"
            ) from exc
        raise CalendarApiError(f"Google Calendar API error: {exc}") from exc
    except Exception as exc:
        raise CalendarApiError(f"Could not update Google Calendar event: {exc}") from exc


def delete_event(google_event_id: str) -> None:
    """Delete an event from the primary Google Calendar."""
    try:
        (
            _get_service()
            .events()
            .delete(calendarId="primary", eventId=google_event_id)
            .execute()
        )
    except HttpError as exc:
        if _is_insufficient_scope_error(exc):
            raise CalendarSetupError(
                "token.json does not have Google Calendar write permission yet. "
                "Run: python3 calendar_service.py auth"
            ) from exc
        raise CalendarApiError(f"Google Calendar API error: {exc}") from exc
    except Exception as exc:
        raise CalendarApiError(f"Could not delete Google Calendar event: {exc}") from exc


def delete_important_tasks_event(google_event_id: str) -> None:
    """Delete the all-day Important Tasks event from the primary calendar."""
    delete_event(google_event_id)


def get_event_by_id(google_event_id: str) -> CalendarEvent:
    """Fetch one event by Google Calendar event ID."""
    try:
        item = (
            _get_service()
            .events()
            .get(calendarId="primary", eventId=google_event_id)
            .execute()
        )
    except HttpError as exc:
        raise CalendarApiError(f"Google Calendar API error: {exc}") from exc
    except Exception as exc:
        raise CalendarApiError(f"Could not reach Google Calendar: {exc}") from exc

    start_value, start_all_day = _parse_event_time(item.get("start", {}))
    end_value, end_all_day = _parse_event_time(item.get("end", {}))
    return CalendarEvent(
        google_event_id=item["id"],
        title=item.get("summary") or "(No title)",
        start=start_value,
        end=end_value,
        all_day=start_all_day or end_all_day,
        location=_clean_text(item.get("location")),
        description=_clean_text(item.get("description")),
        recurring_event_id=item.get("recurringEventId", ""),
    )


def get_events_for_day(target_day: date) -> list[CalendarEvent]:
    """Fetch primary-calendar events for one Singapore calendar day."""
    start_dt = datetime.combine(target_day, time.min, tzinfo=SINGAPORE_TZ)
    end_dt = start_dt + timedelta(days=1)

    try:
        service = _get_service()
        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=start_dt.isoformat(),
                timeMax=end_dt.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                timeZone="Asia/Singapore",
            )
            .execute()
        )
    except HttpError as exc:
        raise CalendarApiError(f"Google Calendar API error: {exc}") from exc
    except Exception as exc:
        raise CalendarApiError(f"Could not reach Google Calendar: {exc}") from exc

    events: list[CalendarEvent] = []
    for item in result.get("items", []):
        start_value, start_all_day = _parse_event_time(item.get("start", {}))
        end_value, end_all_day = _parse_event_time(item.get("end", {}))
        events.append(
            CalendarEvent(
                google_event_id=item["id"],
                title=item.get("summary") or "(No title)",
                start=start_value,
                end=end_value,
                all_day=start_all_day or end_all_day,
                location=_clean_text(item.get("location")),
                description=_clean_text(item.get("description")),
                recurring_event_id=item.get("recurringEventId", ""),
            )
        )

    return sorted(events, key=_event_sort_key)


def _event_sort_key(event: CalendarEvent) -> tuple[int, str]:
    if event.all_day:
        return (0, str(event.start))
    return (1, event.start.isoformat())


def format_events_for_telegram(events: list[CalendarEvent], day_label: str) -> str:
    if not events:
        return f"No events found for {day_label}."

    lines = [f"Google Calendar events for {day_label}:"]
    for event in events:
        if event.all_day:
            line = f"All day: {event.title}"
        else:
            start_text = event.start.strftime("%H:%M")
            end_text = event.end.strftime("%H:%M")
            line = f"{start_text} - {end_text}: {event.title}"

        details = []
        if event.location:
            details.append(f"Location: {event.location}")
        if event.description:
            details.append(f"Notes: {event.description}")
        if details:
            line = f"{line}\n  " + "\n  ".join(details)
        lines.append(line)

    return "\n".join(lines)


if __name__ == "__main__":
    authenticate()
    print("Google Calendar authentication complete. token.json has been saved.")
