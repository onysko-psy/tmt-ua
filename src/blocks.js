import { placeholder, placeholderMessage } from './tasks/placeholder.js';
import { deviceCheck, deviceCheckMessage } from './tasks/device_check.js';
import { fullscreenScreens, fullscreenMessage } from './tasks/fullscreen.js';
import { calibrationScreens, calibrationMessage } from './tasks/calibration.js';
import { tmtScreens, tmtMessage } from './tasks/tmt.js';
import { codingScreens, codingMessage } from './tasks/coding.js';
import { stroopScreens, stroopMessage } from './tasks/stroop.js';
import { sartScreens, sartMessage } from './tasks/sart.js';
import {
  consentScreens,
  consentRetestScreens,
  consentMessage,
  criteriaScreens,
  criteriaMessage,
  demographicsScreens,
  demographicsMessage,
  conditionsScreens,
  conditionsMessage,
} from './tasks/questionnaires.js';
import {
  pssScreens,
  pssMessage,
  postScreens,
  postMessage,
  inviteScreens,
  inviteMessage,
  thanksScreens,
  thanksMessage,
} from './tasks/closing.js';

// Blocks of a first session in their fixed order (decision 33;
// docs/11-technical-plan.md, section 2). build(block, ctx) returns the block's
// part of the jsPsych timeline; message(block, ctx) runs when the block ends
// and returns what to send to the receiver ({ summary, log, contact }) or
// null. ctx is { jsPsych, params, session, sender, monitor, stimuli,
// calibration, scale(), end(status), ending() }; a block calls ctx.end(status) to end the session
// early after itself (main.js). label is shown in the dev menu, task names
// the development task that builds the block.
// isTask marks the five tasks: each starts only in fullscreen, and what
// happens around it (leaving the tab, fullscreen, zoom) is recorded
// (decisions 87, 99).

const block = (id, label, task, { isTask = false, build = placeholder, message = placeholderMessage } = {}) => ({
  id,
  label,
  task,
  isTask,
  build,
  message,
});

const TASK = { isTask: true };
const TMT = { ...TASK, build: tmtScreens, message: tmtMessage };
const CODING = { ...TASK, build: codingScreens, message: codingMessage };
const STROOP = { ...TASK, build: stroopScreens, message: stroopMessage };
const SART = { ...TASK, build: sartScreens, message: sartMessage };

export const BLOCKS = [
  block('device_check', 'Перевірка пристрою', 'Т0.5', { build: deviceCheck, message: deviceCheckMessage }),
  block('consent', 'Згода', 'Т2.2', { build: consentScreens, message: consentMessage }),
  block('criteria', 'Критерії включення й виключення', 'Т2.2', { build: criteriaScreens, message: criteriaMessage }),
  block('demographics', 'Біографічна анкета', 'Т2.2', { build: demographicsScreens, message: demographicsMessage }),
  block('conditions', 'Анкета умов', 'Т2.2', { build: conditionsScreens, message: conditionsMessage }),
  block('calibration', 'Калібрування екрана', 'Т0.6', { build: calibrationScreens, message: calibrationMessage }),
  block('fullscreen', 'Повноекранний режим', 'Т0.5', { build: fullscreenScreens, message: fullscreenMessage }),
  block('tmt_a', 'TMT, частина A', 'Т1.2–Т1.4', TMT),
  block('tmt_b', 'TMT, частина B', 'Т1.2–Т1.4', TMT),
  block('coding', 'Кодування символів', 'Т3.1', CODING),
  block('stroop', 'Stroop', 'Т3.2', STROOP),
  block('sart', 'SART', 'Т3.3', SART),
  block('pss10', 'PSS-10', 'Т2.3', { build: pssScreens, message: pssMessage }),
  block('post', 'Питання після тесту', 'Т2.3', { build: postScreens, message: postMessage }),
  block('retest_invite', 'Запрошення на ретест', 'Т2.3', { build: inviteScreens, message: inviteMessage }),
  block('thanks', 'Подяка', 'Т2.3', { build: thanksScreens, message: thanksMessage }),
];

export const isPlaceholder = (b) => b.build === placeholder;

// The retest (decisions 52, 71; T2.4): no criteria, no biography, no invitation
// to a retest; the consent is a short confirmation. The stimuli are the same
// as in the first session (decisions 64, 89).
const NOT_IN_RETEST = new Set(['criteria', 'demographics', 'retest_invite']);

export const RETEST_BLOCKS = BLOCKS.filter((b) => !NOT_IN_RETEST.has(b.id)).map((b) =>
  b.id === 'consent'
    ? block('consent', 'Підтвердження згоди (ретест)', 'Т2.4', { build: consentRetestScreens, message: consentMessage })
    : b,
);

export const blocksFor = (session) => (session.type === 'retest' ? RETEST_BLOCKS : BLOCKS);
