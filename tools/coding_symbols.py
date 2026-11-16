"""Generates the candidate figure sets of the symbol coding task (T3.1,
decision 79; rules K2 of docs/13): strokes only, one thickness, black on
white, no fonts. Writes stimuli/coding-symbol-candidates.json; once the
author has chosen a set (decision 144 onwards), the chosen one is written to
stimuli/coding-symbols.json by `--choose <set id>`.

A figure lives in a 100 x 100 box. Its lines are paths of a fixed thickness
(`stroke`, in box units) with round ends; a dot is a filled circle of radius
`dot_r`. Figures are kept 14 units from the box edge, so that thickness never
touches the edge.

Usage, from app/:
    python tools/coding_symbols.py                # writes the candidates
    python tools/coding_symbols.py --choose A     # writes the chosen set
"""

import json
import math
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
STROKE = 10
DOT_R = 8
VERSION = 1


def fmt(x):
    return f"{x:.1f}".rstrip("0").rstrip(".")


def pt(cx, cy, r, deg):
    a = math.radians(deg)
    return cx + r * math.cos(a), cy + r * math.sin(a)


def poly(*points, close=False):
    d = "M" + " L".join(f"{fmt(x)} {fmt(y)}" for x, y in points)
    return d + (" Z" if close else "")


def arc(cx, cy, r, start, span):
    """An arc clockwise on screen from angle `start` (degrees; 0 = right, 90 = down)."""
    x0, y0 = pt(cx, cy, r, start)
    x1, y1 = pt(cx, cy, r, start + span)
    large = 1 if abs(span) > 180 else 0
    sweep = 1 if span > 0 else 0
    return f"M{fmt(x0)} {fmt(y0)} A{fmt(r)} {fmt(r)} 0 {large} {sweep} {fmt(x1)} {fmt(y1)}"


def circle(cx, cy, r):
    return arc(cx, cy, r, 0, 180) + " " + arc(cx, cy, r, 180, 180).replace("M", "M", 1)


def sym(sid, *paths, dots=()):
    return {"id": sid, "paths": list(paths), "dots": [[x, y] for x, y in dots]}


# ---------- Set A: straight lines and angles ----------
SET_A = [
    sym("a1", poly((16, 84), (16, 58), (44, 58), (44, 30), (84, 30))),  # steps
    sym("a2", poly((16, 16), (62, 16), (62, 62), (16, 62), close=True), poly((38, 38), (84, 38), (84, 84), (38, 84), close=True)),  # two overlapping squares
    sym("a3", poly((16, 38), (16, 16), (38, 16)), poly((62, 84), (84, 84), (84, 62))),  # opposite corners
    sym("a4", poly((50, 14), (86, 50), (50, 86), (14, 50), close=True), dots=[(50, 50)]),  # rhombus with a dot
    sym("a5", poly((16, 16), (60, 16), (84, 40), (84, 84), (16, 84), close=True)),  # square with a cut corner
    sym("a6", poly((16, 28), (64, 28)), poly((16, 50), (84, 50)), poly((16, 72), (44, 72))),  # three bars of unequal length
    sym("a7", poly((62, 14), (30, 54), (70, 54), (38, 88))),  # bolt
    sym("a8", dots=[(50, 22), (24, 72), (76, 72)]),  # three dots
    sym("a9", poly((40, 16), (16, 50), (40, 84)), poly((60, 16), (84, 50), (60, 84))),  # two angle brackets turned outwards
]

