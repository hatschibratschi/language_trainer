import random

from parla.store import Store
from parla.trainer import BOXES, box_counts, next_box, pick_round


def cards(n_per_box: int) -> list[tuple[str, str, int]]:
    return [(f"w{b}-{i}", f"t{b}-{i}", b) for b in range(1, BOXES + 1) for i in range(n_per_box)]


def test_round_has_ten_distinct_cards_mostly_from_low_boxes():
    rng = random.Random(1)
    low = high = 0
    for _ in range(200):
        picked = pick_round(cards(20), rng=rng)
        assert len(picked) == 10 and len(set(picked)) == 10
        low += sum(c[2] <= 2 for c in picked)
        high += sum(c[2] >= 5 for c in picked)
    assert low > 4 * high


def test_round_with_few_cards_takes_all_of_them():
    few = [("a", "A", 1), ("b", "B", 6)]
    assert sorted(pick_round(few)) == few
    assert pick_round([]) == []


def test_next_box_moves_one_step_and_stays_in_range():
    assert next_box(1, True) == 2
    assert next_box(BOXES, True) == BOXES
    assert next_box(3, False) == 2
    assert next_box(1, False) == 1


def test_box_counts_cover_all_boxes():
    assert box_counts([("a", "A", 1), ("b", "B", 1), ("c", "C", 6)]) == {1: 2, 2: 0, 3: 0, 4: 0, 5: 0, 6: 1}


def test_store_cards_start_in_box_one_and_box_is_saved(tmp_path):
    store = Store(tmp_path / "parla.db")
    store.ensure_users(["u"])
    store.add_vocab("u", [("ciao", "hallo")])
    store.add_vocab("u", [("il cane", "der Hund")], "Tiere")
    assert store.cards("u") == [("ciao", "hallo", 1), ("il cane", "der Hund", 1)]
    store.set_box("u", "il cane", 4)
    assert store.cards("u", "Tiere") == [("il cane", "der Hund", 4)]
