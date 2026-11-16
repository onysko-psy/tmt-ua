import { HtmlButtonResponse } from '../lib.js';
import { texts } from '../texts.uk.js';
import { SartPlugin } from '../plugins/sart.js';

// Block "sart" (T3.3): the instruction, the training with one repeat, the
// screen before the main part, the countdown and the main part of 225 trials.
//
// Training (decisions 85, 159, 160): 18 trials; after a wrong one (a press on
// the 3 or a missed digit) a hint under the mask for 1.5 s; with 9 or more of
// the 16 digits other than 3 missed the training is repeated once, with
// another list of 18 trials; then the main part follows in any case, and the
// results and the repeat are recorded. Main part (decisions 66, 89, 116):
// 225 trials in a fixed order, no feedback, a countdown of 3 s without digits
// first.

// Options of a run (sart/run.js) for 'practice' or 'main'. The look and the
// sequences come from stimuli/.
export function sartConfig(mode, ctx, attempt = 0) {
  const p = ctx.params.sart;
  const { look, sequence } = ctx.stimuli.sart;
  const training = mode === 'practice';
  return {
    mode,
    look,
    area: look.area,
    items: training ? sequence.practice[attempt].slice(0, p.practiceTrials) : sequence.main.slice(0, p.mainTrials),
    nogoDigit: sequence.nogo_digit,
    limits: {
      digitMs: p.digitMs,
      maskMs: p.maskMs,
      feedbackMs: p.feedbackMs,
      countdownMs: p.countdownMs,
      fastMs: p.fastMs,
      measureFrames: p.measureFrames,
      frameMsOverride: p.frameMsOverride,
    },
    texts: { countdown: texts.sart.countdown, noGo: texts.sart.feedbackNoGo, miss: texts.sart.feedbackMiss },
    font: ctx.stimuli.tmt.font,
    pxPerMm: ctx.scale().pxPerMm,
  };
}

export function sartScreens(block, ctx) {
  const p = ctx.params.sart;
  const state = { practice: [], main: null, during: null };
  ctx.sart = state;

  const screen = (stimulus, button) => ({
    type: HtmlButtonResponse,
    stimulus: `<div class="screen">${stimulus}</div>`,
    choices: [button],
  });
  const attempt = (number) => ({
    type: SartPlugin,
    config: () => sartConfig('practice', ctx, number - 1),
    on_result: (result) => {
      state.practice.push({ attempt: number, ...result });
    },
  });
  // (jsPsych takes conditional_function only on a timeline, not on a trial.)
  const repeat = {
    timeline: [screen(texts.sart.trainingRepeat, texts.sart.practiceButton), attempt(2)],
    conditional_function: () => state.practice[0].omission_n >= p.practiceRepeatAtOmissions,
  };
  const main = {
    type: SartPlugin,
    config: () => sartConfig('main', ctx),
    // The main part itself, apart from the instruction, the training and the
    // countdown (the same as in the TMT, the coding and Stroop, decisions 133,
    // 135): only in the log.
    on_test_start: () => ctx.monitor.startSpan('test'),
    on_test_end: () => {
      state.during = ctx.monitor.endSpan();
    },
    on_result: (result) => {
      state.main = result;
    },
  };
  return [
    {
      type: HtmlButtonResponse,
      // The last line of the Stroop task comes first (decision 162).
      stimulus: () => `<div class="screen"><p>${texts.stroop.done}</p>${texts.sart.intro}</div>`,
      choices: [texts.sart.practiceButton],
    },
    attempt(1),
    repeat,
    screen(texts.sart.main, texts.sart.mainButton),
    main,
  ];
}

// The timing of one run, for the summary and the log.
const timingOf = (r) => ({
  frame_ms: r.frame_ms,
  refresh_hz: r.refresh_hz,
  measure_ok: r.measure_ok,
  frames_measured: r.frames_measured,
  override_ms: r.override_ms,
  digit_frames: r.digit_frames,
  total_frames: r.total_frames,
  digit_mean_ms: r.digit_mean_ms,
  digit_dev_mean_ms: r.digit_dev_mean_ms,
  digit_dev_max_ms: r.digit_dev_max_ms,
  mask_mean_ms: r.mask_mean_ms,
});

export function sartMessage(block, ctx) {
  const state = ctx.sart;
  // Nothing to report if the participant never got to the first trial.
  if (!state || (state.practice.length === 0 && !state.main)) return null;
  const { look, sequence } = ctx.stimuli.sart;
  const p = ctx.params.sart;
  const summary = {
    sart_practice_attempts_n: state.practice.length,
    sart_practice_omissions_1: state.practice[0]?.omission_n ?? null,
    sart_practice_omissions_2: state.practice[1]?.omission_n ?? null,
    sart_practice_commissions_1: state.practice[0]?.commission_n ?? null,
    sart_practice_commissions_2: state.practice[1]?.commission_n ?? null,
    sart_look_version: String(look.look_version),
    sart_sequence_version: String(sequence.sequence_version),
  };
  const log = {
    look: {
      version: look.look_version,
      variant: look.variant,
      bg: look.bg,
      fg: look.fg,
    },
    sequence: { version: sequence.sequence_version, seed: sequence.seed, main_length: sequence.main_length, nogo_digit: sequence.nogo_digit },
    sizes_mm: {
      area: look.area,
      digit_cap: look.digit_cap_mm,
      mask: look.mask_mm,
      hint_cap: look.hint_cap_mm,
      hint_below_center: look.hint_below_center_mm,
    },
    limits: {
      digit_ms: p.digitMs,
      mask_ms: p.maskMs,
      feedback_ms: p.feedbackMs,
      countdown_ms: p.countdownMs,
      fast_ms: p.fastMs,
      measure_frames: p.measureFrames,
    },
    scale_source: ctx.scale().source,
    practice: {
      trials: p.practiceTrials,
      repeat_at_omissions: p.practiceRepeatAtOmissions,
      attempts: state.practice.map((a) => ({ ...a, timing: timingOf(a) })),
    },
  };
  if (state.main) {
    const { trials, keys, ...counts } = state.main;
    Object.assign(summary, {
      sart_commission_n: counts.commission_n, // the main indicator of inhibition (hypothesis 4)
      sart_commission_rate: counts.commission_rate,
      sart_omission_n: counts.omission_n,
      sart_omission_rate: counts.omission_rate,
      sart_hit_n: counts.hit_n,
      sart_withhold_n: counts.withhold_n,
      sart_rt_mean_ms: counts.rt_mean_ms,
      sart_rt_sd_ms: counts.rt_sd_ms,
      sart_rt_cv: counts.rt_cv,
      sart_fast_n: counts.fast_n,
      sart_extra_n: counts.extra_n,
      sart_time_ms: counts.time_ms,
      sart_refresh_hz: counts.refresh_hz,
      sart_digit_frames: counts.digit_frames,
      sart_digit_mean_ms: counts.digit_mean_ms,
      sart_digit_dev_mean_ms: counts.digit_dev_mean_ms,
      sart_digit_dev_max_ms: counts.digit_dev_max_ms,
      sart_mask_mean_ms: counts.mask_mean_ms,
    });
    // Leaving the tab, losing focus and leaving fullscreen during the main part itself
    // (decision 168, as in the TMT and the coding): sart_test_hidden_n, ... .
    for (const [key, value] of Object.entries(state.during ?? {})) summary[`sart_test_${key}`] = value;
    log.main = { ...counts, timing: timingOf(counts), trials, keys, during_test: state.during };
  }
  return { summary, log };
}
