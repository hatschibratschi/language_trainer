"""Gradio web UI for Parla."""

from __future__ import annotations

import html
import os
import re
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
from parla import lookup, speech
from parla.render import CSS, render_chat
from parla.shortcuts import SHORTCUTS_HELP, SHORTCUTS_JS
from parla.store import BOXES, DEFAULT_LIST, Settings, Store
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
    session["unspoken"] = turn.reply  # read aloud by speak_reply, if enabled
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
        s.speak,
        s.slow_speech,
        session,
        chat,
        gr.update(choices=list_choices(user), value=ALL_LISTS),
        vocab,
        user,  # remembered in this browser (localStorage)
        gr.update(choices=list_choices(user), value=ALL_LISTS),
        *trainer_view(new_trainer(), user),
    )


def save_settings(session, model, level, scenario_key, expand, speak, slow) -> None:
    if session.get("user"):
        get_store().save_settings(
            session["user"],
            Settings(
                model=model,
                level=level,
                scenario=scenario_key,
                expand_translation=expand,
                speak=speak,
                slow_speech=slow,
            ),
        )


# --- vocabulary trainer ------------------------------------------------------


def new_trainer(list_name: str = ALL_LISTS) -> dict:
    # cards: [word, translation, box] for this round; i: current card
    return {"list": list_name, "cards": [], "i": 0, "revealed": False, "missed": []}


def trainer_cards(user: str, list_name: str):
    return get_store().cards(user, None if list_name == ALL_LISTS else list_name)


