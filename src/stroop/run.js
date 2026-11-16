import { eventTime } from '../tmt/run.js';
import { createStroopScreen } from './screen.js';
import { conditionOf, summarize } from './score.js';

// One run of the Stroop task: a training attempt or the main part (T3.2).
// Used by the Stroop plugin (plugins/stroop.js).
//
// A trial (decisions 88, 91, 93): a dot at the centre; the participant clicks
// it; the word appears above it, printed in a colour; the participant clicks
// the plate of that colour (plates carry no words, decision 90); the word
// stays until the answer, at most responseLimitMs (decision 91); then a pause
// of itiMs and the next dot. Reaction time is from the moment the word was
// drawn (the browser's next frame after it was put on the page) to the press
// of the mouse button on the plate (a click is the press, as in the TMT).
//
// What counts as an answer: a press of the main button on a plate while the
// word is on the screen and drawn. Every other press is no answer and no error
// (decision 152): it is counted (`miss_n`: beside the plates while the word is
// on the screen or before it was drawn; `dot_repeat_n`: on the dot again while
// the word is on the screen) and kept in the log with its place and time.
// Presses during the pause, and beside the dot while it waits, are in the
// log only. A trial without an answer in time is a 'timeout'.
//
// Training (decision 92): after every trial the feedback replaces the word for
// feedbackMs (decision 153): right, wrong with the colour of the word's print,
// or too late; main part: none.

const round1 = (x) => Math.round(x * 10) / 10;

