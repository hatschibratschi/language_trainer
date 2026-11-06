"""Vocabulary trainer: a Leitner card box ("Zettelkasten") with 6 boxes.

Box 1 holds the words you struggle with, box 6 the ones you know well. A known word moves
up one box, an unknown word down one box. Each round asks ROUND_SIZE words, picked mostly
from the low boxes.
"""

from __future__ import annotations

import random
from collections import defaultdict

from parla.store import BOXES

ROUND_SIZE = 10
# Relative chance that the next word comes from a box (only non-empty boxes count).
BOX_WEIGHTS = {1: 40, 2: 25, 3: 15, 4: 10, 5: 6, 6: 4}

Card = tuple[str, str, int]  # (word, translation, box)


def pick_round(cards: list[Card], size: int = ROUND_SIZE, rng: random.Random | None = None) -> list[Card]:
    """Pick up to `size` different cards: first a box by BOX_WEIGHTS, then a random card in it."""
    rng = rng or random.Random()
    by_box: dict[int, list[Card]] = defaultdict(list)
    for card in cards:
        by_box[card[2]].append(card)
    picked: list[Card] = []
    while len(picked) < size and by_box:
        boxes = sorted(by_box)
        box = rng.choices(boxes, weights=[BOX_WEIGHTS.get(b, 1) for b in boxes])[0]
        pool = by_box[box]
        picked.append(pool.pop(rng.randrange(len(pool))))
        if not pool:
            del by_box[box]
    return picked


def next_box(box: int, known: bool) -> int:
    return min(BOXES, box + 1) if known else max(1, box - 1)


def box_counts(cards: list[Card]) -> dict[int, int]:
    counts = {b: 0 for b in range(1, BOXES + 1)}
    for _, _, box in cards:
        counts[box] = counts.get(box, 0) + 1
    return counts
