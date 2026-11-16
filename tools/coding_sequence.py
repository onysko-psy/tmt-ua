"""Generates the fixed sequence of the symbol coding task (T3.1, decisions
80, 89, 93): 180 items, each of the nine symbols 20 times, the same symbol
never twice in a row, and every nine items (1-9, 10-18, ...) hold each symbol
once, so that the symbols are equally frequent wherever a participant stops; plus two practice lists of 10 items (the second is for
the repeat of the practice) in which every symbol occurs and none twice in a
row. The sequence is the same for everybody and at the retest.

An item is the digit of its symbol (1-9); the figure with that digit in the
key is what the participant sees. Run once; the result is stimuli/coding-
sequence.json, which carries its own version. Changing the file after data
collection starts needs the author's decision and a new version.

Usage, from app/:
    python tools/coding_sequence.py          # writes the file
    python tools/coding_sequence.py --check  # verifies the file, changes nothing
"""

import json
import random
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
PATH = APP / "stimuli" / "coding-sequence.json"
VERSION = 1
SEED = 20261116
SYMBOLS = 9
LENGTH = 180
PER_SYMBOL = LENGTH // SYMBOLS
PRACTICE_LENGTH = 10


def build_main(rng):
    """20 blocks of nine: each block has every symbol once, in random order,
    and its first symbol is not the last of the block before. So the symbols
    stay equally frequent whenever a participant stops: after any whole
    number of blocks every symbol was shown equally often, and at any point
    the counts differ by at most one."""
    items = []
    for _ in range(PER_SYMBOL):
        block = rng.sample(range(1, SYMBOLS + 1), SYMBOLS)
        while items and block[0] == items[-1]:
            block = rng.sample(range(1, SYMBOLS + 1), SYMBOLS)
        items += block
    return items


def build_practice(rng):
    """Every symbol once, in random order, and one more at the end that is not
    the one before it."""
    while True:
        items = rng.sample(range(1, SYMBOLS + 1), SYMBOLS)
        extra = rng.choice([s for s in range(1, SYMBOLS + 1) if s != items[-1]])
        items.append(extra)
        if problems_in_practice(items) == []:
            return items


def problems_in_main(items):
    found = []
    if len(items) != LENGTH:
        found.append(f"length {len(items)}, not {LENGTH}")
    for symbol in range(1, SYMBOLS + 1):
        if items.count(symbol) != PER_SYMBOL:
            found.append(f"symbol {symbol} occurs {items.count(symbol)} times, not {PER_SYMBOL}")
    if any(a == b for a, b in zip(items, items[1:])):
        found.append("the same symbol twice in a row")
    for start in range(0, len(items), SYMBOLS):
        if sorted(items[start:start + SYMBOLS]) != list(range(1, SYMBOLS + 1)):
            found.append(f"block from item {start + 1} does not hold every symbol once")
    if not all(isinstance(s, int) and 1 <= s <= SYMBOLS for s in items):
        found.append("an item outside 1..9")
    return found


def problems_in_practice(items):
    found = []
    if len(items) != PRACTICE_LENGTH:
        found.append(f"length {len(items)}, not {PRACTICE_LENGTH}")
    if set(items) != set(range(1, SYMBOLS + 1)):
        found.append("not every symbol occurs")
    if any(a == b for a, b in zip(items, items[1:])):
        found.append("the same symbol twice in a row")
    return found


def generate():
    rng = random.Random(SEED)
    main = build_main(rng)
    practice = [build_practice(rng), build_practice(rng)]
    while practice[1] == practice[0]:
        practice[1] = build_practice(rng)
    return {
        "sequence_version": VERSION,
        "symbols_version": json.loads((APP / "stimuli" / "coding-symbols.json").read_text())["symbols_version"],
        "seed": SEED,
        "length": LENGTH,
        "per_symbol": PER_SYMBOL,
        "items": main,
        "practice": practice,
    }


def check(data):
    found = problems_in_main(data["items"])
    for number, items in enumerate(data["practice"], 1):
        found += [f"practice {number}: {p}" for p in problems_in_practice(items)]
    return found


def main():
    if "--check" in sys.argv:
        found = check(json.loads(PATH.read_text()))
        print("\n".join(found) if found else "ok")
        sys.exit(1 if found else 0)
    data = generate()
    found = check(data)
    assert not found, found
    PATH.write_text(json.dumps(data, indent=1) + "\n")
    print(f"written: {PATH.name}, version {VERSION}, {len(data['items'])} items")


if __name__ == "__main__":
    main()
