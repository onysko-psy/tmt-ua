import { loadJson } from '../coding/symbols.js';

// What the Stroop block needs (T3.2): the look and the colours (decision 151)
// and the fixed sequences (decisions 89, 92, 93). Loaded before the session
// starts, so that a failed download shows at once.

export const COLORS_URL = 'stimuli/stroop-colors.json';
export const SEQUENCE_URL = 'stimuli/stroop-sequence.json';

export async function loadStroopStimuli() {
  const [look, sequence] = await Promise.all([loadJson(COLORS_URL), loadJson(SEQUENCE_URL)]);
  if (sequence.colors_version !== look.colors_version) {
    throw new Error(`${SEQUENCE_URL}: made for colours version ${sequence.colors_version}, not ${look.colors_version}`);
  }
  return { look, sequence };
}
