import { eventTime } from '../tmt/run.js';
import { createStroopScreen } from './screen.js';
import { conditionOf, summarize } from './score.js';

// One run of the Stroop task: a training attempt or the main part (T3.2).
// Used by the Stroop plugin (plugins/stroop.js).
//
// A trial (decisions 91, 170): a dot at the centre, which stays on the screen
// as a point to look at and takes no clicks; itiMs after the previous answer
// (or after the start, or after the feedback) the word appears above it,
// printed in a colour; the participant clicks the plate of that colour (plates
// carry no words, decision 90); the word stays until the answer, at most
// responseLimitMs (decision 91). Reaction time is from the moment the word was
// drawn (the browser's next frame after it was put on the page) to the press
// of the mouse button on the plate (a click is the press, as in the TMT).
//
// What counts as an answer: a press of the main button on a plate while the
// word is on the screen and drawn. Every other press is no answer and no error
// (decision 152): it is counted (`miss_n`: anywhere but on a plate while the
// word is on the screen or before it was drawn) and kept in the log with its
// place and time. Presses during the pause and the feedback are in the log
// only. A trial without an answer in time is a 'timeout'.
//
// Training (decision 92): after every trial the feedback replaces the word for
// feedbackMs (decisions 153, 170): right, wrong with the colour of the word's
// print, or too late; main part: none.

const round1 = (x) => Math.round(x * 10) / 10;

// options:
//   look, words, order, area   the look and the colours (stimuli/stroop-colors.json)
//   items                      the trials, as [word, ink] pairs of colour ids
//   mode                       'practice' or 'main'
//   limits                     { responseLimitMs, itiMs, feedbackMs }
//   texts                      { right, wrong(inkId), timeout } for training
//   font, pxPerMm              as for the TMT field
//   onStart, onEnd             called when the dot of the first trial is drawn and when the run ends
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
  const counts = { miss_n: 0 };
  let phase = 'start'; // 'pause' (before the word), 'word', 'feedback', 'done'
  let index = -1;
  let t0 = null; // when the first dot was drawn
  let startedAt = null;
  let wordShownAt = null; // when the word was drawn; null until then
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

  // Trial i begins: the dot is on the screen and itiMs later the word comes.
  // The very first dot is noted (the run's time zero) in the frame that draws it.
  function beginTrial(i) {
    index = i;
    stray = [];
    wordShownAt = null;
    stage.dataset.trial = String(i);
    screen.setWord(null);
    screen.setFeedback(null);
    screen.setDotVisible(true);
    setPhase('pause');
    if (t0 === null) {
      requestAnimationFrame(() => {
        if (phase === 'done' || t0 !== null) return;
        t0 = performance.now();
        stage.dataset.started = '1'; // for automated checks
        startedAt = new Date().toISOString();
        onStart?.();
      });
    }
    timer = setTimeout(showWord, limits.itiMs);
  }

  // The word is put on the page; its time starts in the frame that draws it.
  function showWord() {
    if (phase !== 'pause') return;
    const [word, ink] = items[index];
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
      t_ms: Math.round(wordShownAt - t0),
      miss_n: stray.filter((s) => s.where === 'outside' || s.where === 'before_shown').length,
      stray,
    };
    trials.push(trial);
    counts.miss_n += trial.miss_n;
    screen.setWord(null);
    const last = index === items.length - 1;
    if (last && !training) return finish();
    if (training) {
      const text = type === 'correct' ? texts.right : type === 'error' ? texts.wrong(ink) : texts.timeout;
      screen.setFeedback(text, type);
      setPhase('feedback');
      timer = setTimeout(() => (last ? finish() : beginTrial(index + 1)), limits.feedbackMs);
    } else {
      beginTrial(index + 1);
    }
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
    const note = (where) => stray.push({ t_ms: t0 === null ? null : Math.round(t - t0), where, phase });
    if (phase === 'word') {
      if (wordShownAt === null || t < wordShownAt) return note('before_shown');
      if (t - wordShownAt >= limits.responseLimitMs) return endTrial('timeout', null, null);
      if (plate) return endTrial(plate === items[index][1] ? 'correct' : 'error', plate, t);
      return note('outside');
    }
    // In the pause and in the feedback a press is no answer (log only).
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
