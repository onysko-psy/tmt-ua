// App-wide settings. APP_VERSION is written into every data row. Once data
// collection starts, any change in the app needs the author's decision and a
// new version number (CLAUDE.md). Decision numbers refer to
// docs/05-history-and-decisions.md in the private research repo.

export const APP_VERSION = '0.13.0';

// Values allowed in the ?mode= URL parameter; no parameter means 'main'.
// pilot and dev write to the pilot copies of the spreadsheets (decision 53).
export const MODES = ['main', 'pilot', 'dev'];

// Google Apps Script web app that stores the data; routes rows by mode
// (receiver/Code.gs). Redeploying a new version keeps this URL.
export const RECEIVER_URL =
  'https://script.google.com/macros/s/AKfycbwMoh04a4S9_JvBzR4s4yWavwa4wUuTVS2WzYtZOCo8RMeg_t2x-I9d_R_ebUjY2NkL4g/exec';

// Task parameters approved by the author. In dev mode any number here can be
// overridden from the URL, e.g. ?mode=dev&set.tmt.timeLimitMs=20000
// (see session.js); main and pilot always use these values.
export const PARAMS = {
  tmt: {
    timeLimitMs: 300_000, // decision 57
    practiceMaxAttempts: 5, // decision 58
    practiceHintAfterAttempts: 2, // decision 58
    trajectoryHz: 30, // decision 61
    // Stimulus sizes in mm (decision 127); the layout itself, with its
    // version, is stimuli/tmt-layout.json (decision 128). A field unit of the
    // layout is 1/100 of the field height.
    fieldWidthMm: 240,
    fieldHeightMm: 150,
    circleMm: 11,
    letterMm: 4.5, // height of capital letters and digits
    font: 'montserrat-semibold', // bundled in src/fonts/ (decision 131)
  },
  // Criteria of taking part (decisions 11, 86): ages inclusive.
  criteria: {
    ageMin: 18,
    ageMax: 45,
  },
  coding: {
    durationMs: 90_000, // protocol
    practiceItems: 10, // decision 80
    practiceRepeatAtErrors: 3, // decision 80
    // Sizes in mm: A PROPOSAL until the author confirms (stage 1 of T3.1).
    // The same figure size in the key and in the frame, as on the SDMT form.
    figureMm: 14, // a figure in the key and in the frame
    keyCellMm: 22, // width of a key cell; nine cells are 198 mm, inside the 240 mm area
    keyDigitMm: 5, // height of the digits under the figures (TMT letters are 4.5)
    frameMm: 28, // the frame round the current figure
  },
  stroop: {
    // The look (colours, sizes in mm) is stimuli/stroop-colors.json (decision 151).
    practiceTrials: 12, // decision 92
    practiceMinCorrect: 9, // decision 92
    mainTrials: 96, // decision 84
    responseLimitMs: 5000, // decision 91
    itiMs: 500, // decision 93
    feedbackMs: 1500, // training only (decision 153)
  },
  sart: {
    practiceTrials: 18, // decision 85
    mainTrials: 225, // decision 66
    digitMs: 250, // Robertson et al., 1997
    maskMs: 900, // Robertson et al., 1997
  },
  // Screen calibration with a card (decisions 60, 100).
  calibration: {
    attempts: 2, // a suspect result is asked to be redone once (decision 100)
    screenWidthMinMm: 180, // the screen width a card result implies must be
    screenWidthMaxMm: 900, // plausible: an 8" tablet .. a 40" monitor
  },
  // The area the tasks need, in mm: the TMT field (decision 127). Laptops
  // from about 12.5" hold it.
  screen: {
    minWidthMm: 240,
    minHeightMm: 150,
    windowChecks: 3, // without fullscreen: tries to make the window big enough (decision 101)
  },
  // Technical, not research parameters: how data delivery waits and retries
  // (data/sender.js). The receiver's first reply after a pause takes ~7 s.
  send: {
    timeoutMs: 30_000,
    retryBaseMs: 2000,
    retryMaxMs: 30_000,
  },
};