# ---------- Set B: arcs and rings ----------
SET_B = [
    sym("b1", arc(50, 58, 30, -60, 300), poly((50, 14), (50, 50))),  # ring open at the top with a stem through the gap
    sym("b2", arc(50, 50, 36, 160, 160), arc(50, 50, 17, -20, 160)),  # two arcs
    sym("b3", "M14 50 C26 20 40 20 50 50 C60 80 74 80 86 50"),  # wave
    sym("b4", arc(50, 72, 30, 180, 180), dots=[(50, 34)]),  # arch with a dot above
    sym("b5", arc(50, 50, 36, 0, 180), arc(50, 50, 16, 180, 180)),  # bowl with an arch inside
    sym("b6", circle(40, 40, 20), circle(62, 62, 20)),  # two rings on a diagonal
    sym("b7", circle(50, 50, 34), circle(40, 40, 11)),  # ring with a small ring inside
    sym("b8", arc(50, 50, 34, 180, 90), arc(50, 50, 34, 0, 90)),  # two opposite quarter arcs
    sym("b9", circle(42, 58, 24), dots=[(78, 22)]),  # ring with a dot outside
]

# ---------- Set C: lines and arcs together ----------
SET_C = [
    sym("c1", arc(50, 66, 30, 180, 180), poly((14, 66), (86, 66))),  # dome on a line
    sym("c2", poly((32, 20), (86, 20), (68, 80), (14, 80), close=True)),  # slanted rectangle
    sym("c3", circle(28, 28, 13), circle(72, 72, 13), poly((38, 38), (62, 62))),  # two rings on a diagonal link
    sym("c4", poly((16, 70), (50, 70), (50, 30)), circle(70, 30, 14)),  # angle ending in a ring
    sym("c5", "M16 84 L16 16 A68 68 0 0 1 84 84 Z"),  # quarter disc
    sym("c6", "M16 16 H58 A26 26 0 0 1 84 42 V84 H16 Z"),  # square with a round corner
    sym("c7", f"M50 50 L{fmt(pt(50, 50, 36, 35)[0])} {fmt(pt(50, 50, 36, 35)[1])} " + arc(50, 50, 36, 35, 290)[arc(50, 50, 36, 35, 290).index("A"):] + " Z"),  # circle with a wedge cut out
    sym("c8", circle(24, 50, 12), poly((36, 50), (66, 50)), dots=[(80, 50)]),  # ring, line, dot
    sym("c9", poly((84, 84), (16, 84), (66, 34)), arc(16, 84, 42, -45, 45)),  # angle with an arc marker
]

# ---------- Set K: the author's choice (decision 144) ----------
# Set C, with its 4th figure replaced by the 3rd of set B (the wave) and its
# 8th by the 7th of set A (the bolt). The figure's position in the key is its
# digit; the ids k1..k9 are the digits.
_BY_ID = {x["id"]: x for part in (SET_A, SET_B, SET_C) for x in part}
SET_K = [dict(_BY_ID[src], id=f"k{i}") for i, src in enumerate(["c1", "c2", "c3", "b3", "c5", "c6", "c7", "a7", "c9"], 1)]

SETS = [
    {"id": "A", "name": "Прямі лінії й кути", "symbols": SET_A},
    {"id": "B", "name": "Дуги й кружечки", "symbols": SET_B},
    {"id": "C", "name": "Лінії й дуги разом", "symbols": SET_C},
    {"id": "K", "name": "Обраний: набір C, 4-та фігурка — хвиля з B, 8-ма — блискавка з A", "symbols": SET_K},
]


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--choose":
        chosen = next(s for s in SETS if s["id"] == sys.argv[2])
        out = {
            "symbols_version": VERSION,
            "set": chosen["id"],
            "name": chosen["name"],
            "box": 100,
            "stroke": STROKE,
            "dot_r": DOT_R,
            "symbols": chosen["symbols"],
        }
        (APP / "stimuli" / "coding-symbols.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
        write_candidates(chosen["id"])
        print("written: coding-symbols.json, set", chosen["id"])
        return
    write_candidates(None)


def write_candidates(chosen):
    """`chosen` is the id of the set the author chose, or None: the dev page
    loads the chosen file only when it is named here."""
    out = {"box": 100, "stroke": STROKE, "dot_r": DOT_R, "chosen": chosen, "sets": SETS}
    (APP / "stimuli" / "coding-symbol-candidates.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print("written: coding-symbol-candidates.json")


if __name__ == "__main__":
    main()
