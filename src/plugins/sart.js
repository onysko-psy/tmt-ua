import { ParameterType } from '../lib.js';
import { runSart } from '../sart/run.js';

// One run of the SART task as a jsPsych trial (T3.2): a training attempt or
// the main part. All behaviour is in sart/run.js. The full result, with
// every trial, goes to on_result; the jsPsych trial's own data holds only the
// counts, so that its data stay small.
export class SartPlugin {
  static info = {
    name: 'tmtua-sart',
    version: '1.0.0',
    parameters: {
      // Options of runSart except its callbacks (see sart/run.js).
      config: { type: ParameterType.OBJECT },
      on_test_start: { type: ParameterType.FUNCTION, default: null },
      on_test_end: { type: ParameterType.FUNCTION, default: null },
      on_result: { type: ParameterType.FUNCTION, default: null },
    },
    data: {
      mode: { type: ParameterType.STRING },
      status: { type: ParameterType.STRING },
      time_ms: { type: ParameterType.INT },
      trials_n: { type: ParameterType.INT },
      hit_n: { type: ParameterType.INT },
      omission_n: { type: ParameterType.INT },
      commission_n: { type: ParameterType.INT },
      withhold_n: { type: ParameterType.INT },
    },
  };

  constructor(jsPsych) {
    this.jsPsych = jsPsych;
  }

  trial(displayElement, trial) {
    const run = runSart(displayElement, {
      ...trial.config,
      onStart: trial.on_test_start,
      onEnd: trial.on_test_end,
    });
    run.promise.then((result) => {
      trial.on_result?.(result);
      displayElement.replaceChildren();
      const data = {};
      for (const key of Object.keys(SartPlugin.info.data)) data[key] = result[key];
      this.jsPsych.finishTrial(data);
    });
  }
}
