import { HtmlButtonResponse } from '../lib.js';
import { texts } from '../texts.uk.js';
import { CodingPlugin } from '../plugins/coding.js';

// Block "coding" (T3.1): the instruction, the training with one repeat, the
// screen before the main part, the main part of 90 s.
//
// Training (decision 80): 10 figures without a time limit; a wrong digit
// shows the hint and the right one has to be pressed. With 3 or more wrong
// digits the training is repeated once, with another list of 10 figures;
// then the main part follows in any case, and the errors and the repeat are
// recorded. Main part (decisions 81, 146-149): 90 s from the first figure
// drawn, no hints, a wrong digit is an error and the next figure comes at
// once, no time shown.

// Options of a run (coding/run.js) for 'practice' or 'main'. Sizes come from
// the parameters, the figures and the sequence from stimuli/.
export function codingConfig(mode, ctx, attempt = 0) {
  const p = ctx.params.coding;
  const { set, sequence } = ctx.stimuli.coding;
  const training = mode === 'practice';
  return {
    mode,
    symbols: set.symbols,
    spec: { box: set.box, stroke: set.stroke, dot_r: set.dot_r },
    items: training ? sequence.practice[attempt].slice(0, p.practiceItems) : sequence.items,
    durationMs: training ? null : p.durationMs,
    sizes: { figureMm: p.figureMm, keyCellMm: p.keyCellMm, keyDigitMm: p.keyDigitMm, frameMm: p.frameMm },
    font: ctx.stimuli.tmt.font,
    pxPerMm: ctx.scale().pxPerMm,
    keyHint: texts.coding.keyHint,
    wrongText: texts.coding.trainingWrong,
  };
}

export function codingScreens(block, ctx) {
  const p = ctx.params.coding;
  const state = { practice: [], main: null, during: null };
  ctx.coding = state;

  const screen = (stimulus, button) => ({
    type: HtmlButtonResponse,
    stimulus: `<div class="screen">${stimulus}</div>`,
    choices: [button],
  });
  const attempt = (number) => ({
    type: CodingPlugin,
    config: () => codingConfig('practice', ctx, number - 1),
    on_result: (result) => {
      const { answers, extra_keys, ...counts } = result;
      state.practice.push({ attempt: number, ...counts, answers, extra_keys });
    },
  });
  // (jsPsych takes conditional_function only on a timeline, not on a trial.)
  const repeat = {
    timeline: [screen(texts.coding.trainingRepeat, texts.coding.practiceButton), attempt(2)],
    conditional_function: () => state.practice[0].errors_n >= p.practiceRepeatAtErrors,
  };
  const main = {
    type: CodingPlugin,
    config: () => codingConfig('main', ctx),
    // The main part itself, apart from the instruction and the training
    // (the same as in TMT, decisions 133, 135): only in the log.
    on_test_start: () => ctx.monitor.startSpan('test'),
    on_test_end: () => {
      state.during = ctx.monitor.endSpan();
    },
    on_result: (result) => {
      state.main = result;
    },
  };
  return [
    screen(texts.coding.intro, texts.coding.practiceButton),
    attempt(1),
    repeat,
    screen(texts.coding.main, texts.coding.mainButton),
    main,
  ];
}

export function codingMessage(block, ctx) {
  const state = ctx.coding;
  // Nothing to report if the participant never got to the first figure.
  if (!state || (state.practice.length === 0 && !state.main)) return null;
  const { set, sequence } = ctx.stimuli.coding;
  const p = ctx.params.coding;
  const summary = {
    coding_practice_attempts_n: state.practice.length,
    coding_practice_errors_1: state.practice[0]?.errors_n ?? null,
    coding_practice_errors_2: state.practice[1]?.errors_n ?? null,
    coding_symbols_version: String(set.symbols_version),
    coding_sequence_version: String(sequence.sequence_version),
  };
  const log = {
    symbols: { set: set.set, version: set.symbols_version, ids: set.symbols.map((symbol) => symbol.id) },
    sequence: { version: sequence.sequence_version, length: sequence.length, seed: sequence.seed },
    sizes_mm: { figure: p.figureMm, key_cell: p.keyCellMm, key_digit: p.keyDigitMm, frame: p.frameMm },
    scale_source: ctx.scale().source,
    practice: {
      items: p.practiceItems,
      repeat_at_errors: p.practiceRepeatAtErrors,
      attempts: state.practice,
    },
  };
  if (state.main) {
    const { answers, extra_keys, ...counts } = state.main;
    Object.assign(summary, {
      coding_correct_n: counts.correct_n, // the main indicator (protocol)
      coding_errors_n: counts.errors_n,
      coding_answers_n: counts.answers_n,
      coding_extra_keys_n: counts.extra_keys_n,
      coding_time_ms: counts.time_ms,
      coding_sequence_exhausted: counts.sequence_exhausted,
    });
    log.main = { ...counts, answers, extra_keys, during_test: state.during };
  }
  return { summary, log };
}
