import json

import pytest

from parla.config import LANGUAGE_PAIRS, SCENARIOS
from parla.render import render_chat, render_turn
from parla.tutor import (
    START_TOKEN,
    Correction,
    Tutor,
    TutorTurn,
    build_system_prompt,
    pick_default_model,
)

PAIR = LANGUAGE_PAIRS["de-it"]


class FakeClient:
    def __init__(self, content: str):
        self.content = content
        self.calls: list[dict] = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return {"message": {"content": self.content}}


def test_system_prompt_contains_level_and_scenario():
    prompt = build_system_prompt(PAIR, "A1", SCENARIOS["bar"])
    assert "A1" in prompt
    assert "barista" in prompt
    assert START_TOKEN in prompt
    assert "Italian" in prompt and "German" in prompt


def test_respond_parses_structured_output():
    payload = {
        "corrections": [
            {"original": "Io sono andato in Roma", "corrected": "Sono andato a Roma",
             "explanation": "Vor Städten steht 'a'."}
        ],
        "better_phrasing": None,
        "reply": "Che bello! Ti è piaciuta Roma?",
        "reply_translation": "Wie schön! Hat dir Rom gefallen?",
        "new_vocabulary": [{"word": "piacere", "translation": "gefallen"}],
    }
    client = FakeClient(json.dumps(payload))
    turn = Tutor("x", client=client).respond(
        PAIR, "A2", SCENARIOS["free"], [{"role": "user", "content": "Io sono andato in Roma"}]
    )
    assert turn.corrections[0].corrected == "Sono andato a Roma"
    assert turn.new_vocabulary[0].word == "piacere"
    call = client.calls[0]
    assert call["messages"][0]["role"] == "system"
    assert call["messages"][-1]["content"] == "Io sono andato in Roma"
    assert call["think"] is False
    assert "properties" in call["format"]


def test_respond_falls_back_on_invalid_json():
    turn = Tutor("x", client=FakeClient("Ciao!")).respond(PAIR, "A1", SCENARIOS["free"], [])
    assert turn.reply == "Ciao!"
    assert turn.corrections == []


def test_render_turn_with_and_without_translation():
    turn = TutorTurn(
        corrections=[Correction(original="la problema", corrected="il problema",
                                explanation="'problema' ist maskulin.")],
        reply="Nessun problema!",
        reply_translation="Kein Problem!",
    )
    collapsed = render_turn(turn)
    assert "~~la problema~~" in collapsed and "**il problema**" in collapsed
    assert '<details class="parla-translation">' in collapsed
    assert "<summary>🇩🇪 Übersetzung</summary>" in collapsed
    assert "Kein Problem!" in collapsed
    assert '<details class="parla-translation" open>' in render_turn(turn, expand_translation=True)


def test_render_turn_escapes_translation_html():
    turn = TutorTurn(reply="Ciao", reply_translation="<b>Hallo</b> & so")
    assert "&lt;b&gt;Hallo&lt;/b&gt; &amp; so" in render_turn(turn)


def test_render_chat_roles():
    entries = [
        {"role": "assistant", "turn": TutorTurn(reply="Ciao!", reply_translation="Hallo!")},
        {"role": "user", "text": "Ciao"},
    ]
    msgs = render_chat(entries)
    assert [m["role"] for m in msgs] == ["assistant", "user"]
    assert msgs[1]["content"] == "Ciao"


@pytest.mark.parametrize(
    "available, requested, expected",
    [
        (["qwen3:14b", "gemma3:27b"], None, "gemma3:27b"),
        (["qwen3:14b"], None, "qwen3:14b"),
        (["llama3:8b"], None, "llama3:8b"),
        ([], None, None),
        (["qwen3:14b"], "mymodel", "mymodel"),
    ],
)
def test_pick_default_model(available, requested, expected):
    assert pick_default_model(available, requested) == expected


def test_render_chat_marks_spoken_messages():
    msgs = render_chat([{"role": "user", "text": "Ciao"}, {"role": "user", "text": "Ciao", "voice": True}])
    assert [m["content"] for m in msgs] == ["Ciao", "🎙️ Ciao"]
