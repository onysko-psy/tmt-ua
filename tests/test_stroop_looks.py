"""Checks of the candidate looks of the Stroop screen and of their dev page
(task T3.2, stage 1; decisions 88, 90): every variant fits the task area of
240 x 150 mm, its plates do not touch each other or the dot, the four colours
differ and show against the dark background, and the page draws the screen in
real mm. The structure checks need no browser.

Run from the app/ folder: ../.venv/bin/python -m unittest tests.test_stroop_looks -v
"""

import json
import math
import unittest
from pathlib import Path

from harness import AppTestCase

APP = Path(__file__).resolve().parent.parent
DATA = json.loads((APP / "stimuli" / "stroop-candidates.json").read_text())
SAVED = "localStorage.setItem('tmtua.dev.calibration', JSON.stringify(" \
    "{pxPerMm: 5, dpr: window.devicePixelRatio, suspect: false, savedAt: '2026-11-16T18:00:00Z'}));"
TOOL = "?mode=dev&tool=stroop"
# Capital height 0.7 of the font size; widths of the words in em (Montserrat SemiBold).
WORD_EM = {"ЧЕРВОНИЙ": 6.164, "ЗЕЛЕНИЙ": 5.24, "СИНІЙ": 3.509, "ЖОВТИЙ": 4.907}


def luminance(hex_color):
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def placements(spec, order):
    """(id, cx, cy, w, h) of the plates in mm from the dot, as screen.js does."""
    p = spec["plates"]
    if p["layout"] == "arc":
        return [(i, p["radius_mm"] * math.sin(math.radians(a)), p["radius_mm"] * math.cos(math.radians(a)), p["w_mm"], p["h_mm"])
                for i, a in zip(order, p["angles_deg"])]
    step = p["w_mm"] + p["gap_mm"]
    first = -(len(order) - 1) / 2 * step
    return [(i, first + n * step, p["top_below_dot_mm"] + p["h_mm"] / 2, p["w_mm"], p["h_mm"]) for n, i in enumerate(order)]


class LooksStructureTest(unittest.TestCase):
    def test_three_variants_with_the_same_words_and_order(self):
        self.assertEqual([v["id"] for v in DATA["variants"]], ["1", "2", "3"])
        self.assertEqual([w["word"] for w in DATA["words"]], ["ЧЕРВОНИЙ", "ЗЕЛЕНИЙ", "СИНІЙ", "ЖОВТИЙ"])
        self.assertEqual(DATA["order"], ["red", "green", "blue", "yellow"])
        self.assertEqual(DATA["area"], {"w": 240, "h": 150})

    def test_colours_show_against_the_dark_background_and_differ_from_each_other(self):
        for v in DATA["variants"]:
            with self.subTest(variant=v["id"]):
                self.assertLess(luminance(v["bg"]), 0.05)  # dark grey
                for color, hex_color in v["colors"].items():
                    self.assertGreaterEqual(contrast(hex_color, v["bg"]), 3.9, color)  # large graphics need 3:1
                self.assertEqual(len(set(v["colors"].values())), 4)
                # Hue apart: no two colours share more than ... in any channel pattern
                reds = v["colors"]
                self.assertTrue(int(reds["red"][1:3], 16) > 200 and int(reds["red"][3:5], 16) < 120)
                self.assertTrue(int(reds["green"][3:5], 16) > 150 and int(reds["green"][1:3], 16) < 120)
                self.assertTrue(int(reds["blue"][5:7], 16) > 200 and int(reds["blue"][1:3], 16) < 120)
                self.assertTrue(int(reds["yellow"][1:3], 16) > 200 and int(reds["yellow"][3:5], 16) > 190)

    def test_everything_fits_in_the_task_area(self):
        area = DATA["area"]
        for v in DATA["variants"]:
            with self.subTest(variant=v["id"]):
                widest = max(WORD_EM.values()) * v["word_cap_mm"] / 0.7
                self.assertLess(widest, area["w"] - 40)  # the widest word with room at the sides
                top = v["word_above_dot_mm"] + v["word_cap_mm"] / 2
                self.assertLessEqual(top, area["h"] / 2 - 10)
                for _, cx, cy, w, h in placements(v, DATA["order"]):
                    self.assertLessEqual(abs(cx) + w / 2, area["w"] / 2 - 10)
                    self.assertLessEqual(cy + h / 2, area["h"] / 2 - 10)
                    # The plate is below the dot and clear of its clickable zone.
                    self.assertGreater(math.hypot(max(abs(cx) - w / 2, 0), max(cy - h / 2, 0)), v["dot_hit_mm"] / 2 + 5)

    def test_plates_are_apart_and_the_word_is_clear_of_the_dot(self):
        for v in DATA["variants"]:
            with self.subTest(variant=v["id"]):
                rects = placements(v, DATA["order"])
                for n, a in enumerate(rects):
                    for b in rects[n + 1:]:
                        gap_x = abs(a[1] - b[1]) - (a[3] + b[3]) / 2
                        gap_y = abs(a[2] - b[2]) - (a[4] + b[4]) / 2
                        self.assertGreaterEqual(max(gap_x, gap_y), 3, f"{a[0]}/{b[0]}")  # at least 3 mm between plates
                # The word's lower edge is clear of the dot's clickable zone.
                self.assertGreater(v["word_above_dot_mm"] - v["word_cap_mm"] / 2, v["dot_hit_mm"] / 2 + 8)

    def test_arc_plates_are_equally_far_from_the_dot(self):
        v = DATA["variants"][2]
        self.assertEqual(v["plates"]["layout"], "arc")
        self.assertEqual({round(math.hypot(cx, cy), 6) for _, cx, cy, _, _ in placements(v, DATA["order"])}, {v["plates"]["radius_mm"]})


