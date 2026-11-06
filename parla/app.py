"""Gradio web UI for Parla."""

from __future__ import annotations

import html
import os
from functools import cache
from pathlib import Path

import gradio as gr

from parla.config import (
    DATA_DIR,
    DEFAULT_LEVEL,
    DEFAULT_MODEL,
    DEFAULT_PAIR,
    DEFAULT_SCENARIO,
    LANGUAGE_PAIRS,
    LEVELS,
    SCENARIOS,
    USERS,
)
from parla.render import CSS, render_chat
from parla.store import DEFAULT_LIST, Settings, Store
from parla.trainer import ROUND_SIZE, box_counts, next_box, pick_round
from parla.tutor import START_TOKEN, Tutor, list_models, pick_default_model

PAIR = LANGUAGE_PAIRS[DEFAULT_PAIR]
SCENARIO_CHOICES = [(s.label, s.key) for s in SCENARIOS.values()]
ALL_LISTS = "Alle Listen"


@cache
def get_store() -> Store:
    store = Store(Path(DATA_DIR) / "parla.db")
    store.ensure_users(USERS)
    return store


def new_session(user: str | None = None) -> dict:
    # history: what the model sees; entries: what the UI shows
    return {"user": user, "history": [], "entries": []}


def vocab_rows(session: dict) -> list[list[str]]:
    if not session.get("user"):
        return []
    selected = session.get("vocab_list", ALL_LISTS)
    return get_store().vocab(session["user"], None if selected == ALL_LISTS else selected)


def list_choices(user: str) -> list[str]:
    return [ALL_LISTS, *get_store().vocab_lists(user)]


def select_list(session: dict, name: str):
    session["vocab_list"] = name or ALL_LISTS
    return session, vocab_rows(session)


def chat_view(session: dict, expand: bool):
    return render_chat(session["entries"], expand), vocab_rows(session)


def ask_tutor(session: dict, model: str, level: str, scenario_key: str) -> None:
    """Call the model with the current history and record its turn in the session."""
    if not model:
        raise gr.Error("Kein Ollama-Modell gefunden. Läuft Ollama?")
    turn = Tutor(model).respond(PAIR, level, SCENARIOS[scenario_key], session["history"])
    session["history"].append({"role": "assistant", "content": turn.reply})
    session["entries"].append({"role": "assistant", "turn": turn})
    store = get_store()
    store.add_vocab(
        session["user"],
        [(v.word.strip(), v.translation.strip()) for v in turn.new_vocabulary],
        DEFAULT_LIST,
    )
    store.save_conversation(session["user"], session["history"], session["entries"])


# --- user selection ----------------------------------------------------------


def select_user(user: str | None, current_model: str | None):
    """Load a user's settings, vocabulary and last conversation into the UI."""
    user = user if user in USERS else USERS[0]
    store = get_store()

    models = list_models()
    fallback_model = pick_default_model(models, DEFAULT_MODEL) or current_model
    s = store.load_settings(
        user, Settings(model=fallback_model, level=DEFAULT_LEVEL, scenario=DEFAULT_SCENARIO)
    )
    model = s.model if s.model in models else fallback_model

    session = new_session(user)
    saved = store.load_conversation(user)
    if saved:
        session["history"], session["entries"] = saved

    chat, vocab = chat_view(session, s.expand_translation)
    return (
        gr.update(value=user),
        gr.update(choices=models or ([model] if model else []), value=model),
        s.level,
        s.scenario,
        s.expand_translation,
        session,
        chat,
        gr.update(choices=list_choices(user), value=ALL_LISTS),
        vocab,
        user,  # remembered in this browser (localStorage)
        gr.update(choices=list_choices(user), value=ALL_LISTS),
        *trainer_view(new_trainer(), user),
    )


def save_settings(session, model, level, scenario_key, expand) -> None:
    if session.get("user"):
        get_store().save_settings(
            session["user"],
            Settings(model=model, level=level, scenario=scenario_key, expand_translation=expand),
        )


# --- vocabulary trainer ------------------------------------------------------


def new_trainer(list_name: str = ALL_LISTS) -> dict:
    # cards: [word, translation, box] for this round; i: current card
    return {"list": list_name, "cards": [], "i": 0, "revealed": False, "missed": []}


def trainer_cards(user: str, list_name: str):
    return get_store().cards(user, None if list_name == ALL_LISTS else list_name)


def card_html(prompt: str, answer: str | None, note: str) -> str:
    answer_html = (
        f'<div class="parla-card-answer">🇮🇹 {html.escape(answer)}</div>' if answer is not None else ""
    )
    return (
        f'<div class="parla-card"><div class="parla-card-note">{note}</div>'
        f'<div class="parla-card-prompt">🇩🇪 {html.escape(prompt)}</div>{answer_html}</div>'
    )


