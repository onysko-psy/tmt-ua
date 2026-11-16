// A trial that shows nothing and ends at once: it lets a block that has no
// screen of its own (the thanks block, which only sends the end of the
// session) take its place in the timeline.
export class PassPlugin {
  static info = { name: 'tmtua-pass', version: '1.0.0', parameters: {}, data: {} };

  constructor(jsPsych) {
    this.jsPsych = jsPsych;
  }

  trial() {
    this.jsPsych.finishTrial({});
  }
}
