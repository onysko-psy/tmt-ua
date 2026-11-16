import { eventTime } from '../tmt/run.js';
import { createSartScreen } from './screen.js';
import { outcomeOf, summarize, planFrames, frameTimeFrom } from './score.js';

// One run of the SART task: a training attempt or the main part (T3.3). Used
// by the SART plugin (plugins/sart.js) and by the timing page (dev-sart-timing.js).
//
// A trial is 1150 ms (decision 66; Robertson et al., 1997): a digit of one of
// five sizes for 250 ms, then the mask (a ring with a cross) for 900 ms. The
// time is set by frames, not by timers: at the start the run measures the
// frame time of this screen (the median gap between frames in the first
// `measureFrames` frames, recorded), takes the number of frames that makes
// 250 ms (15 at 60 Hz, 30 at 120 Hz) and 1150 ms, and changes the picture in
// the first frame that is on or after that many frames from the previous
// change (a frame of requestAnimationFrame, with its own time stamp). Each
// trial starts from the real time of its first frame, so a slow frame is not
// carried into the next trial. For every trial the real time of the digit and
// of the mask is recorded, from the time stamps of the frames in which the
// pictures were drawn.
//
// What counts as an answer (decisions 157, 158): the space bar (event.code
// 'Space'), pressed without Ctrl, Alt or Cmd, not held down (auto-repeat), on
// a digit that has been drawn, up to the moment the next digit was put on the
// screen, and not faster than fastMs after the digit was drawn; the first such
// press of a trial. Reaction time is from the frame in which the digit was
// drawn to the press (the keydown). Other presses are no answers and no
// errors; they are counted (`fast_n`, `extra_n`) or are in the log only, each
// with its reason (`keys`). A press on the no-go digit (3) is a false response
// (commission); no press on another digit is a miss (omission).
//
// Training (decisions 85, 159): after a trial with a commission or an omission
// the next digit waits feedbackMs while the mask and the hint are on the
// screen. Main part: no feedback and no pauses; before it a countdown of
// countdownMs, a text with a bar and no digits (decision 116), which is also
// where the frame time is measured.

const round1 = (x) => Math.round(x * 10) / 10;
const KEY_LOG_LIMIT = 200;

