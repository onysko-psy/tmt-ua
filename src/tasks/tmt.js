import { HtmlButtonResponse } from '../lib.js';
import { texts } from '../texts.uk.js';
import { TmtPlugin } from '../plugins/tmt.js';
import { STYLE } from '../tmt/stimuli.js';

// Blocks "tmt_a" and "tmt_b" (T1.2, T1.3): the instruction, the practice, the
// screen before the test, the test itself, and (T1.4) the derived columns
// B-A and B/A that part B adds to its message.
//
// The practice (decisions 58, 107-109) runs the same field as the test but
// without the time limit and with the corner label. It counts as passed when
// it has no errors (clicks beside the circles and repeated clicks are not
// errors). After a failed attempt the practice is not stopped: the attempt
// runs to the end, then a screen follows: "try again" after the first
// failure, the hint after the second and later ones. After the last allowed
// attempt (practiceMaxAttempts) the session ends with the status
// practice_failed, and neither the screen before the test nor the test run.

const partOf = (block) => block.id.replace('tmt_', ''); // 'a' or 'b'

// Options of a run (tmt/run.js) for a part: 'a', 'b', 'practice_a' or
// 'practice_b'. Sizes come from the parameters, the layout from
// stimuli/tmt-layout.json, the scale from the calibration.
export function tmtConfig(part, ctx) {
  const p = ctx.params.tmt;
  const { layout, font } = ctx.stimuli.tmt;
  const practice = part.startsWith('practice');
  return {
    part,
    layout: layout.layouts[part],
    fieldMm: { w: p.fieldWidthMm, h: p.fieldHeightMm },
    areaUnits: layout.fields[part],
    circleMm: p.circleMm,
    letterMm: p.letterMm,
    font,
    pxPerMm: ctx.scale().pxPerMm,
    style: STYLE,
    timeLimitMs: practice ? null : p.timeLimitMs, // the practice has no limit
    trajectoryHz: p.trajectoryHz,
    startHint: texts.tmt.startHint,
    cornerLabel: practice ? texts.tmt.practiceLabel : '',
  };
}

export function tmtScreens(block, ctx) {
  const part = partOf(block);
  const t = ctx.params.tmt;
  const words = texts.tmt[part];
  ctx.tmt ??= {};
  const state = { result: null, during: null, practice: { attempts: [], passed: false } };
  ctx.tmt[part] = state;

  const { practice } = state;
  const trying = () => !practice.passed && practice.attempts.length < t.practiceMaxAttempts;
  const screen = (stimulus, button, extra = {}) => ({
    type: HtmlButtonResponse,
    stimulus: `<div class="screen">${stimulus}</div>`,
    choices: [button],
    ...extra,
  });

  const intro = screen(words.intro, texts.tmt.practiceButton);
  const attempt = {
    type: TmtPlugin,
    config: () => tmtConfig(`practice_${part}`, ctx),
    on_result: (result) => {
      // The cursor trajectory is kept for the test only (decisions 61 and
      // the author's answer of 16.11.2026); every click of every attempt stays.
      const { trajectory, ...record } = result;
      practice.attempts.push({ attempt: practice.attempts.length + 1, ...record });
      practice.passed = record.errors_n === 0;
      if (!practice.passed && !trying()) ctx.end('practice_failed');
    },
  };
  // Between attempts: after the first failure "try again", after the second
  // and later ones the hint (decisions 58, 109).
  // (jsPsych takes conditional_function only on a timeline, not on a trial.)
  const between = {
    timeline: [
      {
        timeline: [screen(words.retry, texts.tmt.retryButton)],
        conditional_function: () => practice.attempts.length < t.practiceHintAfterAttempts,
      },
      {
        timeline: [screen(words.hint, texts.tmt.retryButton)],
        conditional_function: () => practice.attempts.length >= t.practiceHintAfterAttempts,
      },
    ],
    conditional_function: trying,
  };
  const practiceLoop = { timeline: [attempt, between], loop_function: trying };

  const beforeTest = { timeline: [screen(words.main, texts.tmt.mainButton)], conditional_function: () => practice.passed };
  const test = {
    type: TmtPlugin,
    config: () => tmtConfig(part, ctx),
    // What happens during the test itself, apart from the whole task with
    // its instructions and practice (decisions 133, 135).
    on_test_start: () => ctx.monitor.startSpan('test'),
    on_test_end: () => {
      state.during = ctx.monitor.endSpan();
    },
    on_result: (result) => {
      state.result = result;
    },
  };
  const timeout = {
    timeline: [
      {
        type: HtmlButtonResponse,
        stimulus: `<div class="screen">${texts.tmt.timeout}</div>`,
        choices: [texts.common.next],
      },
    ],
    conditional_function: () => state.result?.status === 'timeout',
  };
  return [intro, practiceLoop, beforeTest, { timeline: [test], conditional_function: () => practice.passed }, timeout];
}

// B-A (ms) and B/A (3 decimals). A PROPOSAL, not an approved decision: both
// are filled only when BOTH parts ended complete. On a timeout time_ms is the
// limit itself, so the difference would be false; then both stay null.
export function tmtDerived(a, b) {
  const both = a?.status === 'complete' && b?.status === 'complete';
  const ok = both && Number.isFinite(a.time_ms) && Number.isFinite(b.time_ms) && a.time_ms > 0;
  return {
    tmt_b_minus_a_ms: ok ? b.time_ms - a.time_ms : null,
    tmt_b_over_a: ok ? Math.round((b.time_ms / a.time_ms) * 1000) / 1000 : null,
  };
}

export function tmtMessage(block, ctx) {
  const part = partOf(block);
  const state = ctx.tmt?.[part];
  const attempts = state?.practice.attempts ?? [];
  // Nothing to report if the participant never got to the field.
  if (!state?.result && attempts.length === 0) return null;
  const p = `${block.id}_`;
  const t = ctx.params.tmt;
  const summary = { [`${p}practice_attempts_n`]: attempts.length };
  const log = { practice: { max_attempts: t.practiceMaxAttempts, attempts } };
  // The test did not run when the practice failed (status practice_failed).
  if (state.result) {
    const { clicks, trajectory, ...run } = state.result;
    Object.assign(summary, {
      [`${p}status`]: run.status,
      [`${p}time_ms`]: run.time_ms,
      [`${p}targets_done`]: run.targets_done,
      [`${p}errors_n`]: run.errors_n,
      [`${p}err_wrong_target_n`]: run.err_wrong_target_n,
      // Numbers and letters alternate only in part B.
      ...(part === 'b' && { [`${p}err_alternation_n`]: run.err_alternation_n }),
      [`${p}repeat_n`]: run.repeat_n,
      [`${p}miss_n`]: run.miss_n,
    });
    for (const [key, value] of Object.entries(state.during ?? {})) summary[`${p}test_${key}`] = value;
    // Part B sees both parts; if part A did not run (dev link only=tmt_b), the columns stay empty.
    if (part === 'b') Object.assign(summary, tmtDerived(ctx.tmt?.a?.result, state.result));
    const { layout } = ctx.stimuli.tmt;
    if (part === 'a') summary.layout_version = String(layout.layout_version);
    Object.assign(log, {
      ...run,
      layout_version: String(layout.layout_version),
      field_mm: [t.fieldWidthMm, t.fieldHeightMm],
      circle_mm: t.circleMm,
      letter_mm: t.letterMm,
      font: t.font,
      scale_source: ctx.scale().source,
      during_test: state.during,
      clicks,
      trajectory,
    });
  }
  return { summary, log };
}
