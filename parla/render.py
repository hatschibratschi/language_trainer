"""Turn tutor output into chat messages (Markdown) for the UI."""

from __future__ import annotations

import html

from parla.tutor import TutorTurn

# Passed to launch(css=...); THEME in theme.py sets the colours and shapes.
CSS = """
.parla-translation summary {
  display: inline-block; cursor: pointer; list-style: none; user-select: none;
  padding: 3px 12px; border-radius: 999px; font-size: 0.85em; font-weight: 600;
  background: color-mix(in srgb, var(--color-accent) 10%, transparent); color: var(--color-accent);
}
.dark .parla-translation summary { background: rgba(255, 216, 102, 0.14); color: #ffd866; }
.parla-translation summary::-webkit-details-marker { display: none; }
.parla-translation summary:hover { filter: brightness(1.08); }
.parla-translation[open] summary { margin-bottom: 6px; }
.parla-vocab { font-size: 0.85em; opacity: 0.75; }
/* List editor: the Nr. column only carries the row id for saving; headers are read-only. */
#parla-editor th:first-child, #parla-editor td:first-child { display: none; }
#parla-editor thead, #parla-editor th { pointer-events: none; }
.parla-hidden { display: none !important; }

/* --- buttons ------------------------------------------------------------------- */
button.primary, button.secondary, button.stop { font-weight: 700; }
button.primary:active, button.secondary:active, button.stop:active { transform: scale(0.97); }

/* --- app bar ------------------------------------------------------------------- */
#parla-header {
  position: sticky; top: 0; z-index: 50; flex-wrap: nowrap !important; align-items: center;
  gap: 8px; padding: 10px 0; background: transparent;
}
#parla-header::before {  /* frosted strip so content scrolls under it nicely */
  content: ""; position: absolute; inset: 0 -100vw; z-index: -1;
  background: color-mix(in srgb, var(--body-background-fill) 85%, transparent);
  backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--border-color-primary);
}
#parla-title { min-width: 0 !important; flex: 1 1 auto !important; }
.parla-title { font-family: "Patrick Hand", "Comic Sans MS", cursive; font-size: 1.75em; line-height: 1.1;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
#parla-restart { flex: 0 0 auto !important; white-space: nowrap; height: 40px; padding: 0 16px; }
#parla-scenario { flex: 0 0 auto !important; width: 9.5em !important; }
#parla-scenario > div > .wrap { min-height: 0; height: 40px; padding: 0 8px 0 14px; border-radius: 999px; }
#parla-scenario .wrap-inner { padding: 0; }
#parla-scenario input { min-width: 0; height: auto; padding: 0 18px 0 0; margin: 0; font-weight: 700;
  text-align: left; text-overflow: ellipsis; }
/* Gradio lays the arrow over the text field and lets clicks through (pointer-events: none),
   so a click on the arrow opens the list too. Only move it to the right edge. */
#parla-scenario .icon-wrap { right: 0; width: 16px; }
@media (max-width: 899px) {
  #parla-restart { padding: 0 10px; }
  #parla-scenario { width: 8.5em !important; }
}
/* Day/night switch (behaviour in theme.py); the icon shows what you switch to. */
#parla-theme-wrap { flex: 0 0 auto !important; width: fit-content !important; }
#parla-theme-btn {
  width: 40px; height: 40px; border-radius: 999px; cursor: pointer; font-size: 1.1em; padding: 0;
  border: 1px solid var(--button-secondary-border-color); background: var(--button-secondary-background-fill);
  box-shadow: var(--button-secondary-shadow); transition: transform 0.12s ease;
}
#parla-theme-btn::before { content: "🌙"; }
.dark #parla-theme-btn::before { content: "☀️"; }
#parla-theme-btn:active { transform: scale(0.92); }

/* --- navigation: bottom tab bar on phones, sidebar on desktop -------------------- */
#parla-nav {
  position: fixed !important; z-index: 1000; flex-wrap: nowrap !important; min-width: 0 !important;
  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
}
.parla-nav-item {
  background: transparent !important; border: none !important; box-shadow: none !important;
  color: var(--body-text-color-subdued) !important; font-weight: 700 !important;
  min-width: 0 !important; transform: none !important;
}
.parla-nav-item:hover { color: var(--body-text-color) !important; }
.parla-nav-item.primary {
  color: var(--color-accent) !important;
  background: color-mix(in srgb, var(--color-accent) 13%, transparent) !important;
}
.dark .parla-nav-item.primary { color: #ffd866 !important; background: rgba(255, 216, 102, 0.14) !important; }
.parla-nav-head { font-family: "Patrick Hand", "Comic Sans MS", cursive; font-size: 2em; padding: 4px 10px 16px; }
.parla-nav-sub { font-family: var(--font); font-size: 0.42em; opacity: 0.65; }

@media (max-width: 899px) {
  #parla-nav {
    top: auto; left: 10px; right: 10px; bottom: calc(10px + env(safe-area-inset-bottom));
    width: auto !important; height: 66px; flex-direction: row !important; gap: 2px; padding: 6px;
    border-radius: 24px; border: 1px solid var(--border-color-primary);
    background: color-mix(in srgb, var(--background-fill-primary) 88%, transparent);
    box-shadow: 0 8px 30px rgba(43, 58, 85, 0.16);
  }
  .dark #parla-nav { box-shadow: 0 8px 30px rgba(0, 0, 0, 0.4); }
  #parla-nav > div:first-child { display: none !important; }  /* the "Parla" heading */
  .parla-nav-item {
    display: block !important; flex: 1 1 0 !important; height: 100%; padding: 4px 0 !important;
    border-radius: 18px !important; white-space: pre-line; text-align: center;
    font-size: 0.72em !important; line-height: 1.25 !important;
  }
  .parla-nav-item::first-line { font-size: 1.75em; line-height: 1.3; }
}
@media (min-width: 900px) {
  #parla-nav {
    top: 0; bottom: 0; left: 0; width: 236px !important; flex-direction: column !important;
    gap: 4px; padding: 20px 14px; overflow-y: auto;
    background: color-mix(in srgb, var(--background-fill-primary) 80%, transparent);
    border-right: 1px solid var(--border-color-primary);
  }
  .parla-nav-item {
    justify-content: flex-start !important; text-align: left; white-space: normal;
    padding: 11px 14px !important; border-radius: 14px !important; font-size: 1em !important;
  }
  .parla-nav-item:hover:not(.primary) { background: var(--background-fill-secondary) !important; }
}

/* --- chat page ------------------------------------------------------------------- */
#parla-page-chat { gap: 8px; }
/* Bubbles float on the page; your messages highlighted, the tutor's on paper. */
#parla-chat { background: transparent !important; border: none !important; box-shadow: none !important; }
#parla-chat .bot, #parla-chat .user {
  border: none !important; border-radius: 20px !important; padding: 10px 16px !important;
  box-shadow: 0 1px 2px rgba(43, 58, 85, 0.06), 0 4px 14px rgba(43, 58, 85, 0.07) !important;
}
#parla-chat .bot { background: var(--background-fill-primary) !important; border-bottom-left-radius: 6px !important; }
#parla-chat .user { border-bottom-right-radius: 6px !important; }
.dark #parla-chat .bot, .dark #parla-chat .user { box-shadow: 0 4px 14px rgba(0, 0, 0, 0.18) !important; }
#parla-chat del { color: #e5484d; text-decoration-thickness: 2px; }
.dark #parla-chat del { color: #ff9aa0; }
/* The chatbot's own "Clear" only empties the screen, not the saved conversation. */
#parla-chat button[aria-label="Clear"] { display: none; }
/* Copy buttons: quiet until you point at them. */
#parla-chat .message-buttons { opacity: 0.35; transition: opacity 0.15s; }
#parla-chat .message-buttons:hover { opacity: 1; }
#parla-chat .message-buttons .icon-button { border: none !important; background: transparent !important; }

/* Composer: one floating card with the voice button and the text field. */
#parla-composer {
  gap: 8px; padding: 10px; border-radius: 26px; border: 1px solid var(--border-color-primary);
  background: var(--background-fill-primary);
  box-shadow: 0 2px 6px rgba(43, 58, 85, 0.06), 0 10px 30px rgba(43, 58, 85, 0.08);
}
.dark #parla-composer { box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25); }
#parla-input, #parla-voice { flex-wrap: nowrap !important; align-items: stretch; gap: 8px; }
#parla-msg textarea {
  font-size: 16px;  /* 16px: iOS doesn't zoom in when typing */
  border-radius: 22px !important; padding: 12px 16px !important; min-height: 48px;
  background: var(--background-fill-secondary) !important; border-color: transparent !important;
}
#parla-msg textarea:focus { border-color: var(--input-border-color-focus) !important; }
#parla-send, #parla-replay {
  width: 48px; height: 48px; min-width: 48px !important; padding: 0 !important;
  border-radius: 999px !important; font-size: 1.2em; flex: 0 0 48px !important;
}
/* Hold-to-talk / hands-free button (behaviour in voice_ui.py). No text selection or
   iOS long-press menu while holding it. */
#parla-talk-wrap { flex: 1 1 auto !important; }
#parla-talk-wrap .html-container { padding: 0 !important; height: 100%; }
#parla-talk-wrap .prose { height: 100%; }
#parla-talk {
  width: 100%; height: 100%; min-height: 48px; padding: 8px 16px; border-radius: 999px; border: none;
  font-size: 1.02em; font-weight: 700; cursor: pointer; touch-action: none;
  user-select: none; -webkit-user-select: none; -webkit-touch-callout: none;
  background: color-mix(in srgb, var(--color-accent) 12%, transparent); color: var(--color-accent);
  transition: background 0.15s, transform 0.12s, color 0.15s;
}
.dark #parla-talk { background: rgba(255, 216, 102, 0.14); color: #ffd866; }
#parla-talk.active, .dark #parla-talk.active {
  background: #e5484d; color: white; transform: scale(0.98);
  box-shadow: 0 0 0 6px rgba(229, 72, 77, 0.2);
}
#parla-talk.hands-free[data-state="listening"], .dark #parla-talk.hands-free[data-state="listening"] {
  background: #2fb171; color: white; box-shadow: 0 0 0 6px rgba(47, 177, 113, 0.2);
}
#parla-talk[data-state="sending"], #parla-talk[data-state="starting"] { opacity: 0.7; }

/* Shown on the chat and lookup pages while the Mac Mini (Ollama) is off. */
.parla-mac-off {
  align-items: center; gap: 10px; padding: 10px 12px 10px 16px; border-radius: 18px; border: none;
  background: #fff4d6; color: #6b4e00;
}
.dark .parla-mac-off { background: rgba(255, 216, 102, 0.14); color: #ffe7a3; }
.parla-mac-off .parla-mac-text { flex: 1 1 auto; font-size: 0.88em; }
.parla-mac-off button { flex: 0 0 auto !important; white-space: nowrap; }

/* --- vocab trainer ----------------------------------------------------------------- */
/* Card: a lined index card by day, a chalk-drawn card by night. */
.parla-card {
  min-height: 240px; display: flex; flex-direction: column; justify-content: center;
  align-items: center; gap: 16px; padding: 52px 24px 32px; text-align: center; border-radius: 24px;
  box-shadow: 0 2px 6px rgba(43, 58, 85, 0.06), 0 14px 36px rgba(43, 58, 85, 0.10);
  background:
    linear-gradient(#ffffff 0 32px, rgba(229, 72, 77, 0.55) 32px 34px, transparent 34px),
    repeating-linear-gradient(#ffffff 0 31px, #dde8f6 31px 32px);
}
.dark .parla-card {
  border: 1.5px dashed rgba(243, 241, 231, 0.35); box-shadow: 0 14px 36px rgba(0, 0, 0, 0.22);
  background: rgba(255, 255, 255, 0.05);
}
.parla-card-note { opacity: 0.7; font-size: 0.9em; }
.parla-card-prompt { font-family: "Patrick Hand", "Comic Sans MS", cursive; font-size: 2.3em; line-height: 1.2; }
.parla-card-answer { font-family: "Patrick Hand", "Comic Sans MS", cursive; font-size: 2em; color: #2f6fd6; }
.dark .parla-card-answer { color: #ffd866; }
.parla-round { display: flex; flex-direction: column; gap: 10px; margin-bottom: 4px; }
.parla-round-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.parla-round-count { font-size: 1em; }
.parla-round-box {
  padding: 3px 12px; border-radius: 999px; font-size: 0.8em; font-weight: 800;
  background: #fff1b8; color: #6b4e00;
}
.dark .parla-round-box { background: #ffd866; color: #17302a; }
.parla-round-score { font-size: 0.95em; opacity: 0.85; }
.parla-round-bar { height: 8px; border-radius: 999px; overflow: hidden;
  background: color-mix(in srgb, var(--body-text-color) 10%, transparent); }
.parla-round-bar > div { height: 100%; border-radius: 999px; background: #2fb171; transition: width 0.35s ease; }
#parla-answer-row { gap: 12px !important; margin-top: 12px; }
@media (max-width: 640px) { #parla-trainer-top { flex-direction: column !important; align-items: stretch; } }
#parla-start { min-height: 48px; }
#parla-reveal, #parla-known, #parla-unknown { min-height: 56px; font-size: 1.08em; }
#parla-known { background: #2fb171 !important; border-color: #2fb171 !important; color: white !important;
  box-shadow: 0 2px 8px rgba(47, 177, 113, 0.32) !important; }
.dark #parla-known { background: #5fd69a !important; border-color: #5fd69a !important; color: #10291f !important; }
"""

# Gradio scopes CSS= rules to the inside of the app, so styles for the page around it
# (margins, footer, room for the tab bar / sidebar) go into <head> instead.
# --parla-chat-offset: everything on the chat page that isn't the chat itself.
HEAD_CSS = """
<style>
:root { --parla-chat-offset: 252px; }
.gradio-container footer { display: none !important; }
.gradio-container .main.fillable { padding-top: 0 !important; padding-bottom: 0 !important; }
@media (max-width: 899px) {
  :root { --parla-chat-offset: calc(318px + env(safe-area-inset-bottom)); }
  .gradio-container .main.fillable {
    padding-left: 10px !important; padding-right: 10px !important;
    padding-bottom: calc(86px + env(safe-area-inset-bottom)) !important;
  }
}
@media (min-width: 900px) {
  .gradio-container { padding-left: 236px !important; }
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
