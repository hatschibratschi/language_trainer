"""Static configuration: language pairs, CEFR levels and role-play scenarios."""

from __future__ import annotations

import os
from dataclasses import dataclass

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# Models tried in this order when PARLA_MODEL is not set.
PREFERRED_MODELS = ["gemma3:27b", "mistral-small3.2:24b", "qwen3:14b", "gemma3:12b"]
DEFAULT_MODEL = os.environ.get("PARLA_MODEL")


@dataclass(frozen=True)
class LanguagePair:
    key: str
    source: str  # learner's native language (used for explanations)
    target: str  # language being learned
    label: str


LANGUAGE_PAIRS: dict[str, LanguagePair] = {
    "de-it": LanguagePair(
        key="de-it", source="German", target="Italian", label="Deutsch → Italienisch"
    ),
}
DEFAULT_PAIR = "de-it"


LEVELS: dict[str, str] = {
    "A1": "absolute beginner: very short sentences (max ~8 words), present tense only, "
    "the 500 most common words, speak slowly and simply",
    "A2": "elementary: short simple sentences, present tense and passato prossimo, "
    "everyday vocabulary, avoid idioms",
    "B1": "intermediate: normal everyday sentences, all common tenses, occasional "
    "common idioms, explain rare words",
    "B2": "upper intermediate: natural conversational language, subjunctive and "
    "conditional, idioms are fine",
    "C1": "advanced: fully natural, idiomatic, native-speaker language including "
    "colloquial expressions",
}
DEFAULT_LEVEL = "A2"


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str  # shown in the UI (German)
    prompt: str  # instructions for the model (English)


SCENARIOS: dict[str, Scenario] = {
    s.key: s
    for s in [
        Scenario(
            "free",
            "Freies Gespräch",
            "Have a friendly free conversation. Ask the learner about their day, "
            "hobbies, work or travel plans and keep the conversation going.",
        ),
        Scenario(
            "bar",
            "Al bar – Im Café",
            "You are a barista in a busy Italian bar in the morning. The learner is a "
            "customer ordering coffee and something to eat, then paying.",
        ),
        Scenario(
            "hotel",
            "In albergo – Im Hotel",
            "You are the receptionist of a small hotel in Florence. The learner is "
            "checking in; ask about the booking, documents, breakfast and wifi.",
        ),
        Scenario(
            "ristorante",
            "Al ristorante – Im Restaurant",
            "You are a waiter in a trattoria in Rome. Present the menu, take the "
            "order, recommend dishes and bring the bill at the end.",
        ),
        Scenario(
            "direzioni",
            "Chiedere indicazioni – Nach dem Weg fragen",
            "You are a local passer-by in Bologna. The learner asks you for directions "
            "(to the station, a museum, a pharmacy). Give clear directions.",
        ),
        Scenario(
            "medico",
            "Dal medico – Beim Arzt",
            "You are a general practitioner. The learner is a patient describing "
            "symptoms. Ask questions and give simple advice.",
        ),
        Scenario(
            "collega",
            "Small Talk mit Kollegen",
            "You are a friendly Italian colleague at the coffee machine at work. "
            "Make small talk about the weekend, work and plans.",
        ),
    ]
}
DEFAULT_SCENARIO = "free"


# Multi-user without login: everyone picks their name from a list.
USERS = [
    u.strip()
    for u in os.environ.get("PARLA_USERS", "hatschibratschi,bellaMelanto").split(",")
    if u.strip()
]

# Where the SQLite database lives (mounted as a volume in Docker).
DATA_DIR = os.environ.get("PARLA_DATA_DIR", "data")
