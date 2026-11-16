import { ParameterType } from '../lib.js';
import { runCoding } from '../coding/run.js';

// One run of the symbol coding task as a jsPsych trial (T3.1): a training
// attempt or the main part. All behaviour is in coding/run.js. The full
// result, with every answer, goes to on_result; the trial's own data holds
// only the counts, so that jsPsych's data stay small.
export class CodingPlugin {
  static info = {
    name: 'tmtua-coding',
    version: '1.0.0',
    parameters: {
      // Options of runCoding except its callbacks (see coding/run.js).
      config: { type: ParameterType.OBJECT },
      on_test_start: { type: ParameterType.FUNCTION, default: null },
      on_test_end: { type: ParameterType.FUNCTION, default: null },
      on_result: { type: ParameterType.FUNCTION, default: null },
    },
    data: {
      mode: { type: ParameterType.STRING },
      status: { type: ParameterType.STRING },
      time_ms: { type: ParameterType.INT },
      correct_n: { type: ParameterType.INT },
      errors_n: { type: ParameterType.INT },
      answers_n: { type: ParameterType.INT },
      extra_keys_n: { type: ParameterType.INT },
    },
  };

  constructor(jsPsych) {
    this.jsPsych = jsPsych;
  }

  trial(displayElement, trial) {
    const run = runCoding(displayElement, {
      ...trial.config,
      onStart: trial.on_test_start,
      onEnd: trial.on_test_end,
    });
    run.promise.then((result) => {
      trial.on_result?.(result);
      displayElement.replaceChildren();
      const data = {};
      for (const key of Object.keys(CodingPlugin.info.data)) data[key] = result[key];
      this.jsPsych.finishTrial(data);
    });
  }
}