// options:
//   look, words, order, area   the look and the colours (stimuli/stroop-colors.json)
//   items                      the trials, as [word, ink] pairs of colour ids
//   mode                       'practice' or 'main'
//   limits                     { responseLimitMs, itiMs, feedbackMs }
//   texts                      { dotHint, right, wrong(inkId), timeout } for training
//   font, pxPerMm              as for the TMT field
//   onStart, onEnd             called when the first dot is drawn and when the run ends
//
// Returns { promise, cancel }; the promise resolves to the result or, after
// cancel(), to null. Times are in ms from the moment the first dot was drawn
// (t_ms), or from the moment the answered word was drawn (rt_ms).
export function runStroop(container, options) {
  const { look, words, order, area, items, mode, limits, texts = {}, font, pxPerMm, onStart, onEnd } = options;
  const training = mode === 'practice';

  const stage = document.createElement('div');
  stage.className = 'stroop-run';
  stage.style.background = look.bg;
  const screen = createStroopScreen({ spec: look, words, order, area, font, pxPerMm, container: stage });
  container.replaceChildren(stage);
  stage.addEventListener('contextmenu', (event) => event.preventDefault());

  const created = performance.now();
  const trials = [];
  const counts = { miss_n: 0, dot_repeat_n: 0 };
  let phase = 'start'; // 'dot', 'word', 'feedback', 'pause', 'done'
  let index = -1;
  let t0 = null; // when the first dot was drawn
  let startedAt = null;
  let dotShownAt = null;
  let wordShownAt = null; // when the word was drawn; null until then
  let dotRt = null;
  let stray = [];
  let timer = null;
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });

  const setPhase = (value) => {
    phase = value;
    stage.dataset.phase = value;
  };

  // The dot of trial i: shown, and its drawing noted for the dot's own time.
  function beginTrial(i) {
    index = i;
    stray = [];
    dotShownAt = null;
    wordShownAt = null;
    dotRt = null;
    stage.dataset.trial = String(i);
    delete stage.dataset.dotShown; // set again once the dot is drawn (for automated checks)
    screen.setWord(null);
    screen.setFeedback(null);
    screen.setDotVisible(true);
    screen.setHint(training ? texts.dotHint : null);
    setPhase('dot');
    requestAnimationFrame(() => {
      if (phase !== 'dot' || index !== i) return;
      dotShownAt = performance.now();
      stage.dataset.dotShown = '1';
      if (t0 === null) {
        t0 = dotShownAt;
        startedAt = new Date().toISOString();
        onStart?.();
      }
    });
  }

  // The dot was pressed: the word comes. Its time starts in the frame that draws it.
  function showWord(t) {
    dotRt = dotShownAt === null ? null : round1(t - dotShownAt);
    const [word, ink] = items[index];
    screen.setHint(null);
    screen.setWord(word, ink);
    setPhase('word');
    const i = index;
    requestAnimationFrame(() => {
      if (phase !== 'word' || index !== i) return;
      wordShownAt = performance.now();
      screen.word.dataset.shown = '1';
      timer = setTimeout(() => endTrial('timeout', null, null), limits.responseLimitMs);
    });
  }

  function endTrial(type, resp, t) {
    if (phase !== 'word') return;
    clearTimeout(timer);
    const [word, ink] = items[index];
    const trial = {
      i: index,
      word,
      ink,
      condition: conditionOf(word, ink),
      type, // 'correct', 'error' or 'timeout'
      resp,
      ok: type === 'correct',
      rt_ms: type === 'timeout' ? null : round1(t - wordShownAt),
      dot_rt_ms: dotRt,
      t_ms: Math.round(wordShownAt - t0),
      miss_n: stray.filter((s) => s.where === 'outside' || s.where === 'before_shown').length,
      dot_repeat_n: stray.filter((s) => s.where === 'dot').length,
      stray,
    };
    trials.push(trial);
    counts.miss_n += trial.miss_n;
    counts.dot_repeat_n += trial.dot_repeat_n;
    screen.setWord(null);
    const last = index === items.length - 1;
    if (last && !training) return finish();
    if (training) {
      const text = type === 'correct' ? texts.right : type === 'error' ? texts.wrong(ink) : texts.timeout;
      screen.setFeedback(text, type);
      setPhase('feedback');
      timer = setTimeout(() => (last ? finish() : pause()), limits.feedbackMs);
    } else {
      pause();
    }
  }

  function pause() {
    screen.setFeedback(null);
    screen.setDotVisible(false);
    screen.setHint(null);
    setPhase('pause');
    timer = setTimeout(() => beginTrial(index + 1), limits.itiMs);
  }

  function cleanup() {
    setPhase('done');
    clearTimeout(timer);
    stage.removeEventListener('pointerdown', onDown);
  }

  function finish() {
    if (phase === 'done') return;
    const t = performance.now();
    cleanup();
    onEnd?.();
    const scores = summarize(trials);
    resolve({
      mode,
      status: training ? 'done' : 'complete',
      time_ms: Math.round(t - t0),
      trials_n: trials.length,
      correct_n: scores.correct_n,
      errors_n: scores.errors_n,
      timeouts_n: scores.timeouts_n,
      miss_n: counts.miss_n,
      dot_repeat_n: counts.dot_repeat_n,
      effect_ms: scores.effect_ms,
      congruent: scores.congruent,
      incongruent: scores.incongruent,
      started_at: startedAt,
      first_shown_ms: Math.round(t0 - created),
      px_per_mm: pxPerMm,
      trials,
    });
  }

  function onDown(event) {
    if (phase === 'done' || event.button !== 0 || event.isPrimary === false) return;
    const t = eventTime(event);
    const hit = event.target instanceof Element ? event.target : null;
    const plate = hit?.closest('.stroop-plate')?.dataset.color ?? null;
    const onDot = Boolean(hit?.closest('.stroop-dot'));
    const note = (where) => stray.push({ t_ms: t0 === null ? null : Math.round(t - t0), where, phase });
    if (phase === 'dot') {
      // The dot has to be drawn first, as with the word.
      if (onDot && dotShownAt !== null && t >= dotShownAt) showWord(t);
      else note(onDot ? 'dot_early' : 'before_dot');
      return;
    }
    if (phase === 'word') {
      if (wordShownAt === null || t < wordShownAt) return note('before_shown');
      if (t - wordShownAt >= limits.responseLimitMs) return endTrial('timeout', null, null);
      if (plate) return endTrial(plate === items[index][1] ? 'correct' : 'error', plate, t);
      return note(onDot ? 'dot' : 'outside');
    }
    // In the feedback and in the pause a press is no answer (log only, on the next trial's record).
    stray.push({ t_ms: t0 === null ? null : Math.round(t - t0), where: 'pause', phase });
  }

  stage.addEventListener('pointerdown', onDown);
  beginTrial(0);

  function cancel() {
    if (phase === 'done') return;
    cleanup();
    resolve(null);
  }

  return { promise, cancel };
}
