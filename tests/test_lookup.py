import json

from parla.config import LANGUAGE_PAIRS
from parla.lookup import build_prompt, lookup, split_queries

PAIR = LANGUAGE_PAIRS["de-it"]


class FakeClient:
    def __init__(self, content: str):
        self.content = content
        self.calls: list[dict] = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return {"message": {"content": self.content}}


def test_split_queries():
    assert split_queries(" Rucksack, sbrigarsi;\nrucksack\n\n gemütlich ") == ["Rucksack", "sbrigarsi", "gemütlich"]
    assert split_queries("") == []


def test_lookup_parses_and_dedupes_senses():
    payload = {"entries": [
        {"query": "Rucksack", "senses": [
            {"word": "lo zaino", "translation": "der Rucksack", "level": "A2", "example": "Ho uno zaino."},
            {"word": " lo zaino ", "translation": "Rucksack", "level": "A2"},
            {"word": "lo zainetto", "translation": "der kleine Rucksack", "level": "B1"},
        ]},
        {"query": "nix", "senses": [{"word": " ", "translation": "", "level": "A1"}]},
    ]}
    client = FakeClient(json.dumps(payload))
    entries = lookup("m", PAIR, ["Rucksack", "nix"], client=client)
    assert [e.query for e in entries] == ["Rucksack"]
    assert [s.word for s in entries[0].senses] == ["lo zaino", "lo zainetto"]
    assert client.calls[0]["messages"][1]["content"] == "Rucksack\nnix"
    assert client.calls[0]["think"] is False


def test_prompt_names_languages():
    p = build_prompt(PAIR)
    assert "Italian" in p and "German" in p and "CEFR" in p
