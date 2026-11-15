import { ParameterType } from '../lib.js';
import { runTmt } from '../tmt/run.js';

// One run of a TMT field as a jsPsych trial (T1.2): the practice or the test
// of part A or B. All behaviour is in tmt/run.js. The full result, with every
// click and the cursor trajectory, goes to on_result; the trial's own data
// holds only the counts, so that jsPsych's data stay small.
export class TmtPlugin {
  static info = {
    name: 'tmtua-tmt',
    version: '1.0.0',
    parameters: {
      // Options of runTmt except its callbacks (see tmt/run.js).
      config: { type: ParameterType.OBJECT },
      on_test_start: { type: ParameterType.FUNCTION, default: null },
      on_test_end: { type: ParameterType.FUNCTION, default: null },
      on_result: { type: ParameterType.FUNCTION, default: null },
    },
    data: {
      part: { type: ParameterType.STRING },
      layout_id: { type: ParameterType.STRING },
      status: { type: ParameterType.STRING },
      time_ms: { type: ParameterType.INT },
      targets_total: { type: ParameterType.INT },
      targets_done: { type: ParameterType.INT },
      errors_n: { type: ParameterType.INT },
      err_wrong_target_n: { type: ParameterType.INT },
      err_alternation_n: { type: ParameterType.INT },
      repeat_n: { type: ParameterType.INT },
      miss_n: { type: ParameterType.INT },
    },
  };

  constructor(jsPsych) {
    this.jsPsych = jsPsych;
  }

  trial(displayElement, trial) {
    const run = runTmt(displayElement, {
      ...trial.config,
      onStart: trial.on_test_start,
      onEnd: trial.on_test_end,
    });
    run.promise.then((result) => {
      trial.on_result?.(result);
      displayElement.replaceChildren();
      const data = {};
      for (const key of Object.keys(TmtPlugin.info.data)) data[key] = result[key];
      this.jsPsych.finishTrial(data);
    });
  }
}
