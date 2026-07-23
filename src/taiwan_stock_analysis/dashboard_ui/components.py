from __future__ import annotations

from html import escape

_TONES = {"info", "blocked", "warn", "ok"}


def esc(value) -> str:
    return escape(str(value))


def _tone(tone: str) -> str:
    return tone if tone in _TONES else "info"


def pill(text, *, tone: str = "info") -> str:
    return f'<span class="ui-pill ui-pill-{_tone(tone)}">{esc(text)}</span>'


def badge(text, *, tone: str = "info") -> str:
    return f'<span class="ui-badge ui-badge-{_tone(tone)}">{esc(text)}</span>'


def card(title, body_html: str, *, wide: bool = False) -> str:
    cls = "ui-card ui-card-wide" if wide else "ui-card"
    head = f"<h4>{esc(title)}</h4>" if title else ""
    return f'<section class="{cls}">{head}{body_html}</section>'


def copy_button(label, command) -> str:
    return f'<button type="button" class="ui-btn" data-copy="{esc(command)}">{esc(label)}</button>'
