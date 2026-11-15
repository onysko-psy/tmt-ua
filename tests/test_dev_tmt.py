"""Checks of the TMT options page and of the scale for dev links (task T1.1)
in Chromium and WebKit: real sizes in mm from the calibration, the fallback
without one, switching the options, and the bundled fonts.

Run from the app/ folder: ../.venv/bin/python -m unittest tests.test_dev_tmt -v
"""

import json
import unittest

from playwright.sync_api import expect

from harness import AppTestCase, TMT_POINTS

PX_PER_MM = 380 / 85.6  # harness.calibrate() sets the card to 380 px
FALLBACK = 96 / 25.4
TOOL = "?mode=dev&tool=tmt"

SAVED = "localStorage.setItem('tmtua.dev.calibration', JSON.stringify(" \
    "{pxPerMm: 5, dpr: window.devicePixelRatio, suspect: false, savedAt: '2026-11-11T18:00:00Z'}));"

# How different two characters look in a font: differing pixels as a share
# of all inked pixels, ink boxes centred on each other.
GLYPH_DIFFERENCE = """async ([family, weight, a, b]) => {
  await document.fonts.load(`${weight} 200px '${family}'`, a + b);
  const mask = (ch) => {
    const c = document.createElement('canvas'); c.width = 400; c.height = 400;
    const g = c.getContext('2d');
    g.font = `${weight} 240px '${family}'`;
    const m = g.measureText(ch);
    g.fillText(ch, 200 - (m.actualBoundingBoxRight - m.actualBoundingBoxLeft) / 2, 300);
    return g.getImageData(0, 0, 400, 400).data;
  };
  const x = mask(a), y = mask(b);
  let differ = 0, ink = 0;
  for (let i = 3; i < x.length; i += 4) {
    const p = x[i] > 127, q = y[i] > 127;
    differ += p !== q; ink += p || q;
  }
  return differ / ink;
}"""


