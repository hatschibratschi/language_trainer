"""Dictionary lookup: ask the model for several meanings of each searched word."""

from __future__ import annotations

import re
from typing import Literal

import ollama
from pydantic import BaseModel, Field, ValidationError

from parla.config import OLLAMA_HOST, LanguagePair
from parla.tutor import ChatClient, chat_json

MAX_QUERIES = 10
CEFR = ("A1", "A2", "B1", "B2", "C1", "C2")


class Sense(BaseModel):
    word: str = Field(description="Word or phrase in the target language (base form, article for nouns)")
    translation: str = Field(description="Translation in the learner's native language")
    level: Literal["A1", "A2", "B1", "B2", "C1", "C2"] = Field(
        description="CEFR level at which a learner usually meets this word in this meaning"
    )
    example: str = Field(default="", description="Short example sentence in the target language")


class LookupEntry(BaseModel):
    query: str = Field(description="The searched word, copied verbatim")
    senses: list[Sense] = Field(description="2-4 different translations or meanings")


class LookupResult(BaseModel):
    entries: list[LookupEntry]


def split_queries(text: str) -> list[str]:
    """Several words may be searched at once: one per line, or separated by , or ;."""
    seen: dict[str, None] = {}
    for part in re.split(r"[\n,;]+", text or ""):
        part = part.strip()
        if part and part.casefold() not in {q.casefold() for q in seen}:
            seen[part] = None
    return list(seen)[:MAX_QUERIES]


def build_prompt(pair: LanguagePair) -> str:
    return f"""You are a {pair.source}-{pair.target} dictionary for a {pair.source} speaker learning {pair.target}.

The user sends one or more words or short phrases, one per line. Each may be {pair.source}
or {pair.target}. For EACH of them return one entry with 2-4 senses:
- different meanings, translations or common alternatives (e.g. synonyms, the
  word in another context), most common first;
- "word": ALWAYS {pair.target}, in base form (infinitive for verbs, singular with
  definite article for nouns, e.g. "la casa", "lo zaino", "l'albero");
- "translation": ALWAYS {pair.source}, short (with article for nouns);
- "level": the CEFR level (A1-C2) at which learners typically meet this word in
  this meaning; it shows how difficult the word is;
- "example": one short, natural {pair.target} sentence using the word.
Do not repeat the same {pair.target} word twice within an entry.
Answer only with the JSON object."""


def lookup(
    model: str, pair: LanguagePair, queries: list[str], client: ChatClient | None = None
) -> list[LookupEntry]:
    if not queries:
        return []
    client = client or ollama.Client(host=OLLAMA_HOST)
    messages = [
        {"role": "system", "content": build_prompt(pair)},
        {"role": "user", "content": "\n".join(queries)},
    ]
    content = chat_json(client, model, messages, LookupResult.model_json_schema(), 0.2)
    try:
        entries = LookupResult.model_validate_json(content).entries
    except ValidationError as err:
        raise ValueError("Das Modell hat keine gültige Antwort geliefert. Bitte nochmal versuchen.") from err
    for e in entries:  # drop empty and duplicate words
        senses: dict[str, Sense] = {}
        for s in e.senses:
            s.word, s.translation = s.word.strip(), s.translation.strip()
            if s.word:
                senses.setdefault(s.word.casefold(), s)
        e.senses = list(senses.values())
    return [e for e in entries if e.senses]
