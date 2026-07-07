from __future__ import annotations
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from ..core.models import CalendarEvent
from ..core.config import config


def _extract_link(text: str) -> Optional[str]:
    meet = re.search(r"https://meet\.google\.com/[a-z-]+", text or "")
    if meet:
        return meet.group(0)
    zoom = re.search(r"https://[a-z0-9.]+\.zoom\.us/j/\S+", text or "")
    if zoom:
        return zoom.group(0)
    return None


class CalendarSync:
    def __init__(self):
        self._service = None

    def authenticate(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
        creds = None
        token_path = config.GOOGLE_TOKEN_PATH
        creds_path = config.GOOGLE_CREDS_PATH

        if not Path(creds_path).exists():
            raise FileNotFoundError(
                f"Google credentials not found at {creds_path}.\n"
                "Download credentials.json from Google Cloud Console."
            )

        if Path(token_path).exists():
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
                creds = flow.run_local_server(port=0)
            Path(token_path).parent.mkdir(parents=True, exist_ok=True)
            with open(token_path, "w") as f:
                f.write(creds.to_json())

        self._service = build("calendar", "v3", credentials=creds)

    def get_today_events(self) -> List[CalendarEvent]:
        return self.get_events_in_range(hours=24)

    def get_upcoming(self, minutes: int = 60) -> List[CalendarEvent]:
        return self.get_events_in_range(minutes_from_now=0, hours=minutes / 60)

    def get_events_in_range(
        self, minutes_from_now: int = 0, hours: float = 8
    ) -> List[CalendarEvent]:
        if not self._service:
            self.authenticate()

        now = datetime.now(timezone.utc)
        time_min = (now + timedelta(minutes=minutes_from_now)).isoformat()
        time_max = (now + timedelta(hours=hours)).isoformat()

        result = (
            self._service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events = []
        for item in result.get("items", []):
            start_raw = item["start"].get("dateTime", item["start"].get("date"))
            end_raw = item["end"].get("dateTime", item["end"].get("date"))

            try:
                start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
            except ValueError:
                continue

            attendees = [
                a.get("displayName") or a.get("email", "")
                for a in item.get("attendees", [])
            ]
            description = item.get("description", "")
            location = item.get("location", "")
            combined = (description or "") + " " + (location or "")

            meet_link = _extract_link(item.get("hangoutLink", "") + " " + combined)
            platform = "unknown"
            if meet_link:
                platform = "gmeet" if "meet.google" in meet_link else "zoom"

            events.append(
                CalendarEvent(
                    id=item["id"],
                    title=item.get("summary", "Untitled Meeting"),
                    start=start_dt,
                    end=end_dt,
                    attendees=attendees,
                    description=description,
                    meet_link=meet_link,
                    platform=platform,
                )
            )
        return events

    def get_event_by_id(self, event_id: str) -> Optional[CalendarEvent]:
        if not self._service:
            self.authenticate()
        item = self._service.events().get(calendarId="primary", eventId=event_id).execute()
        if not item:
            return None
        start_dt = datetime.fromisoformat(item["start"].get("dateTime", item["start"].get("date")).replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(item["end"].get("dateTime", item["end"].get("date")).replace("Z", "+00:00"))
        attendees = [a.get("displayName") or a.get("email", "") for a in item.get("attendees", [])]
        description = item.get("description", "")
        combined = description + " " + item.get("location", "")
        meet_link = _extract_link(item.get("hangoutLink", "") + " " + combined)
        platform = "gmeet" if meet_link and "meet.google" in meet_link else "zoom" if meet_link else "unknown"
        return CalendarEvent(
            id=item["id"],
            title=item.get("summary", "Untitled Meeting"),
            start=start_dt,
            end=end_dt,
            attendees=attendees,
            description=description,
            meet_link=meet_link,
            platform=platform,
        )
