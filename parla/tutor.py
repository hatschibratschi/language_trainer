"""Tutor engine: builds prompts, calls Ollama and parses structured replies."""

from __future__ import annotations

from typing import Any, Protocol

import ollama
from pydantic import BaseModel, Field, ValidationError

from parla.config import LEVELS, OLLAMA_HOST, PREFERRED_MODELS, LanguagePair, Scenario

START_TOKEN = "[START]"


class Correction(BaseModel):
    original: str = Field(description="The learner's wrong phrase, copied verbatim")
    corrected: str = Field(description="The corrected phrase in the target language")
    explanation: str = Field(description="Short explanation in the learner's native language")


class VocabItem(BaseModel):
    word: str = Field(description="Word or phrase in the target language")
    translation: str = Field(description="Translation in the learner's native language")


class TutorTurn(BaseModel):
    corrections: list[Correction] = Field(
        default_factory=list, description="Mistakes in the learner's last message"
    )
    better_phrasing: str | None = Field(
        default=None,
        description="A more natural way to say the learner's whole message, or null",
    )
    reply: str = Field(description="Your in-character reply in the target language")
    reply_translation: str = Field(description="Translation of reply into native language")
    new_vocabulary: list[VocabItem] = Field(
        default_factory=list, description="1-3 useful words from your reply"
    )


class ChatClient(Protocol):
    def chat(self, **kwargs: Any) -> Any: ...


def build_system_prompt(pair: LanguagePair, level: str, scenario: Scenario) -> str:
    return f"""You are Parla, a warm, patient {pair.target} tutor for a native {pair.source} speaker.

LEVEL: {level} ({LEVELS[level]}).
Always write your reply at this level. Never use language far above it.

SCENARIO: {scenario.prompt}
Stay in character and keep the conversation moving: end your reply with a question
or a prompt that invites the learner to answer. Keep replies short (1-3 sentences).

When the user message is exactly "{START_TOKEN}", open the scenario with your first
line; corrections must then be empty.

For every learner message:
1. Check it for mistakes in {pair.target} (grammar, spelling, gender/articles,
   prepositions, verb forms, word choice). Accents matter (e.g. "e" vs "è").
   For each real mistake add an entry to "corrections" with the exact wrong
   phrase, the corrected phrase and a short, friendly explanation in {pair.source}.
   Do NOT invent mistakes: if the message is correct, "corrections" is empty.
   Ignore missing capitalisation and final punctuation.
2. If the learner writes in {pair.source} or mixes languages, help them: put the
   {pair.target} version in "better_phrasing" and continue in {pair.target}.
3. "better_phrasing": only if a native speaker would say it noticeably more
   naturally; otherwise null.
4. "reply": your in-character answer in {pair.target} only. React to what the
   learner said as your character would (answer the question, serve, ask back).
   Never just repeat or paraphrase the learner's message.
5. "reply_translation": a faithful {pair.source} translation of "reply".
6. "new_vocabulary": 1-3 words or phrases from your reply that are useful at this
   level, with their {pair.source} translation (base form, with article for nouns).

LANGUAGES – important:
- "explanation" and "reply_translation" and vocabulary "translation": ALWAYS {pair.source}.
- "reply", "corrected", "better_phrasing" and vocabulary "word": ALWAYS {pair.target}.

{_example(pair)}

Answer only with the JSON object."""


def _example(pair: LanguagePair) -> str:
    if (pair.source, pair.target) != ("German", "Italian"):
        return ""
    return """EXAMPLE (scenario: bar). Learner: "Io vorrei un caffe e una cornetto."
{"corrections": [
  {"original": "un caffe", "corrected": "un caffè",
   "explanation": "„Caffè“ schreibt man mit Akzent auf dem e."},
  {"original": "una cornetto", "corrected": "un cornetto",
   "explanation": "„Cornetto“ ist maskulin, daher der Artikel „un“."}],
 "better_phrasing": "Vorrei un caffè e un cornetto, per favore.",
 "reply": "Certo! Il cornetto lo vuole vuoto o alla crema?",
 "reply_translation": "Natürlich! Möchten Sie das Croissant ohne Füllung oder mit Vanillecreme?",
 "new_vocabulary": [{"word": "vuoto", "translation": "leer, ohne Füllung"},
                    {"word": "la crema", "translation": "die Vanillecreme"}]}
(Note: "Io vorrei" is not wrong, but natives usually drop "io" -> better_phrasing.)"""


def to_ollama_messages(system_prompt: str, history: list[dict[str, str]]) -> list[dict[str, str]]:
    """history holds plain {"role", "content"} turns (assistant content = reply text)."""
    return [{"role": "system", "content": system_prompt}, *history]


class Tutor:
    def __init__(self, model: str, client: ChatClient | None = None):
        self.model = model
        self.client = client or ollama.Client(host=OLLAMA_HOST)

    def respond(
        self,
        pair: LanguagePair,
        level: str,
        scenario: Scenario,
        history: list[dict[str, str]],
    ) -> TutorTurn:
        messages = to_ollama_messages(build_system_prompt(pair, level, scenario), history)
        kwargs: dict[str, Any] = dict(
            model=self.model,
            messages=messages,
            format=TutorTurn.model_json_schema(),
            options={"temperature": 0.6},
        )
        try:
            # Disable "thinking" for reasoning models (qwen3 etc.) – much faster.
            response = self.client.chat(**kwargs, think=False)
        except ollama.ResponseError as err:
            if "think" not in str(err).lower():
                raise
            response = self.client.chat(**kwargs)
        content = response["message"]["content"]
        try:
            return TutorTurn.model_validate_json(content)
        except ValidationError:
            # Fall back to showing the raw text rather than failing the turn.
            return TutorTurn(reply=content.strip(), reply_translation="")


def list_models(client: ChatClient | None = None) -> list[str]:
    try:
        client = client or ollama.Client(host=OLLAMA_HOST)
        names = [m["model"] for m in client.list()["models"]]  # type: ignore[attr-defined]
    except Exception:
        return []
    # Embedding models can't chat.
    return sorted(n for n in names if "embed" not in n and "bge" not in n)


def pick_default_model(available: list[str], requested: str | None = None) -> str | None:
    if requested:
        return requested
    for name in PREFERRED_MODELS:
        if name in available:
            return name
    return available[0] if available else None
