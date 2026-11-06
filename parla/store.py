"""Per-user persistence in SQLite: settings, vocabulary and the current conversation."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass, field
from pathlib import Path

from parla.tutor import TutorTurn

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    name TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS settings (
    user               TEXT PRIMARY KEY REFERENCES users(name),
    model              TEXT,
    level              TEXT NOT NULL,
    scenario           TEXT NOT NULL,
    expand_translation INTEGER NOT NULL DEFAULT 0,
    speak              INTEGER NOT NULL DEFAULT 1,
    slow_speech        INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS vocab (
    user        TEXT NOT NULL REFERENCES users(name),
    word        TEXT NOT NULL,
    translation TEXT NOT NULL,
    added_at    TEXT NOT NULL DEFAULT (datetime('now')),
    list        TEXT NOT NULL DEFAULT 'Standard',
    box         INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (user, word)
);
CREATE TABLE IF NOT EXISTS conversations (
    user       TEXT PRIMARY KEY REFERENCES users(name),
    data       TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


DEFAULT_LIST = "Standard"
BOXES = 6  # Leitner boxes ("Fächer") of the vocabulary trainer


def clamp_box(value, default: int = 1) -> int:
    box = _to_int(value)
    return default if box is None else max(1, min(BOXES, box))


def _to_int(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


@dataclass
class EditResult:
    updated: int = 0
    added: int = 0
    deleted: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class Settings:
    model: str | None
    level: str
    scenario: str
    expand_translation: bool = False
    speak: bool = True  # read the tutor's replies aloud
    slow_speech: bool = False


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.executescript(SCHEMA)
            # Databases from before vocabulary lists: every word goes to the default list.
            cols = [r[1] for r in db.execute("PRAGMA table_info(vocab)")]
            if "list" not in cols:
                db.execute(
                    f"ALTER TABLE vocab ADD COLUMN list TEXT NOT NULL DEFAULT '{DEFAULT_LIST}'"
                )
            # Databases from before the vocabulary trainer: every word starts in box 1.
            if "box" not in cols:
                db.execute("ALTER TABLE vocab ADD COLUMN box INTEGER NOT NULL DEFAULT 1")
            # Databases from before voice mode.
            cols = [r[1] for r in db.execute("PRAGMA table_info(settings)")]
            if "speak" not in cols:
                db.execute("ALTER TABLE settings ADD COLUMN speak INTEGER NOT NULL DEFAULT 1")
            if "slow_speech" not in cols:
                db.execute("ALTER TABLE settings ADD COLUMN slow_speech INTEGER NOT NULL DEFAULT 0")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    # --- users -----------------------------------------------------------
    def ensure_users(self, names: list[str]) -> None:
        with closing(self._connect()) as db, db:
            db.executemany("INSERT OR IGNORE INTO users(name) VALUES (?)", [(n,) for n in names])

    def users(self) -> list[str]:
        with closing(self._connect()) as db:
            return [r[0] for r in db.execute("SELECT name FROM users ORDER BY rowid")]

    # --- settings --------------------------------------------------------
    def load_settings(self, user: str, default: Settings) -> Settings:
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT model, level, scenario, expand_translation, speak, slow_speech"
                " FROM settings WHERE user = ?",
                (user,),
            ).fetchone()
        if row is None:
            return default
        return Settings(
            model=row[0],
            level=row[1],
            scenario=row[2],
            expand_translation=bool(row[3]),
            speak=bool(row[4]),
            slow_speech=bool(row[5]),
        )

    def save_settings(self, user: str, s: Settings) -> None:
        with closing(self._connect()) as db, db:
            db.execute(
                """INSERT INTO settings(user, model, level, scenario, expand_translation,
                                        speak, slow_speech)
                   VALUES (:user, :model, :level, :scenario, :expand_translation,
                           :speak, :slow_speech)
                   ON CONFLICT(user) DO UPDATE SET model = excluded.model,
                       level = excluded.level, scenario = excluded.scenario,
                       expand_translation = excluded.expand_translation,
                       speak = excluded.speak, slow_speech = excluded.slow_speech""",
                {
                    "user": user,
                    **asdict(s),
                    "expand_translation": int(s.expand_translation),
                    "speak": int(s.speak),
                    "slow_speech": int(s.slow_speech),
                },
            )

    # --- vocabulary ------------------------------------------------------
    def add_vocab(
        self, user: str, items: list[tuple[str, str]], list_name: str = DEFAULT_LIST, box: int = 1
    ) -> int:
        """A word is stored once per user; adding it again keeps the existing entry and list.
        Returns how many words were new."""
        with closing(self._connect()) as db, db:
            before = db.total_changes
            db.executemany(
                "INSERT OR IGNORE INTO vocab(user, word, translation, list, box) VALUES (?, ?, ?, ?, ?)",
                [(user, w, t, list_name or DEFAULT_LIST, clamp_box(box)) for w, t in items if w],
            )
            return db.total_changes - before

    def find_vocab(self, user: str, words: list[str]) -> dict[str, tuple[str, int]]:
        """word -> (list, box) for the given words that the user already has."""
        with closing(self._connect()) as db:
            return {
                w: (lst, box)
                for w, lst, box in db.execute(
                    f"SELECT word, list, box FROM vocab WHERE user = ? AND word IN ({','.join('?' * len(words))})",
                    (user, *words),
                )
            }

    # --- list editor -----------------------------------------------------
    def edit_rows(self, user: str, list_name: str | None = None) -> list[list]:
        """[id, word, translation, list, box], newest first; all lists if list_name is None."""
        sql = "SELECT rowid, word, translation, list, box FROM vocab WHERE user = ?"
        args: tuple = (user,)
        if list_name is not None:
            sql, args = sql + " AND list = ?", (user, list_name)
        with closing(self._connect()) as db:
            return [list(r) for r in db.execute(sql + " ORDER BY rowid DESC", args)]

    def apply_edits(
        self, user: str, original_ids: list[int], rows: list[list], default_list: str = DEFAULT_LIST
    ) -> EditResult:
        """Save an edited table of edit_rows(). Rows keep their id; a row with an empty word
        or whose id is gone is deleted; a row without id is a new word."""
        result = EditResult()
        kept: set[int] = set()
        with closing(self._connect()) as db, db:
            for row in rows:
                row = [*row, None, None, None, None, None][:5]
                rid, word, translation, list_name, box = row
                word, translation = str(word or "").strip(), str(translation or "").strip()
                list_name = str(list_name or "").strip() or default_list
                rid = _to_int(rid)
                if rid is not None and rid in original_ids:
                    if not word:
                        continue  # deleted below
                    kept.add(rid)
                    old = db.execute(
                        "SELECT word, translation, list, box FROM vocab WHERE rowid = ? AND user = ?",
                        (rid, user),
                    ).fetchone()
                    if old is None:
                        continue
                    new = (word, translation, list_name, clamp_box(box, old[3]))
                    if new == tuple(old):
                        continue
                    try:
                        db.execute(
                            "UPDATE vocab SET word = ?, translation = ?, list = ?, box = ?"
                            " WHERE rowid = ? AND user = ?",
                            (*new, rid, user),
                        )
                        result.updated += 1
                    except sqlite3.IntegrityError:
                        result.errors.append(f"„{word}“ gibt es schon – nicht umbenannt.")
                elif word:
                    cur = db.execute(
                        "INSERT OR IGNORE INTO vocab(user, word, translation, list, box)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (user, word, translation, list_name, clamp_box(box)),
                    )
                    if cur.rowcount:
                        result.added += 1
                    else:
                        result.errors.append(f"„{word}“ gibt es schon – nicht hinzugefügt.")
            gone = [i for i in original_ids if i not in kept]
            db.executemany("DELETE FROM vocab WHERE rowid = ? AND user = ?", [(i, user) for i in gone])
            result.deleted = len(gone)
        return result

    def rename_list(self, user: str, old: str, new: str) -> int:
        """Rename a list (or merge it into an existing one); returns how many words moved."""
        with closing(self._connect()) as db, db:
            return db.execute(
                "UPDATE vocab SET list = ? WHERE user = ? AND list = ?", (new, user, old)
            ).rowcount

    def vocab(self, user: str, list_name: str | None = None) -> list[list[str]]:
        """Newest first; all lists if list_name is None."""
        sql = "SELECT word, translation FROM vocab WHERE user = ?"
        args: tuple = (user,)
        if list_name is not None:
            sql, args = sql + " AND list = ?", (user, list_name)
        with closing(self._connect()) as db:
            return [list(r) for r in db.execute(sql + " ORDER BY rowid DESC", args)]

    def vocab_lists(self, user: str) -> list[str]:
        """The default list first, then the others alphabetically."""
        with closing(self._connect()) as db:
            names = {r[0] for r in db.execute("SELECT DISTINCT list FROM vocab WHERE user = ?", (user,))}
        return [DEFAULT_LIST, *sorted(names - {DEFAULT_LIST}, key=str.casefold)]

    def move_vocab(self, user: str, words: list[str], list_name: str) -> int:
        """Move existing words to another list; returns how many were moved."""
        with closing(self._connect()) as db, db:
            cur = db.executemany(
                "UPDATE vocab SET list = ? WHERE user = ? AND word = ?",
                [(list_name, user, w) for w in words],
            )
            return cur.rowcount

    # --- vocabulary trainer (boxes) ----------------------------------------
    def cards(self, user: str, list_name: str | None = None) -> list[tuple[str, str, int]]:
        """(word, translation, box) for all words of a list, or of all lists if None."""
        sql = "SELECT word, translation, box FROM vocab WHERE user = ?"
        args: tuple = (user,)
        if list_name is not None:
            sql, args = sql + " AND list = ?", (user, list_name)
        with closing(self._connect()) as db:
            return [tuple(r) for r in db.execute(sql + " ORDER BY rowid", args)]

    def set_box(self, user: str, word: str, box: int) -> None:
        with closing(self._connect()) as db, db:
            db.execute("UPDATE vocab SET box = ? WHERE user = ? AND word = ?", (box, user, word))

    # --- current conversation --------------------------------------------
    def save_conversation(self, user: str, history: list[dict], entries: list[dict]) -> None:
        data = json.dumps(
            {
                "history": history,
                "entries": [
                    {"role": "assistant", "turn": e["turn"].model_dump()}
                    if e["role"] == "assistant"
                    else e
                    for e in entries
                ],
            },
            ensure_ascii=False,
        )
        with closing(self._connect()) as db, db:
            db.execute(
                """INSERT INTO conversations(user, data) VALUES (?, ?)
                   ON CONFLICT(user) DO UPDATE SET data = excluded.data,
                       updated_at = datetime('now')""",
                (user, data),
            )

    def load_conversation(self, user: str) -> tuple[list[dict], list[dict]] | None:
        with closing(self._connect()) as db:
            row = db.execute("SELECT data FROM conversations WHERE user = ?", (user,)).fetchone()
        if row is None:
            return None
        data = json.loads(row[0])
        entries = [
            {"role": "assistant", "turn": TutorTurn.model_validate(e["turn"])}
            if e["role"] == "assistant"
            else e
            for e in data["entries"]
        ]
        return data["history"], entries