def card_html(prompt: str, answer: str | None, note: str) -> str:
    answer_html = (
        f'<div class="parla-card-answer">{html.escape(answer)}</div>' if answer is not None else ""
    )
    return (
        f'<div class="parla-card"><div class="parla-card-note">{note}</div>'
        f'<div class="parla-card-prompt">{html.escape(prompt)}</div>{answer_html}</div>'
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


# --- refreshing the list pickers -----------------------------------------------

# Labels of the trainer boxes when saving looked-up words: the box is the difficulty.
BOX_CHOICES = [
    ("1 · neu / schwer", 1), ("2", 2), ("3", 3), ("4", 4), ("5", 5), ("6 · sitzt sicher", 6)
][:BOXES]


SORT_COLUMNS = {"Hinzugefügt": 0, "Italienisch": 1, "Deutsch": 2, "Liste": 3, "Fach": 4}
# Leading articles are ignored when sorting words, so "la casa" sorts under c.
_ARTICLE = re.compile(r"^(il|lo|la|i|gli|le|un|uno|una|der|die|das|ein|eine)\s+|^(l|un)['’]\s*", re.I)


def sort_key(row: list, col: int):
    value = row[col]
    if col in (0, 4):
        return (0, value or 0)
    text = str(value or "").strip()
    if col in (1, 2):
        text = _ARTICLE.sub("", text)
    return (0, text.casefold())


def filter_rows(rows: list[list], query: str, sort: str, descending: bool) -> list[list]:
    """Search in word, translation and list (case-insensitive), then sort by a column."""
    q = (query or "").strip().casefold()
    if q:
        rows = [r for r in rows if any(q in str(v or "").casefold() for v in r[1:4])]
    col = SORT_COLUMNS.get(sort, 0)
    return sorted(rows, key=lambda r: sort_key(r, col), reverse=bool(descending))


def editor_view(user: str | None, list_name: str, query: str = "", sort: str = "Hinzugefügt",
                descending: bool = True):
    """Outputs: editor table, ids of its rows (to detect edits and deletions)."""
    if not user:
        return [], []
    rows = get_store().edit_rows(user, None if list_name == ALL_LISTS else list_name)
    rows = filter_rows(rows, query, sort, descending)
    return rows, [r[0] for r in rows]


def refresh_lists(session: dict, t: dict, ed_list: str, query: str = "", sort: str = "Hinzugefügt",
                  descending: bool = True):
    """After words were added, edited or moved: update every list picker and table.
    Outputs: session, chat list + table, trainer list + trainer outputs, lookup list,
    editor list + table + ids."""
    user = session.get("user")
    choices = list_choices(user) if user else [ALL_LISTS]
    if session.get("vocab_list", ALL_LISTS) not in choices:
        session["vocab_list"] = ALL_LISTS
    if t["list"] not in choices:
        t = new_trainer()
    if ed_list not in choices:
        ed_list = ALL_LISTS
    return (
        session,
        gr.update(choices=choices, value=session.get("vocab_list", ALL_LISTS)),
        vocab_rows(session),
        gr.update(choices=choices, value=t["list"]),
        *trainer_view(t, user),
        gr.update(choices=choices[1:]),
        gr.update(choices=choices, value=ed_list),
        *editor_view(user, ed_list, query, sort, descending),
    )


# --- dictionary lookup ---------------------------------------------------------


def lookup_search(session: dict, model: str, text: str):
    """Outputs: results table (Markdown), word picker, found [word, translation] pairs."""
    queries = lookup.split_queries(text)
    if not queries:
        raise gr.Error("Bitte ein oder mehrere Wörter eingeben (getrennt durch Komma).")
    if not model:
        raise gr.Error("Kein Ollama-Modell gefunden. Läuft Ollama?")
    try:
        entries = lookup.lookup(model, PAIR, queries)
    except ValueError as err:
        raise gr.Error(str(err)) from err
    except Exception as err:  # noqa: BLE001
        raise gr.Error(f"Fehler beim Aufruf von Ollama: {err}") from err
    if not entries:
        return "Nichts gefunden.", gr.update(choices=[], value=[]), []

    words = [s.word for e in entries for s in e.senses]
    known = get_store().find_vocab(session["user"], words) if session.get("user") else {}
    md = ["| | Italienisch | Deutsch | Niveau | Beispiel |", "|---|---|---|---|---|"]
    found, choices, preselect = [], [], []
    for e in entries:
        md.append(f"| **🔎 {_md(e.query)}** | | | | |")
        for k, sense in enumerate(e.senses):
            idx = len(found)
            found.append([sense.word, sense.translation])
            where = known.get(sense.word)
            have = f" ✔︎ *schon in {_md(where[0])}, Fach {where[1]}*" if where else ""
            md.append(
                f"| | **{_md(sense.word)}**{have} | {_md(sense.translation)} | {sense.level}"
                f" | *{_md(sense.example)}* |"
            )
            choices.append((f"{sense.word} → {sense.translation} ({sense.level})", idx))
            if k == 0 and not where:
                preselect.append(idx)  # the most common meaning
    return "\n".join(md), gr.update(choices=choices, value=preselect), found


def _md(text: str) -> str:
    """Escape text for a Markdown table cell."""
    return html.escape(text or "").replace("|", "\\|").replace("\n", " ")


def lookup_save(session: dict, found: list, picked: list, list_name: str, box):
    user = session.get("user")
    if not user:
        raise gr.Error("Bitte zuerst einen Lernenden wählen.")
    items = [tuple(found[i]) for i in picked or [] if 0 <= int(i) < len(found)]
    if not items:
        raise gr.Error("Bitte mindestens ein Wort ankreuzen.")
    list_name = (list_name or "").strip() or DEFAULT_LIST
    if list_name == ALL_LISTS:
        raise gr.Error(f"„{ALL_LISTS}“ ist keine Liste – bitte eine Liste wählen.")
    added = get_store().add_vocab(user, items, list_name, int(box or 1))
    skipped = len(items) - added
    msg = f"{added} Wort/Wörter in „{list_name}“ gespeichert (Fach {box})."
    if skipped:
        msg += f" {skipped} gab es schon – unverändert (ändern unter „✏️ Listen bearbeiten“)."
    gr.Info(msg)
    return gr.update(value=[])


# --- list editor -----------------------------------------------------------------


def editor_save(session: dict, ed_list: str, ids: list, rows):
    user = session.get("user")
    if not user:
        raise gr.Error("Bitte zuerst einen Lernenden wählen.")
    rows = rows.values.tolist() if hasattr(rows, "values") else (rows or [])
    default = DEFAULT_LIST if ed_list == ALL_LISTS else ed_list
    r = get_store().apply_edits(user, list(ids or []), rows, default)
    msg = f"Gespeichert: {r.updated} geändert, {r.added} neu, {r.deleted} gelöscht."
    for err in r.errors:
        gr.Warning(err)
    gr.Info(msg)


def editor_rename(session: dict, ed_list: str, new_name: str):
    user = session.get("user")
    new_name = (new_name or "").strip()
    if not user:
        raise gr.Error("Bitte zuerst einen Lernenden wählen.")
    if ed_list == ALL_LISTS:
        raise gr.Error("Bitte oben eine einzelne Liste wählen.")
    if not new_name or new_name == ALL_LISTS:
        raise gr.Error("Bitte einen neuen Namen eingeben.")
    merged = new_name in get_store().vocab_lists(user)
    n = get_store().rename_list(user, ed_list, new_name)
    gr.Info(f"{n} Wörter " + (f"zu „{new_name}“ verschoben." if merged else f"in „{new_name}“ umbenannt."))
    return gr.update(choices=list_choices(user), value=new_name), ""


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


def send_message(text, session, model, level, scenario_key, expand, voice=False):
    text = (text or "").strip()
    if not text:
        yield "", session, *chat_view(session, expand)
        return
    voice_flag = {"voice": True} if voice else {}
    session["history"].append({"role": "user", "content": text, **voice_flag})
    session["entries"].append({"role": "user", "text": text, **voice_flag})
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


# --- voice ---------------------------------------------------------------------


def last_reply(session: dict) -> str | None:
    for e in reversed(session["entries"]):
        if e["role"] == "assistant":
            return e["turn"].reply
    return None


def voice_message(audio, session, model, level, scenario_key, expand):
    """Push-to-talk: transcribe the recording, then send it like a typed message."""
    if not audio:
        yield "", session, *chat_view(session, expand)
        return
    try:
        text = speech.transcribe(audio, PAIR.stt_language, last_reply(session))
    except speech.SpeechError as err:
        raise gr.Error(str(err)) from err
    if not text:
        gr.Warning("Nichts verstanden – bitte nochmal sprechen.")
        yield "", session, *chat_view(session, expand)
        return
    yield from send_message(text, session, model, level, scenario_key, expand, voice=True)


def speak_reply(session: dict, speak: bool, slow: bool):
    """Read the tutor's newest reply aloud (only the target-language part)."""
    text = session.pop("unspoken", None)
    if not text or not speak:
        return session, None
    try:
        wav = speech.synthesize(text, PAIR.tts_voice, speech.SLOW_SPEED if slow else 1.0)
    except speech.SpeechError as err:
        gr.Warning(str(err))  # the text answer is already there; don't fail the turn
        return session, None
    return session, speech.wav_to_numpy(wav)


def speak_last(session: dict, slow: bool):
    """🔊 button: read the last tutor reply again."""
    session["unspoken"] = last_reply(session)
    return speak_reply(session, True, slow)


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
                        speak = gr.Checkbox(value=True, label="🔊 Antworten vorlesen")
                        slow = gr.Checkbox(value=False, label="🐢 Langsam vorlesen")
                        restart = gr.Button("🔄 Neues Gespräch", variant="secondary")
                        gr.Markdown("### 📚 Meine Vokabeln")
                        vocab_list = gr.Dropdown([ALL_LISTS], value=ALL_LISTS, label="Liste")
                        vocab = gr.Dataframe(
                            headers=["Italienisch", "Deutsch"], value=[], interactive=False, wrap=True
                        )

                    with gr.Column(scale=3):
                        chatbot = gr.Chatbot(height=560, label="Gespräch", elem_id="parla-chat")
                        with gr.Row():
                            msg = gr.Textbox(
                                placeholder="Scrivi in italiano… (Enter zum Senden)",
                                show_label=False,
                                scale=5,
                                autofocus=True,
                                elem_id="parla-msg",
                            )
                            send = gr.Button("Senden", variant="primary", scale=1)
                        with gr.Row(equal_height=True):
                            # Push-to-talk: tap to record, tap stop → transcribed and sent.
                            mic = gr.Audio(
                                sources=["microphone"],
                                type="filepath",
                                label="🎙️ Sprechen (Italienisch)",
                                editable=False,
                                scale=3,
                                elem_id="parla-mic",
                            )
                            with gr.Column(scale=2, min_width=160):
                                tutor_audio = gr.Audio(
                                    label="🔊 Tutor",
                                    autoplay=True,
                                    interactive=False,
                                    format="wav",
                                    editable=False,
                                    buttons=[],
                                )
                                replay = gr.Button("🔊 Nochmal anhören", size="sm", elem_id="parla-replay")

            with gr.Tab("🗂️ Vokabeltrainer"):
                trainer = gr.State(new_trainer())
                with gr.Row():
                    tr_list = gr.Dropdown([ALL_LISTS], value=ALL_LISTS, label="Liste", scale=2)
                    tr_start = gr.Button(f"▶️ Neue Runde ({ROUND_SIZE} Wörter)", variant="primary", scale=1, elem_id="parla-start")
                tr_stats = gr.Markdown()
                tr_card = gr.HTML(card_html("", None, ""))
                with gr.Row():
                    tr_reveal = gr.Button("👀 Aufdecken", variant="primary", visible=False, elem_id="parla-reveal")
                    tr_known = gr.Button("✅ Gewusst", variant="primary", visible=False, elem_id="parla-known")
                    tr_unknown = gr.Button("❌ Nicht gewusst", variant="stop", visible=False, elem_id="parla-unknown")
                tr_missed = gr.Dataframe(
                    headers=["Deutsch", "Italienisch"],
                    value=[],
                    interactive=False,
                    wrap=True,
                    label="Nicht gewusst – schau sie dir nochmal an",
                    visible=False,
                )

            with gr.Tab("🔎 Nachschlagen"):
                lk_found = gr.State([])
                with gr.Row():
                    lk_query = gr.Textbox(
                        label="Wörter suchen (Deutsch oder Italienisch, mehrere mit Komma trennen)",
                        placeholder="z. B. Rucksack, sbrigarsi, gemütlich  (Enter zum Suchen)",
                        scale=5,
                    )
                    lk_search = gr.Button("🔎 Suchen", variant="primary", scale=1)
                lk_results = gr.Markdown()
                lk_pick = gr.CheckboxGroup([], label="Diese Wörter speichern")
                with gr.Row():
                    lk_list = gr.Dropdown(
                        [DEFAULT_LIST],
                        value=DEFAULT_LIST,
                        allow_custom_value=True,
                        label="In Liste (neuer Name = neue Liste)",
                        scale=2,
                    )
                    lk_box = gr.Radio(
                        BOX_CHOICES, value=1, label="Fach im Vokabeltrainer (Schwierigkeit)", scale=3
                    )
                lk_save = gr.Button("💾 Ausgewählte speichern", variant="primary")

            with gr.Tab("✏️ Listen bearbeiten") as ed_tab:
                ed_ids = gr.State([])
                with gr.Row(equal_height=True):
                    ed_list = gr.Dropdown([ALL_LISTS], value=ALL_LISTS, label="Liste", scale=2)
                    ed_search = gr.Textbox(
                        label="🔍 Suchen", placeholder="Wort, Übersetzung oder Liste", scale=3
                    )
                    ed_sort = gr.Dropdown(
                        list(SORT_COLUMNS), value="Hinzugefügt", label="Sortieren nach", scale=2
                    )
                    ed_desc = gr.Checkbox(value=True, label="absteigend", scale=1, min_width=100)
                gr.Markdown(
                    "Zelle anklicken zum Ändern. **Wort leeren** = löschen. **Liste** ändern = "
                    "Wort verschieben. **Fach** 1 (neu/schwer) bis 6 (sitzt). Neue Zeile über das "
                    "Zellenmenü. Erst mit **💾 Speichern** wird übernommen – vorher nicht suchen "
                    "oder umsortieren, sonst gehen die Änderungen verloren."
                )
                ed_table = gr.Dataframe(
                    headers=["Nr.", "Italienisch", "Deutsch", "Liste", "Fach"],
                    datatype=["number", "str", "str", "str", "number"],
                    value=[],
                    type="array",
                    interactive=True,
                    static_columns=[0],
                    wrap=True,
                    elem_id="parla-editor",  # CSS hides the Nr. column and locks the header
                )
                with gr.Row():
                    ed_save = gr.Button("💾 Speichern", variant="primary")
                    ed_reload = gr.Button("↩️ Änderungen verwerfen")
                with gr.Accordion("Liste umbenennen oder zusammenführen", open=False):
                    with gr.Row():
                        ed_new_name = gr.Textbox(
                            label="Neuer Name (gibt es ihn schon, werden die Listen zusammengeführt)",
                            scale=3,
                        )
                        ed_rename = gr.Button("Umbenennen", scale=1)

        with gr.Accordion("⌨️ Tastenkürzel", open=False):
            gr.Markdown(SHORTCUTS_HELP)

        settings_inputs = [session, model, level, scenario, expand]
        save_inputs = [*settings_inputs, speak, slow]
        user_outputs = [user, model, level, scenario, expand, speak, slow, session, chatbot, vocab_list, vocab, saved_user, tr_list,
                        trainer, tr_card, tr_reveal, tr_known, tr_unknown, tr_missed, tr_stats]
        chat_outputs = [session, chatbot, vocab]

        def locked(dep, fn, inputs, outputs):
            """Run fn with the user selector disabled. Otherwise switching users while the
            tutor is answering would let the late answer overwrite the new user's chat.
            Afterwards the new tutor reply (if any) is read aloud."""
            return (
                dep.then(lambda: gr.update(interactive=False), outputs=user, queue=False)
                .then(fn, inputs=inputs, outputs=outputs)
                .then(speak_reply, inputs=[session, speak, slow], outputs=[session, tutor_audio])
                .then(lambda: gr.update(interactive=True), outputs=user, queue=False)
            )  # .then also runs after errors, so the selector is always unlocked again

        # On page load: restore the user remembered by this browser. The model list is
        # refreshed every time, so it doesn't matter whether Ollama started first.
        trainer_outputs = [trainer, tr_card, tr_reveal, tr_known, tr_unknown, tr_missed, tr_stats]
        ed_view_inputs = [ed_list, ed_search, ed_sort, ed_desc]
        refresh_inputs = [session, trainer, *ed_view_inputs]
        refresh_outputs = [session, vocab_list, vocab, tr_list, *trainer_outputs, lk_list, ed_list, ed_table, ed_ids]

        locked(
            demo.load(select_user, inputs=[saved_user, model], outputs=user_outputs)
            .then(refresh_lists, refresh_inputs, refresh_outputs, queue=False),
            start_if_empty, settings_inputs, chat_outputs,
        )
        locked(
            user.input(select_user, inputs=[user, model], outputs=user_outputs)
            .then(refresh_lists, refresh_inputs, refresh_outputs, queue=False),
            start_if_empty, settings_inputs, chat_outputs,
        )

        vocab_list.input(select_list, [session, vocab_list], [session, vocab], queue=False)

        tr_list.input(trainer_select_list, [session, tr_list], trainer_outputs, queue=False)
        tr_start.click(trainer_start, [session, trainer], trainer_outputs, queue=False)
        tr_reveal.click(trainer_reveal, [session, trainer], trainer_outputs, queue=False)
        tr_known.click(lambda s, t: trainer_answer(s, t, True), [session, trainer], trainer_outputs, queue=False)
        tr_unknown.click(lambda s, t: trainer_answer(s, t, False), [session, trainer], trainer_outputs, queue=False)

        # .input (not .change) so programmatic updates from select_user don't fire these.
        for control in (model, level, expand, speak, slow):
            control.input(save_settings, inputs=save_inputs)
        expand.input(lambda s, e: render_chat(s["entries"], e), [session, expand], chatbot)
        locked(
            scenario.input(save_settings, inputs=save_inputs),
            start_conversation, settings_inputs, chat_outputs,
        )
        locked(restart.click(lambda: None, queue=False), start_conversation, settings_inputs, chat_outputs)

        for trigger in (msg.submit, send.click):
            locked(
                trigger(lambda: None, queue=False), send_message, [msg, *settings_inputs], [msg, *chat_outputs]
            )
        locked(
            mic.stop_recording(lambda: None, queue=False),
            voice_message, [mic, *settings_inputs], [msg, *chat_outputs],
        ).then(lambda: None, outputs=mic, queue=False)  # ready for the next recording
        replay.click(speak_last, [session, slow], [session, tutor_audio])

        # Dictionary lookup
        for trigger in (lk_query.submit, lk_search.click):
            trigger(lookup_search, [session, model, lk_query], [lk_results, lk_pick, lk_found])
        lk_save.click(
            lookup_save, [session, lk_found, lk_pick, lk_list, lk_box], lk_pick, queue=False
        ).success(refresh_lists, refresh_inputs, refresh_outputs, queue=False)

        # List editor (reloaded when the tab is opened: the tutor adds words meanwhile)
        ed_tab.select(refresh_lists, refresh_inputs, refresh_outputs, queue=False)
        def ed_view(s, *view):
            return editor_view(s.get("user"), *view)

        for trigger in (ed_list.input, ed_search.submit, ed_search.input, ed_sort.input, ed_desc.input, ed_reload.click):
            trigger(ed_view, [session, *ed_view_inputs], [ed_table, ed_ids], queue=False)
        ed_save.click(
            editor_save, [session, ed_list, ed_ids, ed_table], queue=False
        ).success(refresh_lists, refresh_inputs, refresh_outputs, queue=False)
        ed_rename.click(
            editor_rename, [session, ed_list, ed_new_name], [ed_list, ed_new_name], queue=False
        ).success(refresh_lists, refresh_inputs, refresh_outputs, queue=False)

    return demo


def main() -> None:
    user, password = os.environ.get("PARLA_AUTH_USER"), os.environ.get("PARLA_AUTH_PASSWORD")
    build_app().launch(
        # Host/port come from GRADIO_SERVER_NAME / GRADIO_SERVER_PORT (default 127.0.0.1:7860).
        css=CSS,
        head=SHORTCUTS_JS,
        inbrowser=os.environ.get("PARLA_OPEN_BROWSER", "1") == "1",
        auth=(user, password) if user and password else None,
    )


if __name__ == "__main__":
    main()
