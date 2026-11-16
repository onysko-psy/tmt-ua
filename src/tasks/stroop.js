import { HtmlButtonResponse } from '../lib.js';
import { texts } from '../texts.uk.js';
import { StroopPlugin } from '../plugins/stroop.js';

// Block "stroop" (T3.2): the instruction, the training with one repeat, the
// screen before the main part, the main part of 96 trials.
//
// Training (decision 92): 12 trials with feedback after each (decision 153);
// with fewer than 9 correct the training is repeated once, with another list
// of 12 trials; then the main part follows in any case, and the results and
// the repeat are recorded. Main part (decisions 83, 84, 91, 93): 96 trials,
// half of them congruent, no feedback, up to 5 s to answer.

export function stroopWrongText(ink) {
  return texts.stroop.feedbackWrong.replace('{color}', texts.stroop.colorInstrumental[ink]);
}

// Options of a run (stroop/run.js) for 'practice' or 'main'. The look, the
// colours and the sequences come from stimuli/.
export function stroopConfig(mode, ctx, attempt = 0) {
  const p = ctx.params.stroop;
  const { look, sequence } = ctx.stimuli.stroop;
  const training = mode === 'practice';
  return {
    mode,
    look,
    words: Object.fromEntries(look.words.map((w) => [w.id, w.word])),
    order: look.order,
    area: look.area,
    items: training ? sequence.practice[attempt].slice(0, p.practiceTrials) : sequence.main.slice(0, p.mainTrials),
    limits: { responseLimitMs: p.responseLimitMs, itiMs: p.itiMs, feedbackMs: p.feedbackMs },
    texts: training
      ? {
          right: texts.stroop.feedbackRight,
          wrong: stroopWrongText,
          timeout: texts.stroop.feedbackTimeout,
        }
      : {},
    font: ctx.stimuli.tmt.font,
    pxPerMm: ctx.scale().pxPerMm,
  };
}

export function stroopScreens(block, ctx) {
  const p = ctx.params.stroop;
  const state = { practice: [], main: null, during: null };
  ctx.stroop = state;

  const screen = (stimulus, button) => ({
    type: HtmlButtonResponse,
    stimulus: `<div class="screen">${stimulus}</div>`,
    choices: [button],
  });
  const attempt = (number) => ({
    type: StroopPlugin,
    config: () => stroopConfig('practice', ctx, number - 1),
    on_result: (result) => {
      const { trials, ...counts } = result;
      state.practice.push({ attempt: number, ...counts, trials });
    },
  });
  // (jsPsych takes conditional_function only on a timeline, not on a trial.)
  const repeat = {
    timeline: [screen(texts.stroop.trainingRepeat, texts.stroop.practiceButton), attempt(2)],
    conditional_function: () => state.practice[0].correct_n < p.practiceMinCorrect,
  };
  const main = {
    type: StroopPlugin,
    config: () => stroopConfig('main', ctx),
    // The main part itself, apart from the instruction and the training
    // (the same as in the TMT and the coding, decisions 133, 135): only in the log.
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
      // The last line of the coding task comes first (decision 154).
      stimulus: () =>
        `<div class="screen"><p>${texts.coding.done}</p>${texts.stroop.intro(ctx.stimuli.stroop.look.colors.red)}</div>`,
      choices: [texts.stroop.practiceButton],
    },
    attempt(1),
    repeat,
    screen(texts.stroop.main, texts.stroop.mainButton),
    main,
  ];
}

export function stroopMessage(block, ctx) {
  const state = ctx.stroop;
  // Nothing to report if the participant never got to the first trial.
  if (!state || (state.practice.length === 0 && !state.main)) return null;
  const { look, sequence } = ctx.stimuli.stroop;
  const p = ctx.params.stroop;
  const summary = {
    stroop_practice_attempts_n: state.practice.length,
    stroop_practice_correct_1: state.practice[0]?.correct_n ?? null,
    stroop_practice_correct_2: state.practice[1]?.correct_n ?? null,
    stroop_colors_version: String(look.colors_version),
    stroop_sequence_version: String(sequence.sequence_version),
  };
  const log = {
    colors: {
      version: look.colors_version,
      variant: look.variant,
      bg: look.bg,
      hex: look.colors,
      order: look.order,
      words: look.words.map((w) => w.word),
    },
    sequence: { version: sequence.sequence_version, seed: sequence.seed, main_length: sequence.main_length },
    sizes_mm: {
      area: look.area,
      word_cap: look.word_cap_mm,
      word_above_dot: look.word_above_dot_mm,
      dot: look.dot_mm,
      plates: look.plates,
    },
    limits: { response_limit_ms: p.responseLimitMs, iti_ms: p.itiMs, feedback_ms: p.feedbackMs },
    scale_source: ctx.scale().source,
    practice: {
      trials: p.practiceTrials,
      min_correct: p.practiceMinCorrect,
      attempts: state.practice,
    },
  };
  if (state.main) {
    const { trials, ...counts } = state.main;
    const cond = (c) => ({
      [`stroop_${c}_correct_n`]: counts[c].correct_n,
      [`stroop_${c}_errors_n`]: counts[c].errors_n,
      [`stroop_${c}_timeouts_n`]: counts[c].timeouts_n,
      [`stroop_${c}_rt_ms`]: counts[c].rt_ms,
    });
    Object.assign(summary, {
      stroop_effect_ms: counts.effect_ms, // the main indicator (hypothesis 4)
      ...cond('congruent'),
      ...cond('incongruent'),
      stroop_correct_n: counts.correct_n,
      stroop_errors_n: counts.errors_n,
      stroop_timeouts_n: counts.timeouts_n,
      stroop_miss_n: counts.miss_n,
      stroop_time_ms: counts.time_ms,
    });
    // Leaving the tab, losing focus and leaving fullscreen during the main part itself
    // (decision 168, as in the TMT and the coding): stroop_test_hidden_n, ... .
    for (const [key, value] of Object.entries(state.during ?? {})) summary[`stroop_test_${key}`] = value;
    log.main = { ...counts, trials, during_test: state.during };
  }
  return { summary, log };
}
