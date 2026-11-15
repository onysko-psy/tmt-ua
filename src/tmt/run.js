import { renderField, svgEl } from './field.js';

// One run of a TMT field: the practice or the test of part A or B (T1.2).
// Used by the TMT plugin (plugins/tmt.js) and by "Try it" on the dev page
// (dev-tmt.js), so both behave alike.
//
// The run starts with a click on the central cross: the circles appear and
// the clock starts (decision 59). A click on the expected circle draws the
// line to it; a click on another circle turns that circle red until the next
// right click, and the line stays where it was. The run ends with the right
// click on the last circle, or when the time limit runs out (decision 57).
//
// A click is the press of the main button (pointerdown), not its release:
// the press is when the participant made the choice, and a press followed by
// a small slip of the cursor still counts.

const CROSS_SLACK_MM = 1; // the cross takes clicks this far beyond its arms
const END_HOLD_MS = 400; // the last line stays on the screen this long

export const labelKind = (label) => (/^\d+$/.test(label) ? 'number' : 'letter');

// Scores the clicks of a run. click(index) takes the index of the clicked
// circle, or null for a click beside the circles, and returns
// { expected, target, result, error_type? }:
//   correct  the expected circle;
//   error    another circle. error_type is 'alternation' when a number was
//            clicked where a letter was due or the other way round (part B
//            only), otherwise 'wrong_target';
//   repeat   the circle the line ends at now, clicked again — typically a
//            double click. Not an error and not highlighted (decision 134);
//            an earlier circle of the path is a wrong target;
//   miss     beside the circles: counted apart, not an error (decision 63).
export function createScorer(labels) {
  const counts = { errors: 0, wrong_target: 0, alternation: 0, repeat: 0, miss: 0 };
  let next = 0;
  return {
    counts,
    next: () => next,
    done: () => next === labels.length,
    click(index) {
      const expected = labels[next];
      if (index === null) {
        counts.miss += 1;
        return { expected, target: null, result: 'miss' };
      }
      const target = labels[index];
      if (index === next) {
        next += 1;
        return { expected, target, result: 'correct' };
      }
      if (index === next - 1) {
        counts.repeat += 1;
        return { expected, target, result: 'repeat' };
      }
      const error_type = labelKind(target) === labelKind(expected) ? 'wrong_target' : 'alternation';
      counts.errors += 1;
      counts[error_type] += 1;
      return { expected, target, result: 'error', error_type };
    },
  };
}

const round1 = (x) => Math.round(x * 10) / 10;

// The moment the browser registered the event, on the performance.now()
// clock. Some browsers may report event times on another clock; then the
// time the handler runs is taken.
function eventTime(event) {
  const now = performance.now();
  return event.timeStamp > 0 && Math.abs(now - event.timeStamp) < 5000 ? event.timeStamp : now;
}