class LooksPageTest(AppTestCase):
    def open_tool(self, browser, init_script=SAVED):
        context, _ = self.new_context(browser, init_script=init_script)
        page, errors = self.open(browser, TOOL, context=context)
        page.locator(".stroop-variant").first.wait_for()
        return page, errors

    def test_the_screen_is_drawn_in_mm_from_the_saved_calibration(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors = self.open_tool(browser)
                self.assertEqual(page.locator(".stroop-variant").count(), 3)
                for v in DATA["variants"]:
                    section = page.locator(f".stroop-variant[data-variant='{v['id']}']")
                    area = section.locator(".stroop-area").bounding_box()
                    self.assertAlmostEqual(area["width"], 240 * 5, delta=1)
                    self.assertAlmostEqual(area["height"], 150 * 5, delta=1)
                    plates = section.locator(".stroop-plate")
                    self.assertEqual(plates.count(), 4)
                    self.assertEqual(plates.evaluate_all("els => els.map(e => e.dataset.color)"), DATA["order"])
                    box = plates.first.bounding_box()
                    self.assertAlmostEqual(box["width"], v["plates"]["w_mm"] * 5, delta=1)
                    self.assertAlmostEqual(box["height"], v["plates"]["h_mm"] * 5, delta=1)
                    word = section.locator(".stroop-word")
                    self.assertEqual(word.get_attribute("data-ink"), "red")
                    self.assertEqual(word.text_content(), "СИНІЙ")
                    self.assertEqual(word.get_attribute("fill"), v["colors"]["red"])
                    # Eight example words, each in its colour.
                    cells = section.locator(".stroop-word-cell")
                    self.assertEqual(cells.count(), 8)
                self.assertEqual(errors, [])

    def test_the_widest_word_measured_in_the_browser_fits(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, _ = self.open_tool(browser)
                for item in page.evaluate("window.tmtuaStroop.info.map(i => ({ id: i.spec.id, widest: i.widest }))"):
                    expected = WORD_EM["ЧЕРВОНИЙ"] * next(v for v in DATA["variants"] if v["id"] == item["id"])["word_cap_mm"] / 0.7
                    self.assertAlmostEqual(item["widest"], expected, delta=2)

    def test_without_calibration_the_page_says_the_sizes_are_approximate(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, _ = self.open_tool(browser, init_script=None)
                self.assertIn("Масштаб приблизний", page.locator(".dev-stroop").inner_text())

    def test_the_dev_menu_links_to_the_page(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, _ = self.open(browser, "?mode=dev")
                self.assertEqual(page.locator("a[href*='tool=stroop']").count(), 1)


if __name__ == "__main__":
    unittest.main()