def trainer_view(t: dict, user: str | None):
    """Outputs: trainer state, card, reveal/known/unknown buttons, missed table, box stats."""
    counts = box_counts(trainer_cards(user, t["list"])) if user else {}
    stats = " · ".join(f"Fach {b}: **{n}**" for b, n in counts.items())
    cards, i = t["cards"], t["i"]
    in_round = 0 < len(cards) and i < len(cards)
    if in_round:
        word, translation, box = cards[i]
        card = card_html(
            translation, word if t["revealed"] else None, f"Karte {i + 1} / {len(cards)} · Fach {box}"
        )
    elif cards:  # round finished
        known = len(cards) - len(t["missed"])
        card = (
            f'<div class="parla-card"><div class="parla-card-prompt">'
            f"🎉 Runde fertig: {known} von {len(cards)} gewusst</div>"
            + ("" if t["missed"] else '<div class="parla-card-note">Alles gewusst – bravissimo!</div>')
            + "</div>"
        )
    else:
        card = (
            '<div class="parla-card"><div class="parla-card-note">'
            f"Wähle eine Liste und starte eine Runde mit {ROUND_SIZE} Wörtern.</div></div>"
        )
    return (
        t,
        card,
        gr.update(visible=in_round and not t["revealed"]),
        gr.update(visible=in_round and t["revealed"]),
        gr.update(visible=in_round and t["revealed"]),
        gr.update(value=t["missed"], visible=bool(cards) and not in_round and bool(t["missed"])),
        stats,
    )


def trainer_select_list(session: dict, list_name: str):
    return trainer_view(new_trainer(list_name or ALL_LISTS), session.get("user"))


def trainer_start(session: dict, t: dict):
    user = session.get("user")
    t = new_trainer(t["list"])
    if user:
        t["cards"] = [list(c) for c in pick_round(trainer_cards(user, t["list"]))]
        if not t["cards"]:
            gr.Info("Diese Liste ist leer.")
    return trainer_view(t, user)


def trainer_reveal(session: dict, t: dict):
    t["revealed"] = True
    return trainer_view(t, session.get("user"))


def trainer_answer(session: dict, t: dict, known: bool):
    user = session.get("user")
    if user and t["i"] < len(t["cards"]) and t["revealed"]:
        word, translation, box = t["cards"][t["i"]]
        get_store().set_box(user, word, next_box(box, known))
        if not known:
            t["missed"].append([translation, word])
        t["i"] += 1
        t["revealed"] = False
    return trainer_view(t, user)


# --- conversation ------------------------------------------------------------


def start_conversation(session, model, level, scenario_key, expand):
    session = {**new_session(session["user"]), "vocab_list": session.get("vocab_list", ALL_LISTS)}
    get_store().save_conversation(session["user"], [], [])
    yield session, *chat_view(session, expand)
    session["history"].append({"role": "user", "content": START_TOKEN})
    try:
        ask_tutor(session, model, level, scenario_key)
    except gr.Error:
        raise
    except Exception as err:  # noqa: BLE001 – surface any backend error in the UI
        raise gr.Error(f"Fehler beim Aufruf von Ollama: {err}") from err
    yield session, *chat_view(session, expand)


def start_if_empty(session, model, level, scenario_key, expand):
    """After switching users: continue their conversation, or open a new one."""
    if session["entries"]:
        yield session, *chat_view(session, expand)
    else:
        yield from start_conversation(session, model, level, scenario_key, expand)


def send_message(text, session, model, level, scenario_key, expand):
    text = (text or "").strip()
    if not text:
        yield "", session, *chat_view(session, expand)
        return
    session["history"].append({"role": "user", "content": text})
    session["entries"].append({"role": "user", "text": text})
    # Show the learner's message immediately while the model is thinking.
    yield "", session, *chat_view(session, expand)
    try:
        ask_tutor(session, model, level, scenario_key)
    except Exception as err:  # noqa: BLE001
        session["history"].pop()
        session["entries"].pop()
        if isinstance(err, gr.Error):
            raise
        raise gr.Error(f"Fehler beim Aufruf von Ollama: {err}") from err
    yield "", session, *chat_view(session, expand)


# --- layout ------------------------------------------------------------------


