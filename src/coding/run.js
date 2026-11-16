import { eventTime } from '../tmt/run.js';
import { figure, keySize, renderKey, renderFrame, KEY_LINE_MM } from './symbols.js';

// One run of the symbol coding task: a training attempt or the main part
// (T3.1). A figure stands in the frame under the key; the participant presses
// the digit that stands under it in the key. Used by the coding plugin
// (plugins/coding.js).
//
// What counts as an answer (decisions 146-148): a key 1-9 of the top row or of
// the numeric pad, told by the key's place (event.code), so any layout works;
// pressed without Ctrl, Alt or Cmd, not held down (auto-repeat), and made
// after the figure was drawn, and, in the main part, before the time is up.
// Every other key press is no answer and no error; it is counted apart and
// kept in the log with its reason (`extra_keys`).
//
// Training: a wrong digit shows the hint and the figure stays until the right
// digit is pressed (decision 80). Main part: a wrong digit counts as an
// error and the next figure comes at once (decision 81); the clock runs from
// the moment the first figure is drawn (decision 146) and no time is shown
// (decision 149).

// The digit a key stands for, from its place on the keyboard.
export const KEY_DIGITS = Object.fromEntries(
  [1, 2, 3, 4, 5, 6, 7, 8, 9].flatMap((d) => [[`Digit${d}`, d], [`Numpad${d}`, d]]),
);

const round1 = (x) => Math.round(x * 10) / 10;

// options:
//   symbols, spec   the figures of the set and their drawing spec (symbols.js)
//   items           the figures to show, as digits 1-9, in order
//   mode            'practice' or 'main'
//   durationMs      the time of the main part, null in training
//   sizes           { figureMm, keyCellMm, keyDigitMm, frameMm }
//   font, pxPerMm   as for the TMT field
//   keyHint         text under the figure
//   wrongText       the training's hint after a wrong digit
//   onStart, onEnd  called when the first figure is drawn and when the run ends
//
// Returns { promise, cancel }; the promise resolves to the result or, after
// cancel(), to null. Times are in ms from the moment the first figure was
// drawn (t_ms) or from the moment the answered figure was drawn (rt_ms).
export function runCoding(container, options) {
  const { symbols, spec, items, mode, durationMs = null, sizes, font, pxPerMm, keyHint, wrongText = '', onStart, onEnd } = options;
  const training = mode === 'practice';
  const mm = (x) => `${x * pxPerMm}px`;

  const stage = document.createElement('div');
  stage.className = 'coding-run';
  stage.style.setProperty('--coding-text', mm(5)); // text 5 mm tall
  const column = document.createElement('div');
  column.className = 'coding-column';
  const key = renderKey({ symbols, spec, sizes, font, pxPerMm });
  const frame = renderFrame({ symbol: symbols[0], spec, sizes, pxPerMm });
  const hint = document.createElement('p');
  hint.className = 'coding-hint';
  hint.textContent = keyHint;
  const wrong = document.createElement('p');
  wrong.className = 'coding-wrong';
  wrong.textContent = wrongText;
  wrong.style.visibility = 'hidden';
  column.style.width = mm(keySize(sizes).w);
  frame.style.marginTop = mm(22);
  column.append(key, frame, hint, wrong);
  stage.append(column);
  container.replaceChildren(stage);

  const created = performance.now();
  const answers = [];
  const extra = [];
  const counts = { correct: 0, errors: 0 };
  let phase = 'running'; // 'running', 'done'
  let index = -1;
  let shownAt = null; // when the current figure was drawn; null until then
  let t0 = null; // when the first figure was drawn
  let startedAt = null;
  let limitTimer = null;
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });

  // Puts item i in the frame and notes when the browser draws it: in the
  // frame before the next paint. Keys before that moment are no answers.
  function show(i) {
    index = i;
    shownAt = null;
    const symbol = symbols[items[i] - 1];
    const old = frame.querySelector('.coding-figure');
    const next = figure(symbol, spec, (sizes.frameMm - sizes.figureMm) / 2, (sizes.frameMm - sizes.figureMm) / 2, sizes.figureMm);
    old.replaceWith(next);
    frame.dataset.symbol = String(items[i]);
    delete frame.dataset.shown; // set again once the figure is drawn (for automated checks)
    wrong.style.visibility = 'hidden';
    requestAnimationFrame(() => {
      if (phase !== 'running' || index !== i) return;
      shownAt = performance.now();
      frame.dataset.shown = '1';
      if (t0 === null) {
        t0 = shownAt;
        startedAt = new Date().toISOString();
        if (durationMs !== null) limitTimer = setTimeout(() => finish('complete', t0 + durationMs), durationMs);
        onStart?.();
      }
    });
  }

  function cleanup() {
    phase = 'done';
    clearTimeout(limitTimer);
    window.removeEventListener('keydown', onKey, true);
  }

  function finish(status, t) {
    if (phase !== 'running') return;
    cleanup();
    onEnd?.();
    const elapsed = Math.round(t - t0);
    resolve({
      mode,
      status, // main: 'complete' (time up) or 'exhausted' (all figures answered); training: 'done'
      time_ms: status === 'complete' && durationMs !== null ? durationMs : elapsed,
      elapsed_ms: elapsed,
      duration_ms: durationMs,
      items_n: items.length,
      correct_n: counts.correct,
      errors_n: counts.errors,
      answers_n: answers.length,
      extra_keys_n: extra.length,
      sequence_exhausted: status === 'exhausted' ? 1 : 0,
      started_at: startedAt,
      first_shown_ms: Math.round(t0 - created),
      px_per_mm: pxPerMm,
      answers,
      extra_keys: extra,
    });
  }

  function onKey(event) {
    if (phase !== 'running') return;
    const t = eventTime(event);
    const digit = KEY_DIGITS[event.code] ?? null;
    let reason = null;
    if (event.repeat) reason = 'repeat';
    else if (event.ctrlKey || event.metaKey || event.altKey) reason = 'modifier';
    else if (digit === null) reason = 'not_digit';
    else if (shownAt === null || t < shownAt) reason = 'before_shown';
    else if (durationMs !== null && t - t0 >= durationMs) reason = 'late';
    if (reason) {
      extra.push({ t_ms: t0 === null ? null : Math.round(t - t0), code: event.code, reason });
      if (reason === 'late') finish('complete', t0 + durationMs);
      return;
    }
    event.preventDefault();
    const expected = items[index];
    const ok = digit === expected;
    answers.push({
      i: index,
      symbol: expected,
      pressed: digit,
      ok,
      rt_ms: round1(t - shownAt),
      t_ms: round1(t - t0),
    });
    if (ok) counts.correct += 1;
    else counts.errors += 1;
    if (training && !ok) {
      wrong.style.visibility = 'visible';
      return;
    }
    if (index === items.length - 1) return finish(training ? 'done' : 'exhausted', t);
    show(index + 1);
  }

  window.addEventListener('keydown', onKey, true);
  show(0);

  function cancel() {
    if (phase === 'done') return;
    cleanup();
    resolve(null);
  }

  return { promise, cancel };
}