class TmtOptionsTest(AppTestCase):
    def open_tool(self, browser, init_script=SAVED, **options):
        context, receiver = self.new_context(browser, init_script=init_script, **options)
        page, errors = self.open(browser, TOOL, context=context)
        page.locator(".tmt-field").wait_for()
        return page, errors, receiver

    def labels(self, page):
        return page.locator(".tmt-circle").evaluate_all("nodes => nodes.map(n => n.dataset.label)")

    def test_field_is_drawn_in_mm_from_the_saved_calibration(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, receiver = self.open_tool(browser)
                field = page.locator(".tmt-field").bounding_box()
                self.assertAlmostEqual(field["width"], 240 * 5, delta=1)
                self.assertAlmostEqual(field["height"], 150 * 5, delta=1)
                # The decided stimuli (decisions 127, 128): part B opens first, for the font choice.
                self.assertEqual(page.locator(".tmt-field").get_attribute("data-layout"), "b-1")
                self.assertEqual(self.labels(page), "1 А 2 Б 3 В 4 Г 5 Ґ 6 Д 7 Е 8 Є 9 Ж 10 З 11 И 12 І 13".split())
                circle = page.locator(".tmt-circle circle").first.bounding_box()
                self.assertAlmostEqual(circle["width"], 11 * 5, delta=1)  # outline included
                # Capital letters and digits are 4.5 mm tall: the font size follows from the font's own proportions.
                font = page.evaluate("window.tmtuaOptions.current().font")
                size = float(page.locator(".tmt-circle text").first.get_attribute("font-size"))
                self.assertAlmostEqual(size * font["cap"], 4.5, delta=0.01)
                # Circle 1 lies where the layout puts it: units of 1/100 of the field height from the centre.
                x, y = page.evaluate("window.tmtuaOptions.current().layout.points[0]")
                self.assertAlmostEqual(circle["x"] + circle["width"] / 2, field["x"] + (120 + x * 1.5) * 5, delta=1)
                self.assertAlmostEqual(circle["y"] + circle["height"] / 2, field["y"] + (75 + y * 1.5) * 5, delta=1)
                expect(page.locator(".tmt-scale")).to_contain_text("5,00 px/мм")
                self.assertEqual(page.locator(".tmt-scale .tmt-warn").count(), 0)
                self.assertEqual(receiver.requests, [])
                self.assertEqual(errors, [])

    def test_without_calibration_the_page_says_sizes_are_approximate(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _ = self.open_tool(browser, init_script=None)
                field = page.locator(".tmt-field").bounding_box()
                self.assertAlmostEqual(field["width"], 240 * FALLBACK, delta=1)
                expect(page.locator(".tmt-scale .tmt-warn")).to_contain_text("Масштаб приблизний")
                self.assertEqual(page.evaluate("window.tmtuaOptions.scale.source"), "fallback")
                self.assertEqual(errors, [])

    def test_dev_calibration_is_remembered_for_the_page_and_for_single_blocks(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, _ = self.new_context(browser)
                page, errors = self.open(browser, "?mode=dev&only=calibration", context=context)
                self.calibrate(page, 380)
                page.locator(".dev-square").wait_for()
                page.get_by_role("button", name="Далі").click()
                page.get_by_role("link", name="Стимули TMT").click()
                page.locator(".tmt-field").wait_for()
                field = page.locator(".tmt-field").bounding_box()
                self.assertAlmostEqual(field["width"], 240 * PX_PER_MM, delta=1)
                self.assertEqual(page.evaluate("window.tmtuaOptions.scale.source"), "dev_saved")

                # A dev link that skips the calibration block gets the same scale.
                page.goto(self.base + "?mode=dev&only=tmt_a")
                self.tmt_lead(page, "TMT, частина A").wait_for()
                scale = page.evaluate("window.tmtua.ctx.scale()")
                self.assertEqual(scale["source"], "dev_saved")
                self.assertAlmostEqual(scale["pxPerMm"], PX_PER_MM, places=6)
                self.assertEqual(errors, [])

    def test_single_block_without_any_calibration_uses_the_fallback(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors = self.open(browser, "?mode=dev&only=tmt_a")
                self.tmt_lead(page, "TMT, частина A").wait_for()
                scale = page.evaluate("window.tmtua.ctx.scale()")
                self.assertEqual(scale["source"], "fallback")
                self.assertAlmostEqual(scale["pxPerMm"], FALLBACK, places=6)
                self.assertEqual(errors, [])

    def test_only_dev_mode_remembers_the_calibration_and_has_the_tool(self):
        browser = self.browsers[0]
        context, _ = self.new_context(browser)
        page, errors = self.open(browser, "?mode=pilot&tool=tmt", context=context)
        self.assertEqual(page.locator(".tmt-field").count(), 0)  # an ordinary pilot session started
        for block in self.session_blocks(page):
            self.pass_block(page, *block)
            if block[0] == "calibration":
                break
        page.get_by_role("button", name="Увімкнути повноекранний режим").wait_for()
        self.assertIsNone(page.evaluate("localStorage.getItem('tmtua.dev.calibration')"))
        self.assertEqual(errors, [])

    def test_switching_parts(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _ = self.open_tool(browser)
                # Sizes and layouts are decided: nothing on the page changes them.
                self.assertEqual(page.get_by_role("button", name="240×150").count(), 0)
                self.assertEqual(page.locator('[data-set="layout"]').count(), 0)
                expect(page.locator(".tmt-layout-note")).to_contain_text("версія 1")

                page.get_by_role("button", name="A", exact=True).click()
                self.assertEqual(page.locator(".tmt-field").get_attribute("data-layout"), "a-1")
                self.assertEqual(self.labels(page), [str(i) for i in range(1, 26)])
                page.keyboard.press("ArrowDown")
                self.assertEqual(page.locator(".tmt-field").get_attribute("data-layout"), "b-1")
                page.keyboard.press("ArrowDown")
                self.assertEqual(page.locator(".tmt-field").get_attribute("data-layout"), "practice_a-1")
                self.assertEqual(self.labels(page), "1 2 3 4 5 6 7 8".split())
                page.get_by_role("button", name="Пробна B").click()
                self.assertEqual(self.labels(page), "1 А 2 Б 3 В 4 Г".split())

                # The decided font (decision 131); nothing on the page changes it.
                text = page.locator(".tmt-circle text").first
                self.assertEqual(text.get_attribute("font-family"), "'Montserrat SemiBold TMT'")
                self.assertEqual(text.get_attribute("font-weight"), "600")
                self.assertEqual(page.locator('[data-set="font"]').count(), 0)
                expect(page.locator(".tmt-layout-note")).to_contain_text("шрифт Montserrat SemiBold")

                page.get_by_label("лінії шляху").check()
                page.get_by_label("хрестик").check()
                self.assertEqual(page.locator(".tmt-path").count(), 1)
                self.assertEqual(page.locator(".tmt-cross").count(), 1)
                self.assertEqual(page.locator(".tmt-word").count(), 0)  # no start and end words (decision 129)

                # The choice survives a reload.
                page.reload()
                page.locator(".tmt-field").wait_for()
                self.assertEqual(page.locator(".tmt-field").get_attribute("data-layout"), "practice_b-1")
                self.assertEqual(page.locator(".tmt-path").count(), 1)

                # The panel hides to leave the field alone, and comes back.
                page.keyboard.press("h")
                expect(page.locator(".tmt-panel")).to_be_hidden()
                page.keyboard.press("h")
                expect(page.locator(".tmt-panel")).to_be_visible()

                page.get_by_role("button", name="Літери зблизька").click()
                self.assertEqual(page.locator(".tmt-specimen .tmt-circle").count(), 18)
                self.assertEqual(errors, [])

    def test_sizes_come_from_the_parameters(self):
        browser = self.browsers[0]
        context, _ = self.new_context(browser, init_script=SAVED)
        page, errors = self.open(browser, TOOL + "&set.tmt.circleMm=12&set.tmt.fieldWidthMm=256", context=context)
        page.locator(".tmt-field").wait_for()
        self.assertAlmostEqual(page.locator(".tmt-field").bounding_box()["width"], 256 * 5, delta=1)
        self.assertAlmostEqual(page.locator(".tmt-circle circle").first.bounding_box()["width"], 12 * 5, delta=1)
        self.assertEqual(errors, [])

    def test_trying_a_layout(self):
        """"Try it" is the same run as in a session (tmt/run.js); the run
        itself is checked in test_tmt.py."""
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, receiver = self.open_tool(browser)
                page.get_by_role("button", name="Пробна B").click()
                page.keyboard.press("t")
                expect(page.locator(".tmt-panel")).to_be_hidden()
                page.locator(".tmt-run").wait_for()
                expect(page.locator(".tmt-run .tmt-circle").first).to_be_hidden()
                expect(page.locator(".tmt-start-hint")).to_have_text("Натисніть хрестик, щоб почати")
                expect(page.locator(".tmt-corner-label")).to_have_text("Пробна спроба")
                expect(page.locator(".tmt-trial-note")).to_be_visible()

                points = page.evaluate(TMT_POINTS)
                circles = points["circles"]
                self.assertEqual(len(circles), 8)
                page.mouse.click(*points["corner"])  # not the cross: nothing starts
                expect(page.locator(".tmt-run .tmt-circle").first).to_be_hidden()
                page.mouse.click(*points["cross"])
                expect(page.locator(".tmt-run .tmt-circle").first).to_be_visible()
                self.assertEqual(page.locator(".tmt-cross").count(), 0)

                page.mouse.click(*circles[0])
                page.mouse.click(*circles[2])  # 2 instead of А
                self.assertEqual(page.locator(".tmt-wrong").count(), 1)
                self.assertEqual(page.locator(".tmt-line").count(), 0)
                page.mouse.click(*points["corner"])  # beside the circles
                page.mouse.click(*circles[1])
                self.assertEqual(page.locator(".tmt-wrong").count(), 0)
                self.assertEqual(page.locator(".tmt-line").count(), 1)
                page.mouse.click(*circles[1])  # the circle the line ends at: not an error
                for point in circles[2:]:
                    page.mouse.click(*point)
                expect(page.locator(".tmt-panel")).to_be_visible()
                expect(page.locator(".tmt-trial-result")).to_contain_text(
                    "помилок 1 (не та ціль 0, чергування 1), повторних кліків 1, кліків повз 1")
                self.assertEqual(page.locator(".tmt-run").count(), 0)  # the plain view is back
                result = page.evaluate("window.tmtuaOptions.lastRun")
                self.assertEqual((result["part"], result["status"], result["time_limit_ms"]),
                                 ("practice_b", "complete", None))  # the practice has no limit
                self.assertEqual(receiver.requests, [])

                # Esc gives up a try and brings the plain view back.
                page.keyboard.press("t")
                page.locator(".tmt-run").wait_for()
                page.keyboard.press("Escape")
                expect(page.locator(".tmt-panel")).to_be_visible()
                self.assertEqual(page.locator(".tmt-run").count(), 0)
                expect(page.locator(".tmt-circle").first).to_be_visible()

                # A test part stops at the time limit, as in a session.
                page.goto(self.base + TOOL + "&set.tmt.timeLimitMs=600")
                page.locator(".tmt-field").wait_for()
                page.get_by_role("button", name="A", exact=True).click()
                page.keyboard.press("t")
                page.locator(".tmt-run").wait_for()
                points = page.evaluate(TMT_POINTS)
                page.mouse.click(*points["cross"])
                page.mouse.click(*points["circles"][0])
                expect(page.locator(".tmt-trial-result")).to_contain_text("ліміт часу (1 с), пройдено 1 з 25")
                self.assertEqual(errors, [])

    def test_field_that_does_not_fit_is_reported(self):
        browser = self.browsers[0]
        page, errors, _ = self.open_tool(browser, viewport={"width": 1000, "height": 700})
        expect(page.locator(".tmt-fit .tmt-warn")).to_have_text("не влазить")
        self.assertEqual(errors, [])

    def test_bundled_fonts_tell_the_look_alikes_apart(self):
        """Decision 121: in the bundled font (decision 131) the digit 3 has
        its flat top and Ґ its hook. Thresholds sit a few points under what
        Montserrat SemiBold measures in Chromium and WebKit."""
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _ = self.open_tool(browser)
                fonts = page.evaluate("window.tmtuaOptions.fonts")
                self.assertEqual([font["id"] for font in fonts], ["montserrat-semibold"])
                for font in fonts:
                    loaded = page.evaluate(
                        "([family, weight]) => document.fonts.check(`${weight} 20px '${family}'`, 'АҐЄІ3')",
                        [font["family"], font["weight"]])
                    self.assertTrue(loaded, font["id"])
                    for pair, least in (("З3", 0.30), ("ГҐ", 0.08), ("ЕЄ", 0.30), ("ИІ", 0.60), ("І1", 0.40), ("Б6", 0.25), ("В8", 0.20)):
                        difference = page.evaluate(GLYPH_DIFFERENCE, [font["family"], font["weight"], *pair])
                        self.assertGreater(difference, least, (font["id"], pair))
                self.assertEqual(errors, [])

    def test_layouts_file_on_the_page_is_the_checked_one(self):
        browser = self.browsers[0]
        page, errors, _ = self.open_tool(browser)
        served = page.evaluate("window.tmtuaOptions.data")
        stored = json.loads((self.app_dir() / "stimuli" / "tmt-layout.json").read_text())
        self.assertEqual(served, stored)

    @staticmethod
    def app_dir():
        from harness import APP_DIR
        return APP_DIR


if __name__ == "__main__":
    unittest.main()