def build_app() -> gr.Blocks:
    get_store()  # create the database and users at startup

    with gr.Blocks(title="Parla – Sprachtrainer") as demo:
        session = gr.State(new_session())
        saved_user = gr.BrowserState(None, storage_key="parla_user")

        gr.Markdown(f"# 🇮🇹 Parla – dein Sprachtrainer\n*{PAIR.label}*")
        user = gr.Dropdown(USERS, value=USERS[0], label="👤 Wer lernt?")

        with gr.Tabs():
            with gr.Tab("💬 Gespräch"):
                with gr.Row():
                    with gr.Column(scale=1, min_width=260):
                        model = gr.Dropdown(choices=[], label="Modell", allow_custom_value=True)
                        level = gr.Radio(list(LEVELS), value=DEFAULT_LEVEL, label="Niveau (GER)")
                        scenario = gr.Dropdown(SCENARIO_CHOICES, value=DEFAULT_SCENARIO, label="Szenario")
                        expand = gr.Checkbox(value=False, label="Übersetzungen immer aufklappen")
                        restart = gr.Button("🔄 Neues Gespräch", variant="secondary")
                        gr.Markdown("### 📚 Meine Vokabeln")
                        vocab_list = gr.Dropdown([ALL_LISTS], value=ALL_LISTS, label="Liste")
                        vocab = gr.Dataframe(
                            headers=["Italienisch", "Deutsch"], value=[], interactive=False, wrap=True
                        )

                    with gr.Column(scale=3):
                        chatbot = gr.Chatbot(height=560, label="Gespräch")
                        with gr.Row():
                            msg = gr.Textbox(
                                placeholder="Scrivi in italiano… (Enter zum Senden)",
                                show_label=False,
                                scale=5,
                                autofocus=True,
                            )
                            send = gr.Button("Senden", variant="primary", scale=1)

            with gr.Tab("🗂️ Vokabeltrainer"):
                trainer = gr.State(new_trainer())
                with gr.Row():
                    tr_list = gr.Dropdown([ALL_LISTS], value=ALL_LISTS, label="Liste", scale=2)
                    tr_start = gr.Button(f"▶️ Neue Runde ({ROUND_SIZE} Wörter)", variant="primary", scale=1)
                tr_stats = gr.Markdown()
                tr_card = gr.HTML(card_html("", None, ""))
                with gr.Row():
                    tr_reveal = gr.Button("👀 Aufdecken", variant="primary", visible=False)
                    tr_known = gr.Button("✅ Gewusst", variant="primary", visible=False)
                    tr_unknown = gr.Button("❌ Nicht gewusst", variant="stop", visible=False)
                tr_missed = gr.Dataframe(
                    headers=["Deutsch", "Italienisch"],
                    value=[],
                    interactive=False,
                    wrap=True,
                    label="Nicht gewusst – schau sie dir nochmal an",
                    visible=False,
                )

        settings_inputs = [session, model, level, scenario, expand]
        user_outputs = [user, model, level, scenario, expand, session, chatbot, vocab_list, vocab, saved_user, tr_list,
                        trainer, tr_card, tr_reveal, tr_known, tr_unknown, tr_missed, tr_stats]
        chat_outputs = [session, chatbot, vocab]

        def locked(dep, fn, inputs, outputs):
            """Run fn with the user selector disabled. Otherwise switching users while the
            tutor is answering would let the late answer overwrite the new user's chat."""
            return (
                dep.then(lambda: gr.update(interactive=False), outputs=user, queue=False)
                .then(fn, inputs=inputs, outputs=outputs)
                .then(lambda: gr.update(interactive=True), outputs=user, queue=False)
            )  # .then also runs after errors, so the selector is always unlocked again

        # On page load: restore the user remembered by this browser. The model list is
        # refreshed every time, so it doesn't matter whether Ollama started first.
        locked(
            demo.load(select_user, inputs=[saved_user, model], outputs=user_outputs),
            start_if_empty, settings_inputs, chat_outputs,
        )
        locked(
            user.input(select_user, inputs=[user, model], outputs=user_outputs),
            start_if_empty, settings_inputs, chat_outputs,
        )

        vocab_list.input(select_list, [session, vocab_list], [session, vocab], queue=False)

        trainer_outputs = [trainer, tr_card, tr_reveal, tr_known, tr_unknown, tr_missed, tr_stats]
        tr_list.input(trainer_select_list, [session, tr_list], trainer_outputs, queue=False)
        tr_start.click(trainer_start, [session, trainer], trainer_outputs, queue=False)
        tr_reveal.click(trainer_reveal, [session, trainer], trainer_outputs, queue=False)
        tr_known.click(lambda s, t: trainer_answer(s, t, True), [session, trainer], trainer_outputs, queue=False)
        tr_unknown.click(lambda s, t: trainer_answer(s, t, False), [session, trainer], trainer_outputs, queue=False)

        # .input (not .change) so programmatic updates from select_user don't fire these.
        for control in (model, level, expand):
            control.input(save_settings, inputs=settings_inputs)
        expand.input(lambda s, e: render_chat(s["entries"], e), [session, expand], chatbot)
        locked(
            scenario.input(save_settings, inputs=settings_inputs),
            start_conversation, settings_inputs, chat_outputs,
        )
        locked(restart.click(lambda: None, queue=False), start_conversation, settings_inputs, chat_outputs)

        for trigger in (msg.submit, send.click):
            locked(
                trigger(lambda: None, queue=False), send_message, [msg, *settings_inputs], [msg, *chat_outputs]
            )

    return demo


def main() -> None:
    user, password = os.environ.get("PARLA_AUTH_USER"), os.environ.get("PARLA_AUTH_PASSWORD")
    build_app().launch(
        # Host/port come from GRADIO_SERVER_NAME / GRADIO_SERVER_PORT (default 127.0.0.1:7860).
        css=CSS,
        inbrowser=os.environ.get("PARLA_OPEN_BROWSER", "1") == "1",
        auth=(user, password) if user and password else None,
    )


if __name__ == "__main__":
    main()
