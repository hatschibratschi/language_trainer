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
/* List editor: the Nr. column only carries the row id for saving; headers are read-only. */
#parla-editor th:first-child, #parla-editor td:first-child { display: none; }
#parla-editor thead, #parla-editor th { pointer-events: none; }
.parla-card-note { opacity: 0.7; font-size: 0.9em; }
.parla-card-prompt { font-size: 1.8em; font-weight: 600; }
.parla-card-answer { font-size: 1.6em; color: var(--color-accent); }
/* Vocab trainer: round header above the card, spaced-out answer buttons. */
.parla-round { display: flex; flex-direction: column; gap: 8px; margin-bottom: 4px; }
.parla-round-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.parla-round-count { font-size: 1.05em; }
.parla-round-box {
  padding: 2px 12px; border-radius: 999px; font-size: 0.85em;
  border: 1px solid var(--border-color-primary); background: var(--background-fill-secondary);
}
.parla-round-score { font-size: 0.95em; opacity: 0.85; }
.parla-round-bar { height: 6px; border-radius: 999px; background: var(--border-color-primary); overflow: hidden; }
.parla-round-bar > div { height: 100%; background: var(--color-accent); transition: width 0.3s ease; }
#parla-answer-row { gap: 48px !important; margin-top: 8px; }
@media (max-width: 640px) { #parla-answer-row { gap: 24px !important; } }
.parla-vocab { font-size: 0.85em; opacity: 0.75; }

/* --- page frame: sticky header with burger menu ------------------------------ */
#parla-header {
  position: sticky; top: 0; z-index: 50; flex-wrap: nowrap !important; align-items: center;
  gap: 8px; padding: 6px 0; background: var(--body-background-fill);
}
#parla-title { min-width: 0 !important; flex: 1 1 auto !important; }
#parla-burger { font-size: 1.3em; padding: 4px 10px; }
.parla-title { font-size: 1.15em; font-weight: 600; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }

/* Slide-in menu, toggled by its "open" class. (Gradio prefixes these rules with
   .gradio-container, so selectors on <body> would never match.) */
#parla-nav {
  position: fixed !important; top: 0; left: 0; bottom: 0;
  width: min(290px, 82vw) !important; min-width: 0 !important;
  z-index: 1001; padding: 16px; gap: 8px; overflow-y: auto; flex-wrap: nowrap;
  background: var(--background-fill-primary); box-shadow: 4px 0 24px rgba(0, 0, 0, 0.25);
  transform: translateX(-110%); transition: transform 0.2s ease;
}
#parla-nav.open { transform: none; box-shadow: 0 0 0 100vmax rgba(0, 0, 0, 0.35); }
.parla-nav-item { justify-content: flex-start !important; text-align: left; font-size: 1.05em; }
.parla-nav-head { font-size: 1.4em; font-weight: 700; padding: 4px 4px 12px; }
.parla-nav-sub { font-size: 0.6em; font-weight: 400; opacity: 0.7; }

/* --- chat page ---------------------------------------------------------------- */
#parla-input, #parla-voice { flex-wrap: nowrap !important; align-items: stretch; gap: 8px; }
#parla-msg textarea { font-size: 16px; }  /* 16px: iOS doesn't zoom in when typing */
#parla-send, #parla-replay { font-size: 1.2em; }
/* Hold-to-talk / hands-free button (behaviour in voice_ui.py). No text selection or
   iOS long-press menu while holding it. */
#parla-talk {
  width: 100%; height: 100%; min-height: 48px; padding: 8px 12px; border-radius: 12px;
  font-size: 1.05em; font-weight: 600; cursor: pointer; touch-action: none;
  user-select: none; -webkit-user-select: none; -webkit-touch-callout: none;
  border: 1px solid var(--border-color-primary); background: var(--background-fill-secondary);
  color: var(--body-text-color); transition: background 0.15s, transform 0.1s;
}
#parla-talk.active { background: #e5484d; border-color: #e5484d; color: white; transform: scale(0.98); }
#parla-talk.hands-free[data-state="listening"] { background: #2f9e44; border-color: #2f9e44; color: white; }
#parla-talk[data-state="sending"], #parla-talk[data-state="starting"] { opacity: 0.7; }
#parla-talk-wrap { flex: 1 1 auto !important; }
.parla-hidden { display: none !important; }
#parla-page-chat { gap: 8px; }
#parla-burger, #parla-restart { flex: 0 0 auto !important; white-space: nowrap; }
/* The chatbot's own "Clear" only empties the screen, not the saved conversation. */
#parla-chat button[aria-label="Clear"] { display: none; }
/* Shown on the chat and lookup pages while the Mac Mini (Ollama) is off. */
.parla-mac-off {
  align-items: center; gap: 8px; padding: 8px 12px; border-radius: 12px;
  border: 1px solid var(--color-accent); background: var(--background-fill-secondary);
}
.parla-mac-off .parla-mac-text { flex: 1 1 auto; font-size: 0.9em; }
.parla-mac-off button { flex: 0 0 auto !important; white-space: nowrap; }
"""

# Gradio scopes CSS= rules to the inside of the app, so styles for the page around it
# (margins, footer) go into <head> instead.
HEAD_CSS = """
<style>
.gradio-container .main.fillable { padding-top: 4px !important; padding-bottom: 0 !important; }
@media (max-width: 640px) {
  .gradio-container .main.fillable { padding-left: 8px !important; padding-right: 8px !important; }
  .gradio-container footer { display: none !important; }
}
</style>
"""


def render_turn(turn: TutorTurn, expand_translation: bool = False) -> str:
    parts: list[str] = []

    if turn.corrections:
        lines = ["**✏️ Korrektur**"]
        for c in turn.corrections:
            lines.append(f"- ~~{c.original}~~ → **{c.corrected}**  \n  {c.explanation}")
        parts.append("\n".join(lines))

    if turn.better_phrasing:
        parts.append(f"💡 *Natürlicher:* **{turn.better_phrasing}**")

    if parts:
        parts.append("---")

    parts.append(turn.reply)

    if turn.reply_translation:
        # Hidden behind a button by default, so the learner tries to understand first.
        open_attr = " open" if expand_translation else ""
        parts.append(
            f'<details class="parla-translation"{open_attr}>'
            f"<summary>Übersetzung</summary>"
            f"<em>{html.escape(turn.reply_translation)}</em></details>"
        )

    if turn.new_vocabulary:
        # Saved to the "Standard" list automatically; shown so the learner notices.
        words = " · ".join(
            f"<b>{html.escape(v.word)}</b> – {html.escape(v.translation)}" for v in turn.new_vocabulary
        )
        parts.append(f'<div class="parla-vocab">📚 {words}</div>')

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