// options:
//   look, area           the look (stimuli/sart-look.json)
//   items                the trials, as [digit, size index] pairs
//   mode                 'practice' or 'main'
//   nogoDigit            the digit not to press (3)
//   limits               { digitMs, maskMs, feedbackMs, countdownMs, fastMs, measureFrames, frameMsOverride }
//   texts                { countdown, noGo, miss }
//   font, pxPerMm        as for the TMT field
//   onStart, onEnd       called when the first digit is drawn and when the run ends
//
// Returns { promise, cancel }; the promise resolves to the result or, after
// cancel(), to null. t_ms is from the frame in which the first digit was drawn.
export function runSart(container, options) {
  const { look, area, items, mode, nogoDigit, limits, texts = {}, font, pxPerMm, onStart, onEnd } = options;
  const training = mode === 'practice';

  const stage = document.createElement('div');
  stage.className = 'sart-run';
  stage.style.background = look.bg;
  const screen = createSartScreen({ spec: look, area, font, pxPerMm, container: stage });
  container.replaceChildren(stage);
  stage.addEventListener('contextmenu', (event) => event.preventDefault());
  // No button is left holding the focus: a space press would press it.
  if (document.activeElement instanceof HTMLElement) document.activeElement.blur();

  const created = performance.now();
  const trials = [];
  const keys = [];
  let keysDropped = 0;
  let phase = 'prepare'; // 'prepare' (countdown or measuring), 'digit', 'mask', 'feedback', 'done'
  let stamps = []; // functions called with the time of the next frame
  let cur = null; // the trial on the screen
  let t0 = null; // when the first digit was drawn
  let startedAt = null;
  let rafId = null;
  let finishing = false;
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });

  // Frame measuring.
  const frameStamps = [];
  const prepareStart = { ts: null };
  let frameMs = null;
  let plan = null;
  let measured = null;

  const setPhase = (value) => {
    phase = value;
    stage.dataset.phase = value;
  };

  function note(reason, event, t, extraFields = {}) {
    if (keys.length >= KEY_LOG_LIMIT) {
      keysDropped += 1;
      return;
    }
    keys.push({ t_ms: t0 === null ? null : round1(t - t0), code: event.code, reason, i: cur?.i ?? null, ...extraFields });
  }

  function startTrial(i, ts) {
    const [digit, size] = items[i];
    const trial = {
      i,
      digit,
      size,
      size_mm: look.digit_cap_mm[size],
      type: null,
      pressed: false,
      rt_ms: null,
      t_ms: null,
      digit_ms: null,
      mask_ms: null,
      feedback_ms: null,
      fast_n: 0,
      extra_n: 0,
      // Internal times (not in the result): the frame in which the picture was put on the page,
      // the frame in which it was first drawn.
      mutTs: ts,
      shownTs: null,
      maskShownTs: null,
      endTs: null,
    };
    cur = trial;
    screen.setHint(null);
    screen.setDigit(digit, size);
    stage.dataset.trial = String(i);
    stage.dataset.digit = String(digit);
    delete stage.dataset.shown;
    setPhase('digit');
    stamps.push((next) => {
      trial.shownTs = next;
      stage.dataset.shown = '1';
      trial.t_ms = t0 === null ? null : round1(next - t0);
      if (t0 === null) {
        t0 = next;
        trial.t_ms = 0;
        startedAt = new Date().toISOString();
        onStart?.();
      }
    });
    return trial;
  }

  // The trial is over (its window closed): its outcome; stamps for its real times.
  function closeTrial(trial, ts) {
    trial.endTs = ts;
    trial.type = outcomeOf(trial.digit, trial.pressed, nogoDigit);
    trials.push(trial);
    stamps.push((next) => {
      trial.mask_ms = round1(next - trial.maskShownTs);
    });
  }

  function step(ts) {
    if (phase === 'prepare') {
      if (prepareStart.ts === null) prepareStart.ts = ts;
      frameStamps.push(ts);
      const countdown = mode === 'main' && limits.countdownMs > 0;
      if (countdown) screen.setCountdown(Math.max(0, 1 - (ts - prepareStart.ts) / limits.countdownMs), texts.countdown);
      else if (frameStamps.length === 1) screen.setMask();
      if (frameMs === null && frameStamps.length >= limits.measureFrames + 5) {
        const median = frameTimeFrom(frameStamps.slice(0, limits.measureFrames + 5));
        const real = median ?? 1000 / 60;
        frameMs = limits.frameMsOverride > 0 ? limits.frameMsOverride : real;
        plan = planFrames(frameMs, limits);
        measured = {
          frame_ms: Math.round(real * 100) / 100,
          refresh_hz: Math.round((1000 / real) * 10) / 10,
          measure_ok: median !== null,
          frames_measured: Math.min(frameStamps.length, limits.measureFrames + 5),
          override_ms: limits.frameMsOverride > 0 ? limits.frameMsOverride : null,
          digit_frames: plan.digit,
          total_frames: plan.total,
        };
        stage.dataset.digitFrames = String(plan.digit);
      }
      if (frameMs !== null && (!countdown || ts - prepareStart.ts >= limits.countdownMs)) {
        screen.setCountdown(null);
        startTrial(0, ts);
      }
      return;
    }
    if (phase === 'digit') {
      if (ts >= cur.mutTs + plan.digit * frameMs - frameMs / 2) {
        screen.setMask();
        setPhase('mask');
        const trial = cur;
        stamps.push((next) => {
          trial.maskShownTs = next;
          trial.digit_ms = round1(next - trial.shownTs);
        });
      }
      return;
    }
    if (phase === 'mask') {
      if (ts < cur.mutTs + plan.total * frameMs - frameMs / 2) return;
      const trial = cur;
      closeTrial(trial, ts);
      const last = trial.i === items.length - 1;
      const wrong = trial.type === 'commission' || trial.type === 'omission';
      if (training && wrong) {
        screen.setHint(trial.type === 'commission' ? texts.noGo : texts.miss);
        stage.dataset.feedback = trial.type;
        setPhase('feedback');
        trial.feedbackStart = ts;
        stamps.push((next) => {
          trial.hintShownTs = next;
        });
        return;
      }
      if (last) {
        finishing = true;
        return;
      }
      startTrial(trial.i + 1, ts);
      return;
    }
    if (phase === 'feedback') {
      const trial = trials[trials.length - 1];
      if (ts < trial.feedbackStart + limits.feedbackMs - frameMs / 2) return;
      delete stage.dataset.feedback;
      if (trial.i === items.length - 1) {
        trial.feedback_ms = round1(ts - trial.hintShownTs);
        finishing = true;
        return;
      }
      startTrial(trial.i + 1, ts);
      stamps.push((shown) => {
        trial.feedback_ms = round1(shown - trial.hintShownTs);
      });
      return;
    }
  }

  function tick(ts) {
    rafId = null;
    if (phase === 'done') return;
    const due = stamps;
    stamps = [];
    for (const stamp of due) stamp(ts);
    if (finishing && stamps.length === 0) return finish(ts);
    if (!finishing) step(ts);
    if (phase !== 'done') rafId = requestAnimationFrame(tick);
  }

  function cleanup() {
    setPhase('done');
    if (rafId !== null) cancelAnimationFrame(rafId);
    window.removeEventListener('keydown', onKey, true);
    window.removeEventListener('keyup', onKeyUp, true);
  }

  function finish(ts) {
    if (phase === 'done') return;
    cleanup();
    onEnd?.();
    const scores = summarize(trials, limits);
    const clean = trials.map(({ mutTs, shownTs, maskShownTs, endTs, feedbackStart, hintShownTs, ...rest }) => rest);
    resolve({
      mode,
      status: training ? 'done' : 'complete',
      time_ms: Math.round(ts - t0),
      trials_n: trials.length,
      ...scores,
      ...measured,
      started_at: startedAt,
      first_shown_ms: Math.round(t0 - created),
      px_per_mm: pxPerMm,
      keys_dropped: keysDropped,
      trials: clean,
      keys,
    });
  }

  function onKey(event) {
    if (phase === 'done') return;
    if (event.code === 'Space') event.preventDefault(); // no scrolling, no button pressed
    const t = eventTime(event);
    let reason = null;
    if (event.repeat) reason = 'repeat';
    else if (event.ctrlKey || event.metaKey || event.altKey) reason = 'modifier';
    else if (event.code !== 'Space') reason = 'not_space';
    else if (phase === 'prepare') reason = 'before_start';
    else if (phase === 'feedback') reason = 'feedback';
    else if (cur.shownTs === null || t < cur.shownTs) reason = 'before_shown';
    else if (cur.endTs !== null && t >= cur.endTs) reason = 'after_end';
    if (reason) return note(reason, event, t);
    const rt = t - cur.shownTs;
    if (rt < limits.fastMs) {
      cur.fast_n += 1;
      return note('fast', event, t, { rt_ms: round1(rt) });
    }
    if (cur.pressed) {
      cur.extra_n += 1;
      return note('second', event, t, { rt_ms: round1(rt) });
    }
    cur.pressed = true;
    cur.rt_ms = round1(rt);
  }

  // A space released on a button that holds the focus would press it.
  function onKeyUp(event) {
    if (event.code === 'Space') event.preventDefault();
  }

  window.addEventListener('keydown', onKey, true);
  window.addEventListener('keyup', onKeyUp, true);
  setPhase('prepare');
  rafId = requestAnimationFrame(tick);

  function cancel() {
    if (phase === 'done') return;
    cleanup();
    resolve(null);
  }

  return { promise, cancel };
}
