"""Checks of the figure sets of the symbol coding task and of their dev page
(task T3.1, stage 1): the sets obey the rules of docs/13 (K2), no figure is a
rotated or mirrored copy of another in its set, and the page draws the key in
real mm. The structure checks need no browser.

Run from the app/ folder: ../.venv/bin/python -m unittest tests.test_coding_symbols -v
"""

import importlib.util
import json
import re
import unittest
from pathlib import Path

from harness import AppTestCase

APP = Path(__file__).resolve().parent.parent
CANDIDATES = json.loads((APP / "stimuli" / "coding-symbol-candidates.json").read_text())
SAVED = "localStorage.setItem('tmtua.dev.calibration', JSON.stringify(" \
    "{pxPerMm: 5, dpr: window.devicePixelRatio, suspect: false, savedAt: '2026-11-16T18:00:00Z'}));"
TOOL = "?mode=dev&tool=coding"


def load_generator():
    spec = importlib.util.spec_from_file_location("coding_symbols", APP / "tools" / "coding_symbols.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SetsStructureTest(unittest.TestCase):
    def test_the_candidate_sets_and_the_chosen_one_have_nine_figures(self):
        self.assertEqual([s["id"] for s in CANDIDATES["sets"]], ["A", "B", "C", "K"])
        for s in CANDIDATES["sets"]:
            with self.subTest(set=s["id"]):
                self.assertEqual(len(s["symbols"]), 9)
                ids = [x["id"] for x in s["symbols"]]
                self.assertEqual(len(set(ids)), 9)
                self.assertTrue(all(i.startswith(s["id"].lower()) for i in ids))

    def test_one_thickness_for_all_and_figures_inside_the_box(self):
        box, stroke = CANDIDATES["box"], CANDIDATES["stroke"]
        self.assertEqual((box, stroke), (100, 10))
        for s in CANDIDATES["sets"]:
            for x in s["symbols"]:
                with self.subTest(symbol=x["id"]):
                    self.assertTrue(x["paths"] or x["dots"])
                    # Lines: the stroke reaches half its thickness beyond a
                    # coordinate. Arc commands carry radii and flags, not
                    # points, so only the end points of arcs are read here.
                    for d in x["paths"]:
                        numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", re.sub(r"A[^A-Za-z]*", lambda m: "A" + " ".join(m.group(0)[1:].split()[5:]) + " ", d))]
                        for n in numbers:
                            self.assertGreaterEqual(n - stroke / 2, 0, d)
                            self.assertLessEqual(n + stroke / 2, box, d)
                    for cx, cy in x["dots"]:
                        r = CANDIDATES["dot_r"]
                        self.assertTrue(r <= cx <= box - r and r <= cy <= box - r, x["id"])

    def test_the_chosen_set_is_the_file_the_app_loads(self):
        # Decision 144: set K; its figure at position i is the digit i.
        chosen = json.loads((APP / "stimuli" / "coding-symbols.json").read_text())
        self.assertEqual(CANDIDATES["chosen"], "K")
        self.assertEqual(chosen["set"], "K")
        self.assertEqual([x["id"] for x in chosen["symbols"]], [f"k{i}" for i in range(1, 10)])
        self.assertEqual(chosen["symbols"], next(s for s in CANDIDATES["sets"] if s["id"] == "K")["symbols"])
        self.assertEqual((chosen["box"], chosen["stroke"], chosen["dot_r"]), (100, 10, 8))
        self.assertEqual(chosen["symbols_version"], 1)

    def test_the_file_is_what_the_generator_writes(self):
        generator = load_generator()
        expected = {"box": 100, "stroke": generator.STROKE, "dot_r": generator.DOT_R,
                    "chosen": CANDIDATES["chosen"], "sets": generator.SETS}
        self.assertEqual(json.loads(json.dumps(expected, ensure_ascii=False)), CANDIDATES)


# Similarity of every pair of figures of a set under the 8 turns and mirrors:
# the share of the union of two normalised 40 x 40 silhouettes they share.
# Calibration: distinct letters that are rotations of each other score 0.95.
PAIRS = """async (data) => {
  const N = 40, S = 200;
  const crop = (g) => {
    const w = g.canvas.width, h = g.canvas.height, d = g.getImageData(0, 0, w, h).data;
    let x0 = w, y0 = h, x1 = -1, y1 = -1;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (d[(y * w + x) * 4 + 3] > 100) {
      x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
    }
    const c = document.createElement('canvas'); c.width = N; c.height = N;
    const k = c.getContext('2d'); k.drawImage(g.canvas, x0, y0, x1 - x0 + 1, y1 - y0 + 1, 0, 0, N, N);
    const o = k.getImageData(0, 0, N, N).data, bits = new Uint8Array(N * N);
    for (let i = 0; i < N * N; i++) bits[i] = o[i * 4 + 3] > 80 ? 1 : 0;
    return bits;
  };
  const draw = (s) => {
    const c = document.createElement('canvas'); c.width = S; c.height = S;
    const g = c.getContext('2d'); g.scale(S / 100, S / 100);
    g.lineWidth = data.stroke; g.lineCap = 'round'; g.lineJoin = 'round';
    for (const d of s.paths) g.stroke(new Path2D(d));
    for (const [x, y] of s.dots) { g.beginPath(); g.arc(x, y, data.dot_r, 0, 7); g.fill(); }
    return crop(g);
  };
  const turns = [(x, y) => [x, y], (x, y) => [N - 1 - x, y], (x, y) => [x, N - 1 - y], (x, y) => [N - 1 - x, N - 1 - y],
    (x, y) => [y, x], (x, y) => [N - 1 - y, x], (x, y) => [y, N - 1 - x], (x, y) => [N - 1 - y, N - 1 - x]];
  const turn = (b, k) => {
    const o = new Uint8Array(N * N);
    for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) { const [u, v] = turns[k](x, y); o[v * N + u] = b[y * N + x]; }
    return o;
  };
  const iou = (a, b) => { let i = 0, u = 0; for (let k = 0; k < N * N; k++) { if (a[k] && b[k]) i++; if (a[k] || b[k]) u++; } return u ? i / u : 0; };
  const out = {};
  for (const set of data.sets) {
    const bits = set.symbols.map(draw);
    let worst = 0, pair = '';
    for (let i = 0; i < bits.length; i++) for (let j = i + 1; j < bits.length; j++) for (let k = 0; k < 8; k++) {
      const v = iou(bits[i], turn(bits[j], k));
      if (v > worst) { worst = v; pair = set.symbols[i].id + '/' + set.symbols[j].id; }
    }
    out[set.id] = { worst, pair };
  }
  return out;
}"""


class CodingSymbolsPageTest(AppTestCase):
    def open_tool(self, browser, init_script=SAVED):
        context, _ = self.new_context(browser, init_script=init_script)
        page, errors = self.open(browser, TOOL, context=context)
        page.locator(".coding-set").first.wait_for()
        return page, errors

    def test_no_figure_is_a_turned_or_mirrored_copy_of_another(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, _ = self.open_tool(browser)
                result = page.evaluate(PAIRS, CANDIDATES)
                for set_id, item in result.items():
                    self.assertLess(item["worst"], 0.75, f"set {set_id}: {item['pair']}")

    def test_the_key_is_drawn_in_mm_from_the_saved_calibration(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors = self.open_tool(browser)
                self.assertEqual(page.locator(".coding-set").count(), 4)
                self.assertEqual(page.locator(".coding-set").first.get_attribute("data-set"), "K")
                sizes = page.evaluate("window.tmtuaCoding.sizes")
                key = page.locator(".coding-key").first.bounding_box()
                self.assertAlmostEqual(key["width"], 9 * sizes["keyCellMm"] * 5, delta=1)
                digits = page.locator(".coding-set[data-set='A'] .coding-key [data-digit]").all_text_contents()
                self.assertEqual(digits, [str(i) for i in range(1, 10)])
                for set_id in "KABC":
                    figures = page.locator(f".coding-set[data-set='{set_id}'] .coding-key .coding-figure")
                    self.assertEqual(figures.count(), 9)
                    # The figure's own size in mm (its bounding box is only the ink).
                    self.assertEqual(float(figures.first.get_attribute("width")), sizes["figureMm"])
                self.assertEqual(errors, [])

    def test_without_calibration_the_page_says_the_sizes_are_approximate(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, _ = self.open_tool(browser, init_script=None)
                self.assertIn("Масштаб приблизний", page.locator(".dev-coding").inner_text())

    def test_size_can_be_changed_in_the_link(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, _ = self.new_context(browser, init_script=SAVED)
                page, _ = self.open(browser, TOOL + "&set.coding.figureMm=10", context=context)
                page.locator(".coding-set").first.wait_for()
                self.assertEqual(float(page.locator(".coding-key .coding-figure").first.get_attribute("width")), 10)
                key = page.locator(".coding-key").first.bounding_box()
                self.assertAlmostEqual(key["width"], 9 * 22 * 5, delta=1)


if __name__ == "__main__":
    unittest.main()
