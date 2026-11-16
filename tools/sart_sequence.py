"""Generates the fixed sequences of the SART task (T3.3, decisions 66, 85, 89,
93): the main part of 225 trials and two lists of 18 trials for the practice
(the second is for the repeat of the practice), the same for everybody and at
the retest.

A trial is a pair [digit, size]: the digit 1-9 and the index 0-4 of its size
(the five sizes of stimuli/sart-look.json, in the proportions of the original
font sizes). Rules:

- main part: 225 trials, every digit 25 times (25 threes, 11%), the same digit
  never twice in a row. It is five blocks of 45; every block holds each of the
  45 pairs (digit, size) exactly once. So every digit appears in every size
  five times, the three in all five sizes, and the counts stay balanced after
  every block (the participant who stops early still got all digits and sizes
  in equal numbers). No more than three trials of one size follow each other,
  also over the border of two blocks;
- practice list: 18 trials, every digit twice (two threes), the same digit
  never twice in a row, the two appearances of a digit in different sizes, the
  two threes in different sizes and not among the first three trials, at least
  four trials apart; sizes as even as possible (3-4 trials of each); no more
  than two trials of one size in a row. The second list is another order.

Run once; the result is stimuli/sart-sequence.json, which carries its own
version. Changing the file after data collection starts needs the author's
decision and a new version.

Usage, from app/:
    python tools/sart_sequence.py          # writes the file
    python tools/sart_sequence.py --check  # verifies the file, changes nothing
"""

import json
import random
import sys
from collections import Counter
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
PATH = APP / "stimuli" / "sart-sequence.json"
LOOK_PATH = APP / "stimuli" / "sart-look.json"
VERSION = 1
SEED = 20261118
DIGITS = list(range(1, 10))
SIZES = 5
NOGO = 3
BLOCK_LENGTH = len(DIGITS) * SIZES  # 45
BLOCKS = 5
MAIN_LENGTH = BLOCK_LENGTH * BLOCKS  # 225
PRACTICE_LENGTH = 18
MAX_SIZE_RUN_MAIN = 3
MAX_SIZE_RUN_PRACTICE = 2


def longest_size_run(trials):
    best = run = 0
    last = None
    for _, size in trials:
        run = run + 1 if size == last else 1
        last = size
        best = max(best, run)
    return best


def no_repeats(trials):
    return all(a[0] != b[0] for a, b in zip(trials, trials[1:]))


def build_main(rng):
    items = []
    for _ in range(BLOCKS):
        pool = [[d, s] for d in DIGITS for s in range(SIZES)]
        while True:
            rng.shuffle(pool)
            candidate = items[-MAX_SIZE_RUN_MAIN:] + pool
            if no_repeats(items[-1:] + pool) and longest_size_run(candidate) <= MAX_SIZE_RUN_MAIN:
                break
        items += [list(t) for t in pool]
    return items


def build_practice(rng, size_shift):
    base = [0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4]
    base = [(s + size_shift) % SIZES for s in base]
    while True:
        digits = [d for d in DIGITS for _ in range(2)]
        sizes = list(base)
        rng.shuffle(digits)
        rng.shuffle(sizes)
        trials = [[d, s] for d, s in zip(digits, sizes)]
        if not problems_in_practice(trials):
            return trials


def problems_in_practice(items):
    found = []
    if len(items) != PRACTICE_LENGTH:
        return [f"length {len(items)}, not {PRACTICE_LENGTH}"]
    if any(len(t) != 2 or t[0] not in DIGITS or t[1] not in range(SIZES) for t in items):
        return ["a trial that is not [digit 1-9, size 0-4]"]
    counts = Counter(t[0] for t in items)
    if set(counts) != set(DIGITS) or set(counts.values()) != {2}:
        found.append("not every digit twice")
    if not no_repeats(items):
        found.append("the same digit twice in a row")
    for d in DIGITS:
        if len({t[1] for t in items if t[0] == d}) != 2:
            found.append(f"digit {d} twice in the same size")
    threes = [i for i, t in enumerate(items) if t[0] == NOGO]
    if len(threes) == 2:
        if threes[0] < 3:
            found.append("a three among the first three trials")
        if threes[1] - threes[0] < 4:
            found.append("the two threes less than four trials apart")
        if items[threes[0]][1] == items[threes[1]][1]:
            found.append("the two threes in the same size")
    size_counts = Counter(t[1] for t in items)
    if len(size_counts) != SIZES or max(size_counts.values()) > 4 or min(size_counts.values()) < 3:
        found.append("sizes not even (3-4 of each)")
    if longest_size_run(items) > MAX_SIZE_RUN_PRACTICE:
        found.append(f"more than {MAX_SIZE_RUN_PRACTICE} trials of one size in a row")
    return found


def problems_in_main(items):
    found = []
    if len(items) != MAIN_LENGTH:
        return [f"length {len(items)}, not {MAIN_LENGTH}"]
    if any(len(t) != 2 or t[0] not in DIGITS or t[1] not in range(SIZES) for t in items):
        return ["a trial that is not [digit 1-9, size 0-4]"]
    for d in DIGITS:
        if sum(t[0] == d for t in items) != MAIN_LENGTH // len(DIGITS):
            found.append(f"digit {d} not {MAIN_LENGTH // len(DIGITS)} times")
    if not no_repeats(items):
        found.append("the same digit twice in a row")
    if longest_size_run(items) > MAX_SIZE_RUN_MAIN:
        found.append(f"more than {MAX_SIZE_RUN_MAIN} trials of one size in a row")
    for start in range(0, MAIN_LENGTH, BLOCK_LENGTH):
        block = items[start:start + BLOCK_LENGTH]
        if sorted(map(tuple, block)) != sorted((d, s) for d in DIGITS for s in range(SIZES)):
            found.append(f"block from trial {start + 1} is not every (digit, size) pair once")
    return found


def generate():
    rng = random.Random(SEED)
    main = build_main(rng)
    first = build_practice(rng, 0)
    second = build_practice(rng, 2)
    while second == first:
        second = build_practice(rng, 2)
    return {
        "sequence_version": VERSION,
        "look_version": json.loads(LOOK_PATH.read_text())["look_version"],
        "seed": SEED,
        "nogo_digit": NOGO,
        "sizes": SIZES,
        "main_length": MAIN_LENGTH,
        "main": main,
        "practice": [first, second],
    }


def check(data):
    found = problems_in_main(data["main"])
    for number, items in enumerate(data["practice"], 1):
        found += [f"practice {number}: {p}" for p in problems_in_practice(items)]
    if data["practice"][0] == data["practice"][1]:
        found.append("the two practice lists are the same")
    return found


def main():
    if "--check" in sys.argv:
        found = check(json.loads(PATH.read_text()))
        print("\n".join(found) if found else "ok")
        sys.exit(1 if found else 0)
    data = generate()
    found = check(data)
    assert not found, found
    lines = [f" {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in data.items()]
    PATH.write_text("{\n" + ",\n".join(lines) + "\n}\n")
    print(f"written: {PATH.name}, version {VERSION}, {len(data['main'])} trials")


if __name__ == "__main__":
    main()
