import { loadJson } from '../coding/symbols.js';

// What the SART block needs (T3.3): the look (decision 156) and the fixed
// sequences (decisions 89, 85, 93). Loaded before the session starts, so that a
// failed download shows at once.

export const LOOK_URL = 'stimuli/sart-look.json';
export const SEQUENCE_URL = 'stimuli/sart-sequence.json';

export async function loadSartStimuli() {
  const [look, sequence] = await Promise.all([loadJson(LOOK_URL), loadJson(SEQUENCE_URL)]);
  if (sequence.look_version !== look.look_version) {
    throw new Error(`${SEQUENCE_URL}: made for look version ${sequence.look_version}, not ${look.look_version}`);
  }
  return { look, sequence };
}
