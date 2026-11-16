"""Generates the fixed sequences of the Stroop task (T3.2, decisions 83, 84,
89, 92, 93): the main part of 96 trials, two lists of 12 trials for the
practice (the second is for the repeat of the practice), the same for
everybody and at the retest.

A trial is a pair [word, ink] of colour ids: the word names the colour `word`
and is printed in `ink`; the trial is congruent when they are the same. Rules:

- main part: 96 trials, 48 congruent and 48 incongruent (decision 83). It is
  four blocks of 24; every block has each colour as a congruent trial three
  times and each of the 12 incongruent pairs (word, ink) once. So every word
  occurs 24 times, 12 of them congruent and 12 incongruent, every ink the
  same, each incongruent pair four times, and the counts stay balanced after
  every block;
- the ink never repeats in two trials in a row (decision 93), also over the
  border of two blocks; and no more than 4 trials of one condition follow each
  other, so that the conditions are mixed (decision 93);
- practice list: 12 trials, every colour as ink three times and as word three
  times, half congruent (decision 92); the ink never repeats in a row and no
  more than 3 trials of one condition follow each other. The second list is
  another order with another set of congruent colours.

Run once; the result is stimuli/stroop-sequence.json, which carries its own
version. Changing the file after data collection starts needs the author's
decision and a new version.

Usage, from app/:
    python tools/stroop_sequence.py          # writes the file
    python tools/stroop_sequence.py --check  # verifies the file, changes nothing
"""

import json
import random
import sys
from collections import Counter
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
PATH = APP / "stimuli" / "stroop-sequence.json"
COLORS_PATH = APP / "stimuli" / "stroop-colors.json"
VERSION = 1
SEED = 20261117
ORDER = ["red", "green", "blue", "yellow"]
BLOCKS = 4
BLOCK_LENGTH = 24
MAIN_LENGTH = BLOCKS * BLOCK_LENGTH
PRACTICE_LENGTH = 12
MAX_RUN_MAIN = 4
MAX_RUN_PRACTICE = 3


def congruent(trial):
    return trial[0] == trial[1]


def longest_run(trials):
    best = run = 0
    last = None
    for trial in trials:
        run = run + 1 if congruent(trial) == last else 1
        last = congruent(trial)
        best = max(best, run)
    return best


def arrange(trials, rng, previous, max_run):
    """A random order of `trials` in which the ink never repeats (also after
    `previous`, the trials before them) and no more than max_run trials of one
    condition follow each other. Backtracking, in random order."""
    remaining = list(trials)
    rng.shuffle(remaining)
    out = []

    def run_with(candidate):
        flags = [congruent(t) for t in (previous + out)[-max_run:]] + [congruent(candidate)]
        return len(flags) > max_run and len(set(flags[-(max_run + 1):])) == 1

    def place():
        if not remaining:
            return True
        tried = set()
        for k in range(len(remaining)):
            candidate = remaining[k]
            if tuple(candidate) in tried:
                continue
            tried.add(tuple(candidate))
            last = (previous + out)[-1] if (previous + out) else None
            if last is not None and last[1] == candidate[1]:
                continue
            if run_with(candidate):
                continue
            remaining.pop(k)
            out.append(candidate)
            if place():
                return True
            out.pop()
            remaining.insert(k, candidate)
        return False

    return out if place() else None


def build_main(rng):
    items = []
    for _ in range(BLOCKS):
        pool = [[c, c] for c in ORDER for _ in range(3)] + [[w, i] for w in ORDER for i in ORDER if w != i]
        block = arrange(pool, rng, items, MAX_RUN_MAIN)
        assert block is not None
        items += block
    return items


def build_practice(rng, doubled):
    """12 trials: `doubled` are the two colours that are congruent twice, the
    other two once (6 congruent trials); the 6 incongruent ones use every
    colour as word and as ink the remaining number of times."""
    congruent_counts = {c: (2 if c in doubled else 1) for c in ORDER}
    left = [c for c in ORDER for _ in range(3 - congruent_counts[c])]  # incongruent: inks, and words alike
    while True:
        words = list(left)
        rng.shuffle(words)
        if all(w != i for w, i in zip(words, left)):
            break
    trials = [[c, c] for c in ORDER for _ in range(congruent_counts[c])] + [[w, i] for w, i in zip(words, left)]
    return arrange(trials, rng, [], MAX_RUN_PRACTICE)


def problems_in_main(items):
    found = []
    if len(items) != MAIN_LENGTH:
        found.append(f"length {len(items)}, not {MAIN_LENGTH}")
    if any(len(t) != 2 or t[0] not in ORDER or t[1] not in ORDER for t in items):
        return found + ["a trial that is not a pair of colour ids"]
    if sum(congruent(t) for t in items) != MAIN_LENGTH // 2:
        found.append("congruent trials are not half")
    for color in ORDER:
        if sum(t[0] == color for t in items) != MAIN_LENGTH // 4:
            found.append(f"word {color} not {MAIN_LENGTH // 4} times")
        if sum(t[1] == color for t in items) != MAIN_LENGTH // 4:
            found.append(f"ink {color} not {MAIN_LENGTH // 4} times")
        if sum(t == [color, color] for t in items) != 12:
            found.append(f"congruent {color} not 12 times")
    pairs = Counter(tuple(t) for t in items if not congruent(t))
    if set(pairs.values()) != {BLOCKS} or len(pairs) != 12:
        found.append("an incongruent pair is not four times")
    if any(a[1] == b[1] for a, b in zip(items, items[1:])):
        found.append("the same ink twice in a row")
    if longest_run(items) > MAX_RUN_MAIN:
        found.append(f"more than {MAX_RUN_MAIN} trials of one condition in a row")
    for start in range(0, len(items), BLOCK_LENGTH):
        block = items[start:start + BLOCK_LENGTH]
        if sum(congruent(t) for t in block) != 12:
            found.append(f"block from trial {start + 1} is not half congruent")
        for color in ORDER:
            if sum(t == [color, color] for t in block) != 3:
                found.append(f"block from trial {start + 1}: congruent {color} not three times")
        if len(Counter(tuple(t) for t in block if not congruent(t))) != 12:
            found.append(f"block from trial {start + 1}: not every incongruent pair once")
    return found


def problems_in_practice(items):
    found = []
    if len(items) != PRACTICE_LENGTH:
        found.append(f"length {len(items)}, not {PRACTICE_LENGTH}")
    if any(len(t) != 2 or t[0] not in ORDER or t[1] not in ORDER for t in items):
        return found + ["a trial that is not a pair of colour ids"]
    if sum(congruent(t) for t in items) != PRACTICE_LENGTH // 2:
        found.append("congruent trials are not half")
    for color in ORDER:
        if sum(t[1] == color for t in items) != 3:
            found.append(f"ink {color} not three times")
        if sum(t[0] == color for t in items) != 3:
            found.append(f"word {color} not three times")
    if any(a[1] == b[1] for a, b in zip(items, items[1:])):
        found.append("the same ink twice in a row")
    if longest_run(items) > MAX_RUN_PRACTICE:
        found.append(f"more than {MAX_RUN_PRACTICE} trials of one condition in a row")
    return found


def generate():
    rng = random.Random(SEED)
    main = build_main(rng)
    first = build_practice(rng, ["red", "blue"])
    second = build_practice(rng, ["green", "yellow"])
    while second == first:
        second = build_practice(rng, ["green", "yellow"])
    return {
        "sequence_version": VERSION,
        "colors_version": json.loads(COLORS_PATH.read_text())["colors_version"],
        "seed": SEED,
        "order": ORDER,
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
