from __future__ import annotations
import subprocess
import asyncio
import httpx
from typing import Optional
from .models import TriggerEvent, MeetingSummary
from .config import config


def _macos_notify(title: str, subtitle: str, body: str, sound: str = "default"):
    """Send a native macOS notification via osascript."""
    script = (
        f'display notification "{body}" '
        f'with title "{title}" '
        f'subtitle "{subtitle}" '
        f'sound name "{sound}"'
    )
    try:
        subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
    except Exception:
        pass


class Notifier:
    """Sends macOS alerts and WhatsApp DMs for triggers and summaries."""

    def __init__(self):
        self._wa_client = httpx.AsyncClient(timeout=10.0)

    async def send_trigger_alert(self, event: TriggerEvent):
        confidence_label = "high" if event.confidence >= 0.85 else "medium"
        title = f"Copilot — {event.speaker} is asking you"
        subtitle = f"Confidence: {confidence_label}"
        body = event.question[:100] if event.question else "You were mentioned"

        _macos_notify(title, subtitle, body, sound="Ping")

        if config.USER_PHONE and event.question:
            context_text = ""
            if event.context:
                context_text = "\n\n📚 Context:\n" + "\n".join(f"• {c[:150]}" for c in event.context[:3])
            suggestion_text = f"\n\n💡 Suggested: {event.suggestion[:300]}" if event.suggestion else ""
            wa_msg = (
                f"🎙 *{event.speaker}* asked:\n_{event.question}_"
                f"{context_text}{suggestion_text}"
            )
            await self._send_whatsapp(config.USER_PHONE, wa_msg)

    async def send_summary(self, summary: MeetingSummary):
        _macos_notify(
            "Copilot — Meeting ended",
            summary.title,
            f"{summary.duration_minutes} min · {len(summary.my_action_items)} action items for you",
        )

        if not config.USER_PHONE:
            return

        lines = [f"📋 *{summary.title}*", f"_{summary.duration_minutes} min_\n"]
        lines.append(f"*Summary*\n{summary.summary}\n")

        if summary.key_decisions:
            lines.append("*Key Decisions*")
            lines.extend(f"• {d}" for d in summary.key_decisions[:5])
            lines.append("")

        if summary.my_action_items:
            lines.append("*Your Action Items*")
            lines.extend(f"• {a}" for a in summary.my_action_items[:5])
            lines.append("")
        elif summary.action_items:
            lines.append("*All Action Items*")
            lines.extend(f"• {a}" for a in summary.action_items[:5])
            lines.append("")

        if summary.notion_url:
            lines.append(f"🔗 {summary.notion_url}")

        await self._send_whatsapp(config.USER_PHONE, "\n".join(lines))

    async def send_pre_brief(self, title: str, brief_text: str, starts_in_minutes: int):
        _macos_notify(
            f"Copilot — Meeting in {starts_in_minutes} min",
            title,
            "Pre-meeting brief ready",
        )
        if config.USER_PHONE:
            msg = f"⏰ *{title}* starts in {starts_in_minutes} min\n\n{brief_text}"
            await self._send_whatsapp(config.USER_PHONE, msg)

    async def send_catchup(self, title: str, catchup_text: str):
        _macos_notify("Copilot — Catch-up ready", title, "Here's what you missed")
        if config.USER_PHONE:
            msg = f"🔄 *Catch-up for {title}*\n\n{catchup_text}"
            await self._send_whatsapp(config.USER_PHONE, msg)

    async def send_weekly_digest(self, digest):
        if not config.USER_PHONE:
            return
        if isinstance(digest, dict):
            lines = ["📅 *Weekly Digest*\n"]
            if digest.get("week_summary"):
                lines.append(digest["week_summary"] + "\n")
            if digest.get("open_action_items"):
                lines.append("*Open Action Items*")
                lines.extend(f"• {a}" for a in digest["open_action_items"][:7])
                lines.append("")
            if digest.get("recurring_topics"):
                lines.append("*Recurring Topics*")
                lines.extend(f"• {t}" for t in digest["recurring_topics"][:4])
            msg = "\n".join(lines)
        else:
            msg = f"📅 *Weekly Digest*\n\n{digest}"
        await self._send_whatsapp(config.USER_PHONE, msg)

    async def _send_whatsapp(self, phone: str, message: str):
        try:
            resp = await self._wa_client.post(
                f"{config.whatsapp_bridge_url}/send",
                json={"to": phone, "message": message},
            )
            resp.raise_for_status()
        except Exception as e:
            print(f"[Notifier] WhatsApp send failed: {e}")

    async def check_whatsapp_status(self) -> str:
        try:
            resp = await self._wa_client.get(f"{config.whatsapp_bridge_url}/status")
            data = resp.json()
            return data.get("status", "unknown")
        except Exception:
            return "offline"

    async def close(self):
        await self._wa_client.aclose()
