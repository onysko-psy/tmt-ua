import { HtmlButtonResponse } from '../lib.js';
import { texts } from '../texts.uk.js';
import { TmtPlugin } from '../plugins/tmt.js';
import { STYLE } from '../tmt/stimuli.js';

// Blocks "tmt_a" and "tmt_b". For now (T1.2) each is the test itself: the
// cross, the field, the time limit. The instructions and the practice come
// in T1.3, the final set of columns in T1.4.

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
  ctx.tmt ??= {};
  const state = { result: null, during: null };
  ctx.tmt[part] = state;

  // Stand-in for the instructions and the practice (T1.3); seen only during
  // development, so its wording stays here rather than in texts.uk.js.
  const lead = {
    type: HtmlButtonResponse,
    stimulus: `<p class="tmt-lead">${block.label}: основний тест. Інструкції й пробна спроба з’являться в Т1.3.</p>`,
    choices: ['Почати'],
  };
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
  return [lead, test, timeout];
}

export function tmtMessage(block, ctx) {
  const part = partOf(block);
  const state = ctx.tmt?.[part];
  if (!state?.result) return null;
  const { clicks, trajectory, ...run } = state.result;
  const p = `${block.id}_`;
  const summary = {
    [`${p}status`]: run.status,
    [`${p}time_ms`]: run.time_ms,
    [`${p}targets_done`]: run.targets_done,
    [`${p}errors_n`]: run.errors_n,
    [`${p}err_wrong_target_n`]: run.err_wrong_target_n,
    // Numbers and letters alternate only in part B.
    ...(part === 'b' && { [`${p}err_alternation_n`]: run.err_alternation_n }),
    [`${p}repeat_n`]: run.repeat_n,
    [`${p}miss_n`]: run.miss_n,
  };
  for (const [key, value] of Object.entries(state.during ?? {})) summary[`${p}test_${key}`] = value;
  const { layout } = ctx.stimuli.tmt;
  if (part === 'a') summary.layout_version = String(layout.layout_version);
  const t = ctx.params.tmt;
  return {
    summary,
    log: {
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
    },
  };
}
