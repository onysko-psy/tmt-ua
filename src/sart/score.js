// Scores of the SART task (T3.3): from the list of trials of one run, with no
// browser needed. A trial is { digit, type, rt_ms, digit_ms, mask_ms,
// fast_n, extra_n, ... }; type is
//   'hit'         a digit other than the no-go one, pressed in time
//   'omission'    a digit other than the no-go one, not pressed (a miss)
//   'commission'  the no-go digit, pressed (a false response: the inhibition failed)
//   'withhold'    the no-go digit, not pressed (right)
// Reaction time is of the hits only. Its variability is the coefficient of
// variation, SD / mean (protocol: variability of reaction time).

const round1 = (x) => Math.round(x * 10) / 10;
const round3 = (x) => Math.round(x * 1000) / 1000;

export const sum = (xs) => xs.reduce((a, b) => a + b, 0);
export const mean = (xs) => (xs.length ? sum(xs) / xs.length : null);
// Sample standard deviation (n - 1); null with fewer than two values.
export function sd(xs) {
  if (xs.length < 2) return null;
  const m = mean(xs);
  return Math.sqrt(sum(xs.map((x) => (x - m) ** 2)) / (xs.length - 1));
}

export function outcomeOf(digit, pressed, nogoDigit) {
  if (digit === nogoDigit) return pressed ? 'commission' : 'withhold';
  return pressed ? 'hit' : 'omission';
}

export function summarize(trials, { digitMs }) {
  const count = (type) => trials.filter((t) => t.type === type).length;
  const hit_n = count('hit');
  const omission_n = count('omission');
  const commission_n = count('commission');
  const withhold_n = count('withhold');
  const go_n = hit_n + omission_n;
  const nogo_n = commission_n + withhold_n;
  const rts = trials.filter((t) => t.type === 'hit').map((t) => t.rt_ms);
  const rtMean = mean(rts);
  const rtSd = sd(rts);
  const digitMsList = trials.map((t) => t.digit_ms).filter((x) => x !== null && x !== undefined);
  const maskMsList = trials.map((t) => t.mask_ms).filter((x) => x !== null && x !== undefined);
  const deviations = digitMsList.map((x) => Math.abs(x - digitMs));
  return {
    hit_n,
    omission_n,
    commission_n,
    withhold_n,
    go_n,
    nogo_n,
    omission_rate: go_n ? round3(omission_n / go_n) : null,
    commission_rate: nogo_n ? round3(commission_n / nogo_n) : null,
    rt_mean_ms: rtMean === null ? null : round1(rtMean),
    rt_sd_ms: rtSd === null ? null : round1(rtSd),
    rt_cv: rtSd === null || !rtMean ? null : round3(rtSd / rtMean),
    fast_n: sum(trials.map((t) => t.fast_n ?? 0)),
    extra_n: sum(trials.map((t) => t.extra_n ?? 0)),
    digit_mean_ms: digitMsList.length ? round1(mean(digitMsList)) : null,
    digit_dev_mean_ms: deviations.length ? round1(mean(deviations)) : null,
    digit_dev_max_ms: deviations.length ? round1(Math.max(...deviations)) : null,
    mask_mean_ms: maskMsList.length ? round1(mean(maskMsList)) : null,
  };
}

// How many frames a stimulus lasts on a screen whose frame takes frameMs.
// The number of frames, not a timer, sets the time (decision: T3.3).
export function planFrames(frameMs, { digitMs, maskMs }) {
  return {
    digit: Math.max(1, Math.round(digitMs / frameMs)),
    total: Math.max(2, Math.round((digitMs + maskMs) / frameMs)),
  };
}

// The frame time from the times of frames: the median of the gaps between
// them, so that a few slow frames do not spoil it. `skip` first gaps are left
// out (the page has only just been drawn). Null if there are too few frames or
// the result is not that of a screen (under 24 Hz or over 250 Hz).
export function frameTimeFrom(stamps, skip = 4) {
  const gaps = [];
  for (let i = 1; i < stamps.length; i += 1) gaps.push(stamps[i] - stamps[i - 1]);
  const used = gaps.slice(skip).sort((a, b) => a - b);
  if (used.length < 10) return null;
  const median = used.length % 2 ? used[(used.length - 1) / 2] : (used[used.length / 2 - 1] + used[used.length / 2]) / 2;
  return median >= 4 && median <= 42 ? median : null;
}
