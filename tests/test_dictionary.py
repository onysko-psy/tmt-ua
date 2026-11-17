"""The data dictionary (docs/20-data-dictionary.md, task T4.2) must name every
column the app sends, and nothing that it does not send. One whole first
session and one retest are run in Chromium, and the columns of their messages
are compared with the first column of the dictionary tables (the placeholders
{task}, {part}, {cond} are expanded; `pss_1` … `pss_10` is a range).

The dictionary lives in the private repository next to the research notes; if
this test is run from the public copy of app/, it is skipped.

Run from the app/ folder: ../.venv/bin/python -m unittest discover -s tests -p "test_dictionary.py" -v
"""

import re
import unittest
from pathlib import Path

import test_session as ts

DICTIONARY = Path(__file__).resolve().parents[2] / "docs" / "20-data-dictionary.md"
TASKS = ["tmt_a", "tmt_b", "coding", "stroop", "sart"]
PARTS = ["tmt_a", "tmt_b"]
CONDITIONS = ["congruent", "incongruent"]
# Columns the receiver adds (the app does not send them).
RECEIVER = {"received_first_at", "received_last_at", "last_seq", "last_block", "log_folder"}


def dictionary_columns(text):
    columns = set()
    for line in text.splitlines():
        match = re.match(r"^\| ((?:`[^`]+`(?:, | … )?)+)\s*\|", line)
        if not match or match.group(1).strip("` ") in ("Стовпець",):
            continue
        cell = match.group(1)
        if "… `pss_10`" in cell or cell.startswith("`pss_1` …"):
            columns.update(f"pss_{n}" for n in range(1, 11))
            continue
        for name in re.findall(r"`([^`]+)`", cell):
            columns.update(expand(name))
    return columns


def expand(name):
    if "{task}" in name:
        return [name.replace("{task}", t) for t in TASKS]
    if "{part}" in name:
        return [name.replace("{part}", p) for p in PARTS]
    if "{cond}" in name:
        return [name.replace("{cond}", c) for c in CONDITIONS]
    return [name]


@unittest.skipUnless(DICTIONARY.exists(), "the dictionary is in the private repository")
class DictionaryTest(ts.SessionCase):
    def sent_columns(self, query, retest):
        context, receiver, page, errors = self.begin(self.browsers[0], query)
        self.run_session(page, retest=retest)
        self.assertEqual(errors, [])
        # the four identifying fields travel in every message beside the summary; the receiver writes them as columns
        return {key for m in receiver.accepted for key in m["summary"]} | {
            key for m in receiver.accepted for key in ("session_id", "participant_code", "mode", "app_version")}

    def test_every_sent_column_is_in_the_dictionary_and_the_other_way_round(self):
        documented = dictionary_columns(DICTIONARY.read_text(encoding="utf-8"))
        first = self.sent_columns(f"?mode=pilot{ts.FAST}", False)
        retest = self.sent_columns(f"?mode=pilot&r=k7m2x9pq4a{ts.FAST}", True)
        sent = first | retest
        self.assertEqual(sorted(sent - documented), [], "sent, but not in the dictionary")
        # everything documented is sent in a whole session, but what the receiver adds
        # and the reason of an exclusion (which a whole session never has)
        missing = documented - sent - RECEIVER - {"exclusion_reason"}
        self.assertEqual(sorted(missing), [], "in the dictionary, but never sent")


if __name__ == "__main__":
    unittest.main()
