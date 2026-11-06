"""Turn tutor output into chat messages (Markdown) for the UI."""

from __future__ import annotations

import html

from parla.tutor import TutorTurn

# Styles the <summary> as a small pill button; passed to launch(css=...).
CSS = """
.parla-translation summary {
  display: inline-block; cursor: pointer; list-style: none; user-select: none;
  padding: 2px 12px; border: 1px solid var(--border-color-primary);
  border-radius: 999px; font-size: 0.85em; opacity: 0.8;
}
.parla-translation summary::-webkit-details-marker { display: none; }
.parla-translation summary:hover { opacity: 1; background: var(--background-fill-secondary); }
.parla-translation[open] summary { margin-bottom: 6px; }
.parla-card {
  min-height: 200px; display: flex; flex-direction: column; justify-content: center;
  align-items: center; gap: 16px; padding: 24px; text-align: center;
  border: 1px solid var(--border-color-primary); border-radius: 16px;
  background: var(--background-fill-secondary);
}
.parla-card-note { opacity: 0.7; font-size: 0.9em; }
.parla-card-prompt { font-size: 1.8em; font-weight: 600; }
.parla-card-answer { font-size: 1.6em; color: var(--color-accent); }
"""


def render_turn(turn: TutorTurn, expand_translation: bool = False) -> str:
    parts: list[str] = []

    if turn.corrections:
        lines = ["**✏️ Korrektur**"]
        for c in turn.corrections:
            lines.append(f"- ~~{c.original}~~ → **{c.corrected}**  \n  🇩🇪 {c.explanation}")
        parts.append("\n".join(lines))

    if turn.better_phrasing:
        parts.append(f"💡 *Natürlicher:* **{turn.better_phrasing}**")

    if parts:
        parts.append("---")

    parts.append(f"🇮🇹 {turn.reply}")

    if turn.reply_translation:
        # Hidden behind a button by default, so the learner tries to understand first.
        open_attr = " open" if expand_translation else ""
        parts.append(
            f'<details class="parla-translation"{open_attr}>'
            f"<summary>🇩🇪 Übersetzung</summary>"
            f"<em>{html.escape(turn.reply_translation)}</em></details>"
        )

    return "\n\n".join(parts)


def render_chat(entries: list[dict], expand_translation: bool = False) -> list[dict[str, str]]:
    """entries: {"role": "user", "text": str} or {"role": "assistant", "turn": TutorTurn}."""
    messages = []
    for e in entries:
        if e["role"] == "user":
            prefix = "🎙️ " if e.get("voice") else ""  # spoken, shown as transcribed
            messages.append({"role": "user", "content": prefix + e["text"]})
        else:
            messages.append(
                {"role": "assistant", "content": render_turn(e["turn"], expand_translation)}
            )
    return messages
