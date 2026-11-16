// Scores of the Stroop task (T3.2): from the list of trials of one run, with
// no browser needed. A trial is { word, ink, condition, type, rt_ms, ... } with
// type 'correct', 'error' (a wrong plate) or 'timeout' (no answer in time).
//
// The Stroop effect is the mean reaction time of incongruent trials minus that
// of congruent ones, over the correct trials only (protocol, hypothesis 4).
// It is null when a condition has no correct trial.

const round1 = (x) => Math.round(x * 10) / 10;

export const conditionOf = (word, ink) => (word === ink ? 'congruent' : 'incongruent');

function ofCondition(trials, condition) {
  const own = trials.filter((trial) => trial.condition === condition);
  const correct = own.filter((trial) => trial.type === 'correct');
  return {
    n: own.length,
    correct_n: correct.length,
    errors_n: own.filter((trial) => trial.type === 'error').length,
    timeouts_n: own.filter((trial) => trial.type === 'timeout').length,
    rt_ms: correct.length ? round1(correct.reduce((sum, trial) => sum + trial.rt_ms, 0) / correct.length) : null,
  };
}

export function summarize(trials) {
  const congruent = ofCondition(trials, 'congruent');
  const incongruent = ofCondition(trials, 'incongruent');
  return {
    congruent,
    incongruent,
    correct_n: congruent.correct_n + incongruent.correct_n,
    errors_n: congruent.errors_n + incongruent.errors_n,
    timeouts_n: congruent.timeouts_n + incongruent.timeouts_n,
    effect_ms: congruent.rt_ms === null || incongruent.rt_ms === null ? null : round1(incongruent.rt_ms - congruent.rt_ms),
  };
}
