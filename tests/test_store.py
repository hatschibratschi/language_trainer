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


def test_add_vocab_with_list_and_box_counts_new_words(tmp_path):
    store = make_store(tmp_path)
    assert store.add_vocab("bellaMelanto", [("lo zaino", "der Rucksack")], "Reise", box=3) == 1
    assert store.add_vocab("bellaMelanto", [("lo zaino", "x"), ("il treno", "der Zug")], "Reise", box=9) == 1
    assert store.cards("bellaMelanto", "Reise") == [("lo zaino", "der Rucksack", 3), ("il treno", "der Zug", 6)]
    assert store.find_vocab("bellaMelanto", ["lo zaino", "nope"]) == {"lo zaino": ("Reise", 3)}


def test_apply_edits_updates_adds_and_deletes(tmp_path):
    store = make_store(tmp_path)
    store.add_vocab("hatschibratschi", [("ciao", "hallo"), ("grazie", "danke"), ("prego", "bitte")])
    rows = store.edit_rows("hatschibratschi")
    ids = [r[0] for r in rows]
    by_word = {r[1]: r for r in rows}
    edited = [
        [by_word["ciao"][0], "ciao", "hallo, tschüss", "Gruß", 2],  # changed
        [by_word["grazie"][0], "", "danke", "Standard", 1],  # emptied -> deleted
        # "prego" removed from the table -> deleted
        [None, "per favore", "bitte", "", ""],  # new, default list and box
        ["", "", "", "", ""],  # empty new row -> ignored
    ]
    r = store.apply_edits("hatschibratschi", ids, edited, default_list="Standard")
    assert (r.updated, r.added, r.deleted, r.errors) == (1, 1, 2, [])
    assert sorted(store.cards("hatschibratschi")) == [("ciao", "hallo, tschüss", 2), ("per favore", "bitte", 1)]
    assert store.vocab_lists("hatschibratschi") == ["Standard", "Gruß"]


def test_apply_edits_reports_duplicates_and_is_per_user(tmp_path):
    store = make_store(tmp_path)
    store.add_vocab("hatschibratschi", [("ciao", "hallo"), ("grazie", "danke")])
    store.add_vocab("bellaMelanto", [("ciao", "hallo")])
    rows = store.edit_rows("hatschibratschi")
    ciao = next(r for r in rows if r[1] == "ciao")
    r = store.apply_edits("hatschibratschi", [ciao[0]], [[ciao[0], "grazie", "x", "Standard", 1], [None, "grazie", "y", "", 1]])
    assert r.updated == 0 and r.added == 0 and len(r.errors) == 2
    other = store.edit_rows("bellaMelanto")[0][0]
    store.apply_edits("hatschibratschi", [other], [])  # someone else's id: nothing happens
    assert store.vocab("bellaMelanto") == [["ciao", "hallo"]]


def test_rename_list_merges(tmp_path):
    store = make_store(tmp_path)
    store.add_vocab("hatschibratschi", [("ciao", "hallo")], "A")
    store.add_vocab("hatschibratschi", [("grazie", "danke")], "B")
    assert store.rename_list("hatschibratschi", "A", "B") == 1
    assert store.vocab_lists("hatschibratschi") == ["Standard", "B"]


def test_editor_filter_and_sort():
    from parla.app import filter_rows

    rows = [[1, "la casa", "das Haus", "A", 2], [2, "il bar", "die Bar", "B", 5], [3, "l'albero", "der Baum", "A", 1]]
    assert [r[0] for r in filter_rows(rows, "", "Hinzugefügt", True)] == [3, 2, 1]
    assert [r[1] for r in filter_rows(rows, "", "Italienisch", False)] == ["l'albero", "il bar", "la casa"]
    assert [r[0] for r in filter_rows(rows, "", "Fach", True)] == [2, 1, 3]
    assert [r[0] for r in filter_rows(rows, "BA", "Deutsch", False)] == [2, 3]  # Bar, Baum
    assert [r[0] for r in filter_rows(rows, "b", "Liste", False)] == [3, 2]  # lists A, B