// options: what renderField takes (layout, fieldMm, areaUnits, circleMm,
// letterMm, font, pxPerMm, style), plus
//   part          'a', 'b', 'practice_a' or 'practice_b', kept in the result
//   timeLimitMs   null for no limit (practice)
//   trajectoryHz  how often the cursor position is kept (decision 61)
//   startHint     text under the cross until the run starts
//   cornerLabel   small text in the corner of the field (practice)
//   showBorder    dashed outline of the field (dev page only)
//   onStart, onEnd  called at the click on the cross and when the run ends
//
// Returns { promise, cancel }. The promise resolves to the result of the run
// (see finish below), or to null after cancel().
//
// Coordinates in the result are in mm from the centre of the field, x to the
// right and y down; times are in ms from the click on the cross.
export function runTmt(container, options) {
  const {
    part,
    layout,
    fieldMm,
    circleMm,
    pxPerMm,
    style,
    timeLimitMs = null,
    trajectoryHz = 30,
    startHint = '',
    cornerLabel = '',
    showBorder = false,
    onStart,
    onEnd,
  } = options;

  const unit = fieldMm.h / 100;
  const centres = layout.points.map(([x, y]) => [x * unit, y * unit]);
  const scorer = createScorer(layout.labels);

  const stage = document.createElement('div');
  stage.className = 'tmt-run';
  const svg = renderField({ ...options, show: { cross: true, border: showBorder } });
  svg.classList.add('tmt-waiting');
  if (startHint) {
    svg.append(
      svgEl('text', { class: 'tmt-start-hint', x: 0, y: style.crossMm / 2 + 9, 'font-size': 4.2, 'text-anchor': 'middle' }, startHint),
    );
  }
  if (cornerLabel) {
    svg.append(
      svgEl('text', { class: 'tmt-corner-label', x: 4 - fieldMm.w / 2, y: 7 - fieldMm.h / 2, 'font-size': 3.6 }, cornerLabel),
    );
  }
  stage.append(svg);
  container.replaceChildren(stage);
  const circles = [...svg.querySelectorAll('.tmt-circle')];

  const shownAt = performance.now();
  const clicks = [];
  const trajectory = [];
  let phase = 'waiting'; // 'waiting' for the cross, 'running', 'done'
  let t0 = null;
  let startedAt = null;
  let crossStray = 0; // clicks elsewhere before the click on the cross
  let view = null; // what the field looked like on the page at the start
  let latest = null; // last cursor position not yet written to the trajectory
  let limitTimer = null;
  let sampler = null;
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });

  // Position of an event in mm from the centre of the field. Measured
  // against the field as it is drawn now, so scrolling does not matter.
  const position = (event) => {
    const rect = svg.getBoundingClientRect();
    return [
      ((event.clientX - rect.left) / rect.width - 0.5) * fieldMm.w,
      ((event.clientY - rect.top) / rect.height - 0.5) * fieldMm.h,
    ];
  };

  // Index of the circle a point lies in, or null.
  const circleAt = (x, y) => {
    let found = null;
    let nearest = circleMm / 2;
    centres.forEach(([cx, cy], index) => {
      const distance = Math.hypot(x - cx, y - cy);
      if (distance <= nearest) {
        found = index;
        nearest = distance;
      }
    });
    return found;
  };

  const writeSample = () => {
    if (!latest) return;
    trajectory.push([Math.round(latest.t), round1(latest.x), round1(latest.y)]);
    latest = null;
  };

  function begin(t, x, y) {
    phase = 'running';
    t0 = t;
    startedAt = new Date().toISOString();
    const rect = svg.getBoundingClientRect();
    view = {
      field_px: [round1(rect.width), round1(rect.height)],
      page_px: [window.innerWidth, window.innerHeight],
      fits:
        rect.left >= -0.5 &&
        rect.top >= -0.5 &&
        rect.right <= window.innerWidth + 0.5 &&
        rect.bottom <= window.innerHeight + 0.5,
    };
    svg.classList.remove('tmt-waiting');
    svg.querySelector('.tmt-cross').remove();
    svg.querySelector('.tmt-start-hint')?.remove();
    trajectory.push([0, round1(x), round1(y)]);
    sampler = setInterval(writeSample, 1000 / trajectoryHz);
    // A hidden tab runs timers late; the limit is then checked on the next click too.
    if (timeLimitMs !== null) limitTimer = setTimeout(() => finish('timeout', performance.now()), timeLimitMs);
    onStart?.();
  }

  function cleanup() {
    phase = 'done';
    clearTimeout(limitTimer);
    clearInterval(sampler);
    stage.removeEventListener('pointerdown', onDown);
    stage.removeEventListener('contextmenu', onMenu);
    window.removeEventListener('pointermove', onMove, true);
  }

  function finish(status, t) {
    if (phase !== 'running') return;
    writeSample();
    cleanup();
    onEnd?.();
    const elapsed = Math.round(t - t0);
    const { counts } = scorer;
    const result = {
      part,
      layout_id: layout.id,
      status, // 'complete' or 'timeout'
      time_ms: status === 'timeout' ? timeLimitMs : elapsed,
      elapsed_ms: elapsed, // at a timeout: when the run actually stopped
      targets_total: layout.labels.length,
      targets_done: scorer.next(),
      errors_n: counts.errors,
      err_wrong_target_n: counts.wrong_target,
      err_alternation_n: counts.alternation,
      repeat_n: counts.repeat,
      miss_n: counts.miss,
      started_at: startedAt,
      cross_wait_ms: Math.round(t0 - shownAt),
      cross_stray_n: crossStray,
      time_limit_ms: timeLimitMs,
      px_per_mm: pxPerMm,
      ...view,
      trajectory_hz: trajectoryHz,
      clicks,
      trajectory,
    };
    if (status === 'complete') setTimeout(() => resolve(result), END_HOLD_MS);
    else resolve(result);
  }

  function onDown(event) {
    if (phase === 'done' || event.button !== 0 || event.isPrimary === false) return;
    const t = eventTime(event);
    const [x, y] = position(event);
    if (phase === 'waiting') {
      if (Math.hypot(x, y) > style.crossMm / 2 + CROSS_SLACK_MM) crossStray += 1;
      else begin(t, x, y);
      return;
    }
    const elapsed = t - t0;
    if (timeLimitMs !== null && elapsed >= timeLimitMs) return finish('timeout', t);

    const index = circleAt(x, y);
    const outcome = scorer.click(index);
    clicks.push({
      t: Math.round(elapsed),
      x: round1(x),
      y: round1(y),
      ...outcome,
      pointer: event.pointerType || 'unknown',
    });
    latest = { t: elapsed, x, y };
    writeSample();

    if (outcome.result === 'error') circles[index].classList.add('tmt-wrong');
    if (outcome.result !== 'correct') return;
    for (const wrong of svg.querySelectorAll('.tmt-wrong')) wrong.classList.remove('tmt-wrong');
    if (index > 0) {
      const [x1, y1] = centres[index - 1];
      const [x2, y2] = centres[index];
      // Under the circles, so that a line ends at the outline of a circle.
      svg.insertBefore(
        svgEl('line', { class: 'tmt-line', x1, y1, x2, y2, stroke: '#000', 'stroke-width': style.lineMm }),
        circles[0],
      );
    }
    if (scorer.done()) finish('complete', t);
  }

  function onMove(event) {
    if (phase !== 'running') return;
    const [x, y] = position(event);
    latest = { t: eventTime(event) - t0, x, y };
  }

  const onMenu = (event) => event.preventDefault(); // no context menu over the field

  stage.addEventListener('pointerdown', onDown);
  stage.addEventListener('contextmenu', onMenu);
  window.addEventListener('pointermove', onMove, true);

  function cancel() {
    if (phase === 'done') return;
    cleanup();
    resolve(null);
  }

  return { promise, cancel };
}
