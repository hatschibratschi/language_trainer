from parla.store import Settings, Store
from parla.tutor import Correction, TutorTurn

DEFAULT = Settings(model="m", level="A2", scenario="free")


def make_store(tmp_path):
    store = Store(tmp_path / "sub" / "parla.db")
    store.ensure_users(["hatschibratschi", "bellaMelanto"])
    return store


def test_users_are_seeded_once_in_order(tmp_path):
    store = make_store(tmp_path)
    store.ensure_users(["hatschibratschi", "bellaMelanto"])
    assert store.users() == ["hatschibratschi", "bellaMelanto"]


def test_settings_default_and_roundtrip(tmp_path):
    store = make_store(tmp_path)
    assert store.load_settings("bellaMelanto", DEFAULT) == DEFAULT
    s = Settings(model="gemma3:27b", level="B1", scenario="bar", expand_translation=True)
    store.save_settings("bellaMelanto", s)
    store.save_settings("bellaMelanto", s)  # upsert
    assert store.load_settings("bellaMelanto", DEFAULT) == s
    assert store.load_settings("hatschibratschi", DEFAULT) == DEFAULT


def test_vocab_is_per_user_deduplicated_newest_first(tmp_path):
    store = make_store(tmp_path)
    store.add_vocab("hatschibratschi", [("il caffè", "der Kaffee"), ("ciao", "hallo")])
    store.add_vocab("hatschibratschi", [("ciao", "tschüss"), ("", "leer"), ("grazie", "danke")])
    assert store.vocab("hatschibratschi") == [
        ["grazie", "danke"], ["ciao", "hallo"], ["il caffè", "der Kaffee"]
    ]
    assert store.vocab("bellaMelanto") == []


def test_conversation_roundtrip_restores_turn_objects(tmp_path):
    store = make_store(tmp_path)
    assert store.load_conversation("hatschibratschi") is None
    turn = TutorTurn(
        corrections=[Correction(original="caffe", corrected="caffè", explanation="Akzent")],
        reply="Ecco il caffè!",
        reply_translation="Hier ist der Kaffee!",
    )
    history = [{"role": "user", "content": "Un caffe"}, {"role": "assistant", "content": turn.reply}]
    entries = [{"role": "user", "text": "Un caffe"}, {"role": "assistant", "turn": turn}]
    store.save_conversation("hatschibratschi", history, entries)

    loaded_history, loaded_entries = store.load_conversation("hatschibratschi")
    assert loaded_history == history
    assert loaded_entries[0] == entries[0]
    assert loaded_entries[1]["turn"] == turn
    assert store.load_conversation("bellaMelanto") is None


def test_vocab_lists_default_filter_and_move(tmp_path):
    store = make_store(tmp_path)
    assert store.vocab_lists("hatschibratschi") == ["Standard"]
    store.add_vocab("hatschibratschi", [("ciao", "hallo"), ("il gatto", "die Katze")])
    store.add_vocab("hatschibratschi", [("il cane", "der Hund")], "Tiere")
    assert store.move_vocab("hatschibratschi", ["il gatto", "fehlt"], "Tiere") == 1
    assert store.vocab_lists("hatschibratschi") == ["Standard", "Tiere"]
    assert store.vocab("hatschibratschi", "Tiere") == [["il cane", "der Hund"], ["il gatto", "die Katze"]]
    assert store.vocab("hatschibratschi", "Standard") == [["ciao", "hallo"]]
    assert len(store.vocab("hatschibratschi")) == 3
    assert store.vocab_lists("bellaMelanto") == ["Standard"]


def test_old_database_is_migrated_to_default_list(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.executescript(
        "CREATE TABLE vocab (user TEXT NOT NULL, word TEXT NOT NULL, translation TEXT NOT NULL,"
        " added_at TEXT NOT NULL DEFAULT (datetime('now')), PRIMARY KEY (user, word));"
        "INSERT INTO vocab(user, word, translation) VALUES ('u', 'ciao', 'hallo');"
    )
    db.commit()
    db.close()
    store = Store(path)
    assert store.vocab("u", "Standard") == [["ciao", "hallo"]]


def test_voice_settings_roundtrip_and_migration(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:  # settings table from before voice mode
        db.executescript(
            """CREATE TABLE users (name TEXT PRIMARY KEY);
               CREATE TABLE settings (user TEXT PRIMARY KEY, model TEXT, level TEXT NOT NULL,
                   scenario TEXT NOT NULL, expand_translation INTEGER NOT NULL DEFAULT 0);
               INSERT INTO users VALUES ('anna');
               INSERT INTO settings VALUES ('anna', 'm', 'B1', 'bar', 1);"""
        )
    store = Store(path)
    s = store.load_settings("anna", DEFAULT)
    assert (s.level, s.speak, s.slow_speech) == ("B1", True, False)
    s.speak, s.slow_speech = False, True
    store.save_settings("anna", s)
    assert store.load_settings("anna", DEFAULT) == s
