from __future__ import annotations
from typing import Optional
from datetime import datetime
from ..core.models import MeetingSummary
from ..core.config import config


class NotionSync:
    """Creates and updates meeting pages in the Copilot Notion database."""

    DB_NAME = "Copilot — Meeting Notes"

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client:
            return self._client
        from notion_client import Client
        self._client = Client(auth=config.NOTION_TOKEN)
        return self._client

    def setup_database(self, parent_page_id: Optional[str] = None) -> str:
        """Create the Copilot database if it doesn't exist. Returns database_id."""
        client = self._get_client()

        # Check if already configured
        if config.NOTION_DATABASE_ID:
            return config.NOTION_DATABASE_ID

        if not parent_page_id:
            # Search for existing Copilot database
            results = client.search(
                query=self.DB_NAME,
                filter={"value": "database", "property": "object"},
            )
            if results["results"]:
                db_id = results["results"][0]["id"]
                print(f"[Notion] Found existing database: {db_id}")
                return db_id

            # Use the workspace root — need to find a parent page
            pages = client.search(filter={"value": "page", "property": "object"})
            if not pages["results"]:
                raise RuntimeError("Could not find a Notion page to create database in.")
            parent_page_id = pages["results"][0]["id"]

        db = client.databases.create(
            parent={"page_id": parent_page_id},
            title=[{"type": "text", "text": {"content": self.DB_NAME}}],
            properties={
                "Title": {"title": {}},
                "Date": {"date": {}},
                "Duration": {"number": {"format": "number"}},
                "Attendees": {"rich_text": {}},
                "Platform": {
                    "select": {
                        "options": [
                            {"name": "Google Meet", "color": "green"},
                            {"name": "Zoom", "color": "blue"},
                            {"name": "Other", "color": "gray"},
                        ]
                    }
                },
                "Meeting ID": {"rich_text": {}},
            },
        )
        db_id = db["id"]
        print(f"[Notion] Created database: {db_id}")
        print(f"[Notion] Add NOTION_DATABASE_ID={db_id} to your .env file")
        return db_id

    def create_meeting_page(self, summary: MeetingSummary) -> str:
        """Create a Notion page for the meeting. Returns the page URL."""
        client = self._get_client()

        if not config.NOTION_DATABASE_ID:
            db_id = self.setup_database()
        else:
            db_id = config.NOTION_DATABASE_ID

        platform_map = {"gmeet": "Google Meet", "zoom": "Zoom"}

        properties = {
            "Title": {
                "title": [{"type": "text", "text": {"content": summary.title}}]
            },
            "Meeting ID": {
                "rich_text": [{"type": "text", "text": {"content": summary.meeting_id}}]
            },
            "Duration": {"number": summary.duration_minutes},
        }

        if summary.date:
            properties["Date"] = {"date": {"start": summary.date.isoformat()}}

        if summary.attendees:
            properties["Attendees"] = {
                "rich_text": [{"type": "text", "text": {"content": ", ".join(summary.attendees[:10])}}]
            }

        children = self._build_page_content(summary)

        page = client.pages.create(
            parent={"database_id": db_id},
            properties=properties,
            children=children,
        )

        page_url = page.get("url", "")
        return page_url

    def _build_page_content(self, summary: MeetingSummary) -> list:
        blocks = []

        def heading(text: str, level: int = 2):
            return {
                "type": f"heading_{level}",
                f"heading_{level}": {
                    "rich_text": [{"type": "text", "text": {"content": text}}]
                },
            }

        def paragraph(text: str):
            return {
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": text}}]
                },
            }

        def bullet(text: str):
            return {
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": text}}]
                },
            }

        def divider():
            return {"type": "divider", "divider": {}}

        # Summary
        blocks.append(heading("Summary", 2))
        blocks.append(paragraph(summary.summary or "No summary generated."))
        blocks.append(divider())

        # Key decisions
        if summary.key_decisions:
            blocks.append(heading("Key Decisions", 2))
            for d in summary.key_decisions:
                blocks.append(bullet(d))
            blocks.append(divider())

        # My action items
        if summary.my_action_items:
            blocks.append(heading(f"Action Items for {config.USER_NAME}", 2))
            for a in summary.my_action_items:
                blocks.append({
                    "type": "to_do",
                    "to_do": {
                        "rich_text": [{"type": "text", "text": {"content": a}}],
                        "checked": False,
                    },
                })
            blocks.append(divider())

        # All action items
        if summary.action_items:
            blocks.append(heading("All Action Items", 2))
            for a in summary.action_items:
                blocks.append(bullet(a))
            blocks.append(divider())

        # Catch-up
        if summary.catchup_summary:
            blocks.append(heading("Context (Joined Late)", 2))
            blocks.append(paragraph(summary.catchup_summary))
            blocks.append(divider())

        # Metadata
        blocks.append(heading("Meeting Info", 3))
        meta_lines = [
            f"Duration: {summary.duration_minutes} minutes",
            f"Attendees: {', '.join(summary.attendees) if summary.attendees else 'Unknown'}",
            f"Meeting ID: {summary.meeting_id}",
        ]
        for line in meta_lines:
            blocks.append(paragraph(line))

        return blocks[:100]  # Notion API limit: 100 blocks per request
